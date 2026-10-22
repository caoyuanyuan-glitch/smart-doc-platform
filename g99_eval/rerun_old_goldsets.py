"""Re-score stored goldsets if matching PDFs or review rows exist."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("SDP_ROOT", Path(__file__).resolve().parents[1]))
BACKEND = Path(os.environ.get("SDP_BACKEND", ROOT / "backend"))
SUITE = BACKEND / "config" / "review-evaluation-suite.accuracy.json"
OUT = ROOT / "g99_eval" / "old_goldset_rerun.json"


def find_pdfs():
    hits = []
    for path in ROOT.rglob("*.pdf"):
        name = path.name.lower()
        if "e25" in name or "gospatial" in name or "high-throughput" in name or "高通量" in name:
            hits.append(str(path))
    return hits


def main():
    sys.path.insert(0, str(BACKEND))
    os.chdir(str(BACKEND))
    suite = json.loads(SUITE.read_text(encoding="utf-8"))
    from app.database import SQLALCHEMY_DATABASE_URL, SessionLocal
    from app.models.issue import Issue
    from app.models.review import Review
    from app.review_engine.annotation_baseline import (
        HumanAnnotation,
        evaluate_against_annotations,
        parse_human_annotation_markdown,
    )
    sys.path.insert(0, str(ROOT / "g99_eval"))
    from eval_common import (
        classify_old_goldset_status,
        compact_eval,
        expected_pdf_path,
        issue_row_to_dict,
        pdfs_for_goldset,
        redact_database_dsn,
    )

    pdf_hits = find_pdfs()
    dsn = redact_database_dsn(SQLALCHEMY_DATABASE_URL)
    db = None
    db_error = None
    try:
        db = SessionLocal()
        db.query(Review.id).limit(1).all()
    except Exception as exc:
        db_error = f"{exc.__class__.__name__}: dsn={dsn}"
        if db is not None:
            db.close()
        db = None

    reports = []
    for item in suite.get("documents") or []:
        name = item.get("name")
        review_id = item.get("review_id")
        baseline = BACKEND / item.get("baseline")
        item_pdfs = pdfs_for_goldset(name, pdf_hits)
        expected = expected_pdf_path(name, ROOT)
        row = {
            "name": name,
            "review_id": review_id,
            "baseline": str(baseline),
            "expected_pdf": expected,
            "pdf_hits": item_pdfs,
            "dsn": dsn,
        }
        review = None
        query_error = db_error
        if db is not None and review_id:
            try:
                review = db.query(Review).filter(Review.id == review_id).first()
            except Exception as exc:
                query_error = f"{exc.__class__.__name__}: dsn={dsn}"
                review = None
        status, error = classify_old_goldset_status(
            baseline_exists=baseline.exists(),
            review_id=review_id,
            db_error=query_error,
            review_found=bool(review),
            pdf_hits=item_pdfs,
            expected_pdf=expected,
        )
        row["status"] = status
        if error:
            row["error"] = error
        if status == "rerun" and review is not None:
            issues = [issue_row_to_dict(issue) for issue in db.query(Issue).filter(Issue.review_id == review_id).all()]
            if baseline.suffix == ".json":
                data = json.loads(baseline.read_text(encoding="utf-8-sig"))
                anns = [HumanAnnotation(**ann) for ann in data.get("annotations", [])]
            else:
                anns = parse_human_annotation_markdown(baseline.read_text(encoding="utf-8-sig"))
            row["metrics"] = compact_eval(evaluate_against_annotations(issues, anns))
            if name == "e25rs_en":
                issue_total = row["metrics"].get("issue_total") or 0
                strict_recall = row["metrics"].get("strict_recall") or 0
                row["gate"] = {
                    "issue_limit": 17,
                    "min_strict_recall": 0.85,
                    "broken": bool(issue_total >= 18 or strict_recall < 0.85),
                }
        reports.append(row)
    if db is not None:
        db.close()
    payload = {"pdf_hits": pdf_hits, "dsn": dsn, "documents": reports}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=1), flush=True)


if __name__ == "__main__":
    main()
