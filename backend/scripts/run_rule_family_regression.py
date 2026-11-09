#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run rule-family regression against 07_回归测试集.jsonl and persist review_backtest_runs."""
from __future__ import annotations

import argparse
import json
import re
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from app.database import SessionLocal, create_tables
from app.models.document import Document
from app.models.issue import Issue
from app.models.review_backtest_run import ReviewBacktestRun
from app.review_engine.annotation_baseline import (
    HumanAnnotation,
    _issue_blob,
    _load_families,
    _matches_annotation_loosely,
    _matches_annotation_strictly,
    _matches_expected_rule,
    _rule_family_has_text_evidence,
    family_is_reachable,
)
from app.review_engine.issue_rule import looks_like_rule_no

FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "regression_701_rules.jsonl"
DOC_NO_RE = re.compile(r"H-020-\d{6}")


def _doc_no(text: str) -> str:
    m = DOC_NO_RE.search(text or "")
    return m.group(0) if m else ""


def _version_align(sample_file: str, issue_file: str) -> str:
    left, right = _doc_no(sample_file), _doc_no(issue_file)
    if not left or not right:
        return "不可判定"
    if left != right:
        return "不一致"
    sample_l = (sample_file or "").lower()
    issue_l = (issue_file or "").lower()
    if sample_l and issue_l and Path(sample_l).stem[:40] == Path(issue_l).stem[:40]:
        return "一致"
    return "基本一致"


def _looks_like_rule_no(value: str) -> bool:
    return looks_like_rule_no(value)


def _issue_dict(row: Issue, filename: str) -> dict:
    return {
        "id": row.id,
        "rule": row.rule or "",
        "category": row.category or "",
        "original_text": row.original_text or "",
        "suggestion": row.suggestion or "",
        "description": row.description or "",
        "context": row.context or "",
        "audit_basis": row.audit_basis or "",
        "page": getattr(row, "page", None),
        "doc_file": filename,
    }


def _hit_tier(item: HumanAnnotation, issue: dict, blob: str) -> tuple[str, bool, bool]:
    aligned = _matches_expected_rule(item, issue, blob)
    text_ev = _rule_family_has_text_evidence(item, issue, blob) or _matches_annotation_loosely(
        item, issue, blob, allow_rule_family=False
    )
    loose = _matches_annotation_loosely(item, issue, blob)
    strict = _matches_annotation_strictly(item, issue, blob)
    if aligned and text_ev:
        return "TRUE_HIT", loose, strict
    if aligned:
        return "ALIGN_ONLY", loose, strict
    if text_ev or loose:
        return "TEXT_ONLY", loose, strict
    return "NONE", loose, strict


