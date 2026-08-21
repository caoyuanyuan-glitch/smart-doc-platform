#!/usr/bin/env python3
import argparse
import json
import re
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import SessionLocal
from app.models.document import Document
from app.models.issue import Issue
from app.models.review import Review
from app.review_engine.annotation_baseline import HumanAnnotation, evaluate_against_annotations, parse_human_annotation_markdown
from app.review_engine.layers import count_issue_layers
from app.review_engine.validation import (
    ai_suggestion_changes_numeric_values,
    ai_suggestion_changes_protected_meaning,
    has_substantive_suggestion,
)


DEFAULT_MARKERS = [
    "There are 12 columns on each plate",
    "There are 24 columns on each adapter plate",
    "For In Vitro Diagnostic Use",
    "fragmentase",
    "and so forth",
    "along with the corresponding kit",
    "30°C",
    "0.1×TE",
    "E. coli, etc.",
    "yeast, etc.",
]

HIGH_VALUE_RULE_PATTERNS = [
    r"^DOC-(?:REV|SEC|NET|TM|REG|SCOPE|FIGTAB|PROC|MODEL|URL)",
    r"^CHECKLIST-",
    r"^CYY-",
]

HIGH_VALUE_TEXT_PATTERN = re.compile(
    r"revision\s+history|版本记录|default\s+(?:account|password|username)|credential|"
    r"password|ip\s+address|\b(?:\d{1,3}\.){3}\d{1,3}:\d{2,5}\b|trademark|DNBSEQ|"
    r"合规|法规|注册|默认账号|默认密码|密码|商标|物料编码|图片|图标|对象缺失|"
    r"表格|版式|术语一致|重复内容|操作步骤|不可执行|信息完整|缺失|不完整",
    re.IGNORECASE,
)

LOW_VALUE_TEXT_PATTERN = re.compile(
    r"括号后请添加空格|建议拆分为多个短句|article|冠词|punctuation|标点|capitalization|"
    r"formatting\s+artifact|tab|click\s+the\s+icon|\[table content\]|check\s+if|"
    r"\ban\s+fq\b|\bto\s+to\b|after\s+login|Browse|Edit",
    re.IGNORECASE,
)


def issue_to_dict(issue):
    return {
        "id": issue.id,
        "source": issue.source or "",
        "rule": issue.rule or "",
        "category": issue.category or "",
        "severity": issue.severity or "",
        "original_text": issue.original_text or "",
        "suggestion": issue.suggestion or "",
        "description": issue.description or "",
        "audit_basis": issue.audit_basis or "",
    }


def contains_marker(issue, marker):
    blob = json.dumps(issue, ensure_ascii=False).lower()
    return marker.lower() in blob


def issue_blob(issue):
    return " ".join(str(issue.get(key, "") or "") for key in [
        "source", "rule", "category", "severity", "original_text", "suggestion", "description", "audit_basis",
    ])


def is_high_value_issue(issue):
    rule = str(issue.get("rule", "") or "")
    if any(re.search(pattern, rule, re.IGNORECASE) for pattern in HIGH_VALUE_RULE_PATTERNS):
        return True
    return bool(HIGH_VALUE_TEXT_PATTERN.search(issue_blob(issue)))


def is_low_value_noise(issue):
    if is_high_value_issue(issue):
        return False
    blob = issue_blob(issue)
    rule = str(issue.get("rule", "") or "").upper()
    source = str(issue.get("source", "") or "").lower()
    category = str(issue.get("category", "") or "")
    if source == "spellcheck":
        return True
    if rule.startswith(("SPELL", "PUNCT")):
        return True
    if rule in {"R029", "R035", "HR009", "R036", "TENSE-001", "PUNCT-002", "R002", "R003"}:
        return True
    if re.search(r"普通语法|拼写检查|标点符号|字体/版式细节", category, re.IGNORECASE):
        return True
    return bool(LOW_VALUE_TEXT_PATTERN.search(blob))


