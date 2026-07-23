#!/usr/bin/env python3
import argparse
import json
import re
import sys
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


def evaluate(review_id, markers):
    db = SessionLocal()
    try:
        issues = [issue_to_dict(issue) for issue in db.query(Issue).filter(Issue.review_id == review_id).all()]
    finally:
        db.close()

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
    if document_filename:
        normalized_doc = normalize_filename_for_match(document_filename)
        scoped = [item for item in annotations if normalize_filename_for_match(item.file) in normalized_doc or normalized_doc in normalize_filename_for_match(item.file)]
        if scoped:
            annotations = scoped
    result["human_baseline"] = evaluate_against_annotations(issues, annotations)
    result["human_baseline"]["document_filename"] = document_filename
    return result


def normalize_filename_for_match(filename):
    stem = Path(str(filename or "")).stem.lower()
    stem = stem.replace(" tina", "").replace(" reviewed by yuanyuan", "").replace(" reviewed by yy", "")
    stem = stem.replace(" peered by tina", "").replace(" peered by leiwy&tina", "")
    stem = stem.replace("未加密", "")
    return "".join(ch for ch in stem if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")


def main():
    parser = argparse.ArgumentParser(description="Evaluate review issue quality for a completed review.")
    parser.add_argument("--review-id", type=int, required=True)
    parser.add_argument("--marker", action="append", default=[])
    parser.add_argument("--human-baseline", help="Markdown file generated from human review annotations")
    args = parser.parse_args()

    markers = args.marker or DEFAULT_MARKERS
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


if __name__ == "__main__":
    raise SystemExit(main())
