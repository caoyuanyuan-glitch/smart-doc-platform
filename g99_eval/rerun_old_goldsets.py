"""Re-score stored goldsets if matching PDFs or review rows exist."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path("/workspace")
BACKEND = ROOT / "backend"
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
    from app.database import SessionLocal
    from app.models.issue import Issue
    from app.models.review import Review
    from app.review_engine.annotation_baseline import (
        HumanAnnotation,
        evaluate_against_annotations,
        parse_human_annotation_markdown,
    )
    sys.path.insert(0, str(ROOT / "g99_eval"))
    from eval_common import compact_eval, issue_row_to_dict

    db = SessionLocal()
    reports = []
    for item in suite.get("documents") or []:
        name = item.get("name")
        review_id = item.get("review_id")
        baseline = BACKEND / item.get("baseline")
        row = {
            "name": name,
            "review_id": review_id,
            "baseline": str(baseline),
            "status": "skipped",
        }
        if not baseline.exists():
            row["error"] = "baseline_missing"
            reports.append(row)
            continue
        if review_id:
            try:
                review = db.query(Review).filter(Review.id == review_id).first()
            except Exception as exc:
                row["error"] = f"db_unavailable:{exc.__class__.__name__}"
                reports.append(row)
                continue
            if not review:
                row["error"] = "review_row_missing"
                reports.append(row)
                continue
            issues = [issue_row_to_dict(issue) for issue in db.query(Issue).filter(Issue.review_id == review_id).all()]
            if baseline.suffix == ".json":
                data = json.loads(baseline.read_text(encoding="utf-8-sig"))
                anns = [HumanAnnotation(**ann) for ann in data.get("annotations", [])]
            else:
                anns = parse_human_annotation_markdown(baseline.read_text(encoding="utf-8-sig"))
            row["status"] = "scored"
            row["metrics"] = compact_eval(evaluate_against_annotations(issues, anns))
        else:
            row["error"] = "no_review_id"
        reports.append(row)
    db.close()
    payload = {"pdf_hits": find_pdfs(), "documents": reports}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=1), flush=True)


if __name__ == "__main__":
    main()