def load_samples(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def run_regression(db, fixture: Path = FIXTURE) -> dict:
    create_tables()
    samples = load_samples(fixture)
    families = _load_families()
    documents = {row.id: row for row in db.query(Document).all()}
    issues_by_doc = defaultdict(list)
    for issue in db.query(Issue).all():
        issues_by_doc[issue.review_id].append(issue)

    from app.models.review import Review
    reviews = {row.id: row for row in db.query(Review).all()}
    filename_by_review = {}
    for rid, review in reviews.items():
        doc = documents.get(review.document_id)
        filename_by_review[rid] = (doc.filename if doc else "") or ""

    run_id = datetime.utcnow().strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
    stats = defaultdict(int)
    per_rule = defaultdict(lambda: defaultdict(int))

    for sample in samples:
        item = HumanAnnotation(
            file=sample.get("doc_file") or "",
            page=str(sample.get("page") or ""),
            annotation_type="",
            author="",
            comment=sample.get("comment") or "",
            selected_text=sample.get("anchor") or "",
            context=sample.get("anchor") or "",
            category=sample.get("label_name") or "",
            layer=sample.get("layer") or "",
            expected_rule=sample.get("expected_rule") or "",
        )
        sample_no = sample.get("doc") or _doc_no(item.file)
        entry = families.get(item.expected_rule) or {}
        if entry and not entry.get("disabled"):
            stats["enabled_family"] += 1
        if family_is_reachable(item.expected_rule, entry):
            stats["reachable_family"] += 1
        matched_issues = []
        for review_id, rows in issues_by_doc.items():
            filename = filename_by_review.get(review_id, "")
            if _doc_no(filename) != sample_no:
                continue
            for row in rows:
                payload = _issue_dict(row, filename)
                if not _looks_like_rule_no(payload["rule"]):
                    # 前置条件②：rule 不是规则号时，规则族闸门不可用
                    payload["_rule_polluted"] = True
                matched_issues.append(payload)

        if not matched_issues:
            align = "不可判定"
            if entry.get("disabled") or not entry:
                reason = "规则族未接通"
            else:
                reason = "样本版本不可判定"
            tier, loose, strict, channel = "NONE", False, False, ""
            countable = False
        else:
            best = None
            for issue in matched_issues:
                align = _version_align(item.file, issue.get("doc_file") or "")
                if align in {"不一致", "不可判定"}:
                    continue
                blob = _issue_blob(issue)
                tier, loose, strict = _hit_tier(item, issue, blob)
                candidate = (tier, loose, strict, align, issue)
                if best is None or (
                    ["NONE", "TEXT_ONLY", "ALIGN_ONLY", "TRUE_HIT"].index(tier)
                    > ["NONE", "TEXT_ONLY", "ALIGN_ONLY", "TRUE_HIT"].index(best[0])
                ):
                    best = candidate
            if best is None:
                align = "不可判定"
                reason = "样本版本不可判定"
                tier, loose, strict, channel = "NONE", False, False, ""
                countable = False
            else:
                tier, loose, strict, align, issue = best
                channel = issue.get("rule") or ""
                countable = True
                if tier == "NONE":
                    reason = "真实漏检" if not entry.get("disabled") else "规则族未接通"
                else:
                    reason = ""

        if countable:
            stats["countable"] += 1
            if loose:
                stats["loose"] += 1
            if tier == "TRUE_HIT":
                stats["true_hit"] += 1
            if strict:
                stats["strict"] += 1
            if sample.get("must_detect") and tier != "TRUE_HIT":
                stats["must_detect_miss"] += 1
            if sample.get("must_detect"):
                stats["must_detect"] += 1
        else:
            stats["uncountable"] += 1

        per_rule[item.expected_rule][tier] += 1
        db.add(ReviewBacktestRun(
            run_id=run_id,
            sample_id=sample.get("id") or "",
            expected_rule=item.expected_rule,
            doc_no=sample_no,
            doc_file=item.file,
            version_align=align,
            hit_tier=tier,
            channel=channel,
            loose_hit=loose,
            strict_hit=strict,
            must_detect=bool(sample.get("must_detect")),
            miss_reason=reason,
            payload=json.dumps({
                "label_code": sample.get("label_code"),
                "comment": sample.get("comment"),
            }, ensure_ascii=False),
        ))

    db.commit()
    summary = {
        "run_id": run_id,
        "samples": len(samples),
        "rules": len(per_rule),
        "countable": stats["countable"],
        "uncountable": stats["uncountable"],
        "loose": stats["loose"],
        "true_hit": stats["true_hit"],
        "strict": stats["strict"],
        "must_detect": stats["must_detect"],
        "must_detect_miss": stats["must_detect_miss"],
        "true_hit_recall": (stats["true_hit"] / stats["countable"]) if stats["countable"] else None,
        "strict_recall": (stats["strict"] / stats["countable"]) if stats["countable"] else None,
        "must_detect_miss_rate": (stats["must_detect_miss"] / stats["must_detect"]) if stats["must_detect"] else None,
        "note": "不得把 0.6667 当作 recall 基线；只认 TRUE_HIT。",
        "enabled_family_samples": stats["enabled_family"],
        "reachable_family_samples": stats["reachable_family"],
        "family_coverage_pct": round(stats["reachable_family"] / len(samples) * 100, 1) if samples else 0.0,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", default=str(FIXTURE))
    args = parser.parse_args()
    db = SessionLocal()
    try:
        run_regression(db, Path(args.fixture))
    finally:
        db.close()


if __name__ == "__main__":
    main()
