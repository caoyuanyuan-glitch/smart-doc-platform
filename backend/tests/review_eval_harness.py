"""Read-only review evaluation harness. Does not change audit business logic."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from app.api import review as review_api
from app.utils.spell_checker import run_spelling_and_grammar_check

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "review_eval"
SAMPLES = (
    "zh_technical",
    "en_technical",
    "mixed_technical",
    "high_risk_steps",
)


def load_sample(stem: str) -> dict:
    text = (FIXTURE_DIR / f"{stem}.txt").read_text(encoding="utf-8")
    gold = json.loads((FIXTURE_DIR / f"{stem}.json").read_text(encoding="utf-8"))
    gold["text"] = text
    return gold


def collect_current_snippet_rule_issues(content: str) -> tuple[list, dict]:
    """Mirror the current snippet rule path without a database or AI provider."""
    document_language = review_api.detect_language(content)
    rule_issues = []
    if document_language == "cn":
        try:
            rule_issues.extend(run_spelling_and_grammar_check(content, "txt"))
        except Exception:
            pass
    if document_language in ("en", "both"):
        try:
            rule_issues.extend(run_spelling_and_grammar_check(content, "txt"))
        except Exception:
            pass
        try:
            rule_issues.extend(review_api._run_english_heuristic_audit(content, "txt"))
        except Exception:
            pass
        try:
            rule_issues.extend(review_api._run_manual_engineering_audit(content, "txt"))
        except Exception:
            pass
    if document_language in ("cn", "both"):
        try:
            rule_issues.extend(review_api._run_chinese_human_baseline_rules(content))
        except Exception:
            pass
    try:
        rule_issues.extend(review_api._run_snippet_content_audit(content))
    except Exception:
        pass
    final_issues, diagnostics = review_api._finalize_review_issues(
        rule_issues, content, set(), snippet_review=True,
    )
    return final_issues, {
        "document_language": document_language,
        "raw_rule_candidates": len(rule_issues),
        "filter_diagnostics": diagnostics,
    }


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "")).lower()


def _issue_blob(issue: dict) -> str:
    return _normalize(
        " ".join(
            str(issue.get(key) or "")
            for key in ("original_text", "context", "suggestion", "description")
        )
    )


def score_sample(gold: dict, issues: list) -> dict:
    expected = [item for item in gold.get("issues") or [] if item.get("expected")]
    valid = [_normalize(item) for item in gold.get("valid_expressions") or [] if item]
    used = set()
    true_positives = []
    for item in expected:
        needle = _normalize(item.get("text") or "")
        occurrence = int(item.get("occurrence") or 1)
        hits = 0
        matched_index = None
        for index, issue in enumerate(issues):
            if index in used:
                continue
            blob = _issue_blob(issue)
            original = _normalize(issue.get("original_text") or "")
            if needle and (needle in original or needle in blob):
                hits += 1
                if hits == occurrence:
                    used.add(index)
                    matched_index = index
                    break
        if matched_index is not None:
            true_positives.append(item["id"])
        # occurrence > 1 with only one reported issue stays FN

    false_negatives = [item["id"] for item in expected if item["id"] not in true_positives]
    false_positives = []
    for index, issue in enumerate(issues):
        if index in used:
            continue
        original = _normalize(issue.get("original_text") or "")
        if any(token and token in original for token in valid):
            false_positives.append(issue.get("rule") or original)
            continue
        false_positives.append(issue.get("rule") or original)

    span_keys = []
    for issue in issues:
        start, end = review_api._parse_issue_position(issue.get("position"))
        span_keys.append((issue.get("rule"), _normalize(issue.get("original_text") or ""), start, end))
    duplicates = max(0, len(span_keys) - len(set(span_keys)))

    tp = len(true_positives)
    fp = len(false_positives)
    fn = len(false_negatives)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "duplicates": duplicates,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "expected_count": len(expected),
        "issues_total": len(issues),
    }


def evaluate_sample(stem: str, review_mode: str = "snippet:rule") -> dict:
    gold = load_sample(stem)
    started = time.perf_counter()
    issues, meta = collect_current_snippet_rule_issues(gold["text"])
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    scored = score_sample(gold, issues)
    return {
        "sample_id": gold.get("sample_id") or stem,
        "review_mode": review_mode,
        "actual_status": "completed",
        "raw_rule_candidates": meta.get("raw_rule_candidates"),
        "raw_ai_candidates": 0,
        "final_issues": [
            {
                "rule": issue.get("rule"),
                "original_text": issue.get("original_text"),
                "source": issue.get("source"),
            }
            for issue in issues
        ],
        "true_positives": scored["true_positives"],
        "false_positives": scored["false_positives"],
        "false_negatives": scored["false_negatives"],
        "duplicates": scored["duplicates"],
        "ai_call_count": 0,
        "elapsed_ms": elapsed_ms,
        "summary_total": len(issues),
        "issues_total": scored["issues_total"],
        "precision": scored["precision"],
        "recall": scored["recall"],
        "f1": scored["f1"],
        "document_language": meta.get("document_language"),
        "expected_count": scored["expected_count"],
    }


def evaluate_all(review_mode: str = "snippet:rule") -> dict:
    rows = [evaluate_sample(stem, review_mode=review_mode) for stem in SAMPLES]
    tp = sum(len(row["true_positives"]) for row in rows)
    fp = sum(len(row["false_positives"]) for row in rows)
    fn = sum(len(row["false_negatives"]) for row in rows)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return {
        "review_mode": review_mode,
        "samples": rows,
        "totals": {
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round((2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0, 4),
            "elapsed_ms": sum(row["elapsed_ms"] for row in rows),
            "ai_call_count": sum(row["ai_call_count"] for row in rows),
        },
    }
