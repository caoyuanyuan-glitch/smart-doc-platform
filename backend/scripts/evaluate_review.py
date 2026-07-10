#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import SessionLocal
from app.models.document import Document
from app.models.issue import Issue
from app.models.review import Review
from app.review_engine.annotation_baseline import evaluate_against_annotations, parse_human_annotation_markdown
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
    annotations = parse_human_annotation_markdown(baseline_path)
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