def summarize_effectiveness(issues):
    high_value = [issue for issue in issues if is_high_value_issue(issue)]
    low_value = [issue for issue in issues if is_low_value_noise(issue)]
    categories = {}
    rules = {}
    sources = {}
    for issue in issues:
        category = issue.get("category") or "-"
        rule = issue.get("rule") or "-"
        source = issue.get("source") or "-"
        categories[category] = categories.get(category, 0) + 1
        rules[rule] = rules.get(rule, 0) + 1
        sources[source] = sources.get(source, 0) + 1
    total = len(issues)
    return {
        "high_value_count": len(high_value),
        "high_value_rate": round(len(high_value) / total, 4) if total else 0,
        "low_value_noise_count": len(low_value),
        "low_value_noise_rate": round(len(low_value) / total, 4) if total else 0,
        "by_source": dict(sorted(sources.items(), key=lambda pair: (-pair[1], pair[0]))),
        "by_category": dict(sorted(categories.items(), key=lambda pair: (-pair[1], pair[0]))),
        "top_rules": dict(sorted(rules.items(), key=lambda pair: (-pair[1], pair[0]))[:20]),
        "high_value_items": high_value[:20],
        "low_value_noise_items": low_value[:20],
    }


def load_human_annotations(path):
    baseline_path = Path(path)
    if baseline_path.suffix.lower() == ".json":
        payload = json.loads(baseline_path.read_text(encoding="utf-8-sig"))
        return [HumanAnnotation(**item) for item in payload.get("annotations", [])]
    return parse_human_annotation_markdown(baseline_path)


def _norm_match_text(value):
    return re.sub(r"\s+", "", str(value or "")).lower()


def _matches_any_text(value, candidates):
    value_norm = _norm_match_text(value)
    if not value_norm:
        return False
    for candidate in candidates or []:
        candidate_norm = _norm_match_text(candidate)
        if candidate_norm and candidate_norm in value_norm:
            return True
    return False


def _as_list(value):
    if not value:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _annotation_matches_ignore_rule(item, patterns):
    blob = " ".join([item.category, item.expected_rule, item.comment, item.selected_text, item.context])
    return _matches_any_text(blob, patterns)


def _issue_matches_false_positive(issue, patterns):
    blob = " ".join([issue.get("rule", ""), issue.get("category", ""), issue.get("original_text", ""), issue.get("suggestion", ""), issue.get("description", "")])
    return _matches_any_text(blob, patterns)


def _evaluate_annotation_filters(annotations, allowed_misses, explicit_false_positives):
    kept = []
    ignored = []
    for item in annotations:
        if _annotation_matches_ignore_rule(item, allowed_misses):
            ignored.append(asdict(item))
            continue
        kept.append(item)
    return kept, ignored


def _evaluate_issue_filters(issues, explicit_false_positives):
    kept = []
    ignored = []
    for issue in issues:
        if _issue_matches_false_positive(issue, explicit_false_positives):
            ignored.append(issue)
            continue
        kept.append(issue)
    return kept, ignored


