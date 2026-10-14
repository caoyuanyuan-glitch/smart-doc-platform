#!/usr/bin/env python3
"""从 Issue.status 聚合人工标注，估算审核 precision。

审核人在界面上每点一次「确认」或「误报」都会写入 Issue.status：
- confirmed      -> 真阳性（TP）
- false_positive -> 误报（FP）
- 其余（pending / open / ignored / ...） -> 未标注，不计入 precision 分母

precision_proxy 只在标注覆盖度足够高时才有意义，因此同时输出 label_coverage，
并在覆盖度不足时标记 trust=low。
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import SessionLocal
from app.models.document import Document
from app.models.issue import Issue
from app.models.review import Review


CONFIRMED_STATUS = "confirmed"
FALSE_POSITIVE_STATUS = "false_positive"
LOW_COVERAGE_THRESHOLD = 0.3
TOP_RULE_LIMIT = 20


def _status_of(issue):
    return str(getattr(issue, "status", "") or "").strip().lower()


def _ratio(numerator, denominator):
    if not denominator:
        return 0.0
    return round(numerator / denominator, 4)


def _tag(issue):
    status = _status_of(issue)
    if status == CONFIRMED_STATUS:
        return "confirmed"
    if status == FALSE_POSITIVE_STATUS:
        return "false_positive"
    return "unlabeled"


def build_report(issues, document_names):
    confirmed = sum(1 for issue in issues if _tag(issue) == "confirmed")
    false_positive = sum(1 for issue in issues if _tag(issue) == "false_positive")
    total = len(issues)
    labeled = confirmed + false_positive
    unlabeled = total - labeled
    label_coverage = _ratio(labeled, total)

    # 单文档维度
    per_review = defaultdict(lambda: {"confirmed": 0, "false_positive": 0, "document": ""})
    for issue in issues:
        bucket = per_review[issue.review_id]
        bucket["document"] = document_names.get(issue.review_id, "") or bucket["document"]
        tag = _tag(issue)
        if tag != "unlabeled":
            bucket[tag] += 1
    by_document = []
    for review_id in sorted(per_review):
        bucket = per_review[review_id]
        by_document.append({
            "review_id": review_id,
            "document": bucket["document"],
            "confirmed": bucket["confirmed"],
            "false_positive": bucket["false_positive"],
            "precision_proxy": _ratio(bucket["confirmed"], bucket["confirmed"] + bucket["false_positive"]),
        })

    # 来源维度
    by_source = defaultdict(lambda: {"confirmed": 0, "false_positive": 0})
    for issue in issues:
        if _tag(issue) == "unlabeled":
            continue
        source = str(getattr(issue, "source", "") or "unknown").strip().lower() or "unknown"
        by_source[source][_tag(issue)] += 1
    by_source = {source: dict(counts) for source, counts in sorted(by_source.items())}

    # 误报规则排行：提 precision 的直接抓手
    rule_counts = defaultdict(lambda: {"confirmed": 0, "false_positive": 0})
    for issue in issues:
        tag = _tag(issue)
        if tag == "unlabeled":
            continue
        rule = str(getattr(issue, "rule", "") or "").strip() or "(未命名规则)"
        rule_counts[rule][tag] += 1
    top_false_positive_rules = sorted(
        (
            {
                "rule": rule,
                "false_positive": counts["false_positive"],
                "confirmed": counts["confirmed"],
                "share": _ratio(counts["false_positive"], false_positive),
            }
            for rule, counts in rule_counts.items()
            if counts["false_positive"]
        ),
        key=lambda item: (-item["false_positive"], item["rule"]),
    )[:TOP_RULE_LIMIT]

    return {
        "overall": {
            "total_issues": total,
            "confirmed": confirmed,
            "false_positive": false_positive,
            "unlabeled": unlabeled,
            "label_coverage": label_coverage,
            "precision_proxy": _ratio(confirmed, labeled),
            "trust": "low" if label_coverage < LOW_COVERAGE_THRESHOLD else "ok",
        },
        "by_document": by_document,
        "by_source": by_source,
        "top_false_positive_rules": top_false_positive_rules,
    }


def _load_document_names(db, review_ids):
    if not review_ids:
        return {}
    names = {}
    rows = (
        db.query(Review.id, Document.filename)
        .join(Document, Document.id == Review.document_id)
        .filter(Review.id.in_(review_ids))
        .all()
    )
    for review_id, filename in rows:
        names[review_id] = filename or ""
    return names


def main():
    parser = argparse.ArgumentParser(description="Aggregate Issue.status into a precision proxy report.")
    parser.add_argument("--review-id", type=int, help="Only aggregate a single review")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        query = db.query(Issue)
        if args.review_id:
            query = query.filter(Issue.review_id == args.review_id)
        issues = query.all()
        document_names = _load_document_names(db, {issue.review_id for issue in issues})
    finally:
        db.close()

    report = build_report(issues, document_names)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