def evaluate(review_id, markers):
    db = SessionLocal()
    try:
        issues = [issue_to_dict(issue) for issue in db.query(Issue).filter(Issue.review_id == review_id).all()]
        review = db.query(Review).filter(Review.id == review_id).first()
        summary_raw = review.summary if review else "{}"
    finally:
        db.close()

    summary = {}
    try:
        summary = json.loads(summary_raw) if isinstance(summary_raw, str) else (summary_raw or {})
    except Exception:
        pass

    stage_diagnostics = summary.get("stage_diagnostics", [])

    noop = []
    numeric_changed = []
    protected_changed = []
    empty_suggestions = []

    for issue in issues:
        original = issue["original_text"]
        suggestion = issue["suggestion"]
        is_ai = issue["source"].lower() == "ai"
        if not suggestion:
            empty_suggestions.append(issue)
            continue
        if issue["rule"] != "DOC-TITLE-001" and original and not has_substantive_suggestion(original, suggestion):
            noop.append(issue)
        if is_ai and original and ai_suggestion_changes_numeric_values(original, suggestion):
            numeric_changed.append(issue)
        if is_ai and original and ai_suggestion_changes_protected_meaning(original, suggestion):
            protected_changed.append(issue)

    marker_hits = {marker: sum(1 for issue in issues if contains_marker(issue, marker)) for marker in markers}
    result = {
        "review_id": review_id,
        "total": len(issues),
        "layers": count_issue_layers(issues),
        "effectiveness": summarize_effectiveness(issues),
        "empty_suggestions": len(empty_suggestions),
        "empty_suggestion_items": empty_suggestions[:20],
        "noop_suggestions": len(noop),
        "noop_suggestion_items": noop[:20],
        "numeric_changed": len(numeric_changed),
        "protected_meaning_changed": len(protected_changed),
        "marker_hits": marker_hits,
        "stage_diagnostics": stage_diagnostics,
    }
    return result


def evaluate_with_human_baseline(review_id, markers, baseline_path):
    result = evaluate(review_id, markers)
    db = SessionLocal()
    try:
        issues = [issue_to_dict(issue) for issue in db.query(Issue).filter(Issue.review_id == review_id).all()]
        review = db.query(Review).filter(Review.id == review_id).first()
        document = db.query(Document).filter(Document.id == review.document_id).first() if review else None
        document_filename = document.filename if document else ""
    finally:
        db.close()
    annotations = load_human_annotations(baseline_path)
    scoped = []
    if document_filename:
        normalized_doc = normalize_filename_for_match(document_filename)
        scoped = [item for item in annotations if normalize_filename_for_match(item.file) in normalized_doc or normalized_doc in normalize_filename_for_match(item.file)]
    if scoped:
        annotations = scoped
    result["human_baseline"] = evaluate_against_annotations(issues, annotations)
    result["human_baseline"]["document_filename"] = document_filename
    return result


def evaluate_suite_document(doc_cfg, markers):
    review_id = doc_cfg.get("review_id")
    if not review_id:
        return None

    baseline_path = doc_cfg.get("baseline") or doc_cfg.get("baseline_document")
    standard_answers = _as_list(doc_cfg.get("standard_answers"))
    explicit_false_positives = _as_list(doc_cfg.get("explicit_false_positives"))
    allowed_misses = _as_list(doc_cfg.get("allowed_misses"))

    if not baseline_path and standard_answers:
        baseline_path = standard_answers[0]

    if baseline_path:
        result = evaluate_with_human_baseline(review_id, markers, baseline_path)
    else:
        result = evaluate(review_id, markers)

    result["config"] = {
        "name": doc_cfg.get("name", f"review_{review_id}"),
        "standard_answers": list(standard_answers),
        "allowed_misses": list(allowed_misses),
        "explicit_false_positives": list(explicit_false_positives),
    }

    if "human_baseline" in result:
        annotations = load_human_annotations(baseline_path)
        filtered_annotations, ignored_annotations = _evaluate_annotation_filters(
            annotations,
            allowed_misses,
            explicit_false_positives,
        )
        if filtered_annotations != annotations:
            db = SessionLocal()
            try:
                filtered_issues = [issue_to_dict(issue) for issue in db.query(Issue).filter(Issue.review_id == review_id).all()]
            finally:
                db.close()
            result["human_baseline_filtered"] = evaluate_against_annotations(
                filtered_issues,
                filtered_annotations,
            )
            result["human_baseline_filtered"]["ignored_annotations"] = ignored_annotations[:50]

    db = SessionLocal()
    try:
        issues = [issue_to_dict(issue) for issue in db.query(Issue).filter(Issue.review_id == review_id).all()]
    finally:
        db.close()
    filtered_issues, ignored_issues = _evaluate_issue_filters(issues, explicit_false_positives)
    result["suite_filters"] = {
        "filtered_issue_count": len(filtered_issues),
        "ignored_issue_count": len(ignored_issues),
        "explicit_false_positive_rules": list(explicit_false_positives),
    }
    return result


def normalize_filename_for_match(filename):
    stem = Path(str(filename or "")).stem.lower()
    stem = stem.replace(" tina", "").replace(" reviewed by yuanyuan", "").replace(" reviewed by yy", "")
    stem = stem.replace(" peered by tina", "").replace(" peered by leiwy&tina", "")
    stem = stem.replace("未加密", "")
    return "".join(ch for ch in stem if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")


def main():
    parser = argparse.ArgumentParser(description="Evaluate review issue quality for a completed review.")
    parser.add_argument("--review-id", type=int, required=False)
    parser.add_argument("--marker", action="append", default=[])
    parser.add_argument("--human-baseline", help="Markdown file generated from human review annotations")
    parser.add_argument("--config", help="JSON config file for batch evaluation")
    parser.add_argument("--consistency-check", action="store_true", help="Check consistency of the same document across runs")
    args = parser.parse_args()

    markers = args.marker or DEFAULT_MARKERS

    # Batch evaluation from config file
    if args.config:
        results = batch_evaluate_from_config(args.config, markers)
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0 if results.get("summary", {}).get("regressions", 0) == 0 else 1

    # Consistency check mode
    if args.consistency_check:
        if not args.review_id:
            print("ERROR: --review-id is required for --consistency-check", file=sys.stderr)
            return 2
        result = run_consistency_check(args.review_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("consistent", True) else 1

    if not args.review_id:
        print("ERROR: --review-id, --config, or --consistency-check is required", file=sys.stderr)
        return 2

    if args.human_baseline:
        result = evaluate_with_human_baseline(args.review_id, markers, args.human_baseline)
    else:
        result = evaluate(args.review_id, markers)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    failed = (
        result["noop_suggestions"]
        or result["numeric_changed"]
        or result["protected_meaning_changed"]
        or any(result["marker_hits"].values())
    )
    return 1 if failed else 0


def batch_evaluate_from_config(config_path, markers):
    """Evaluate multiple reviews from a JSON config file.

    Config format::

        {
          "documents": [
            {
              "name": "test_doc",
              "review_id": 123,
              "baseline": "path/to/human_baseline.md",
              "allowed_misses": ["AI-STYLE-001"],
              "explicit_false_positives": ["R029"]
            }
          ],
          "thresholds": {
            "max_noop_rate": 0.05,
            "max_numeric_change_rate": 0.0,
            "max_protected_change_rate": 0.0,
            "min_high_value_rate": 0.3
          }
        }
    """
    config = json.loads(Path(config_path).read_text(encoding="utf-8-sig"))
    documents_cfg = config.get("documents", [])
    thresholds = config.get("thresholds", {})

    results = []
    summary = {"total": 0, "passed": 0, "failed": 0, "regressions": 0}

    for doc_cfg in documents_cfg:
        review_id = doc_cfg.get("review_id")
        if not review_id:
            continue
        result = evaluate_suite_document(doc_cfg, markers)
        if not result:
            continue

        total = result["total"]
        noop_rate = result["noop_suggestions"] / max(total, 1)
        numeric_rate = result["numeric_changed"] / max(total, 1)
        protected_rate = result["protected_meaning_changed"] / max(total, 1)
        high_value_rate = result["effectiveness"]["high_value_rate"]

        checks = {
            "noop_rate_ok": noop_rate <= thresholds.get("max_noop_rate", 0.05),
            "numeric_rate_ok": numeric_rate <= thresholds.get("max_numeric_change_rate", 0.0),
            "protected_rate_ok": protected_rate <= thresholds.get("max_protected_change_rate", 0.0),
            "high_value_rate_ok": high_value_rate >= thresholds.get("min_high_value_rate", 0.3),
        }

        all_ok = all(checks.values())
        summary["total"] += 1
        if all_ok:
            summary["passed"] += 1
        else:
            summary["failed"] += 1
            summary["regressions"] += 1

        results.append({
            "name": doc_cfg.get("name", f"review_{review_id}"),
            "review_id": review_id,
            "passed": all_ok,
            "checks": checks,
            "metrics": {
                "total": total,
                "noop_rate": round(noop_rate, 4),
                "numeric_change_rate": round(numeric_rate, 4),
                "protected_change_rate": round(protected_rate, 4),
                "high_value_rate": round(high_value_rate, 4),
            },
            "config": result.get("config", {}),
            "suite_filters": result.get("suite_filters", {}),
            "result": result,
        })

    return {"summary": summary, "results": results}


def run_consistency_check(review_id):
    """Check consistency of review results for the same document across runs.

    Compares formal issue count, rule distribution, and severity distribution
    against previous completed runs for the same document.
    """
    db = SessionLocal()
    try:
        current_review = db.query(Review).filter(Review.id == review_id).first()
        if not current_review:
            return {"error": "Review not found", "review_id": review_id}

        # Get previous completed reviews for the same document
        previous = (
            db.query(Review)
            .filter(
                Review.document_id == current_review.document_id,
                Review.id != review_id,
                Review.status == "completed",
            )
            .order_by(Review.id.desc())
            .limit(5)
            .all()
        )

        if not previous:
            return {
                "review_id": review_id,
                "consistent": True,
                "message": "No previous reviews to compare against",
                "current_total": current_review.total_issues or 0,
            }

        # Compare with the most recent previous run
        prev = previous[0]

        # Compare issue counts
        current_total = current_review.total_issues or 0
        prev_total = prev.total_issues or 0
        count_delta = abs(current_total - prev_total)
        count_delta_pct = round(count_delta / max(prev_total, 1) * 100, 1)

        # Compare severity distribution
        current_severity = _get_severity_distribution(db, review_id)
        prev_severity = _get_severity_distribution(db, prev.id)

        # Compare rule distribution
        current_rules = _get_rule_distribution(db, review_id)
        prev_rules = _get_rule_distribution(db, prev.id)

        # Jaccard similarity of rule sets
        current_rule_set = set(current_rules.keys())
        prev_rule_set = set(prev_rules.keys())
        jaccard = round(len(current_rule_set & prev_rule_set) / max(len(current_rule_set | prev_rule_set), 1), 4)

        is_consistent = jaccard >= 0.5 and count_delta_pct <= 30

        return {
            "review_id": review_id,
            "previous_review_id": prev.id,
            "consistent": is_consistent,
            "current_total": current_total,
            "previous_total": prev_total,
            "count_delta": count_delta,
            "count_delta_pct": count_delta_pct,
            "rule_jaccard": jaccard,
            "severity_comparison": {
                "current": current_severity,
                "previous": prev_severity,
            },
            "rule_comparison": {
                "current_top": dict(sorted(current_rules.items(), key=lambda x: -x[1])[:10]),
                "previous_top": dict(sorted(prev_rules.items(), key=lambda x: -x[1])[:10]),
            },
            "previous_runs_compared": len(previous),
        }
    finally:
        db.close()


def _get_severity_distribution(db, review_id):
    issues = db.query(Issue).filter(Issue.review_id == review_id).all()
    dist = {}
    for issue in issues:
        sev = (issue.severity or "general").lower()
        dist[sev] = dist.get(sev, 0) + 1
    return dist


def _get_rule_distribution(db, review_id):
    issues = db.query(Issue).filter(Issue.review_id == review_id).all()
    dist = {}
    for issue in issues:
        rule = issue.rule or "UNKNOWN"
        dist[rule] = dist.get(rule, 0) + 1
    return dist


if __name__ == "__main__":
    raise SystemExit(main())
