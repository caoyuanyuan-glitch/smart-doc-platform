"""Run G99 through _run_review_background and score five channels."""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(os.environ.get("SDP_ROOT", Path(__file__).resolve().parents[1]))
BACKEND = Path(os.environ.get("SDP_BACKEND", ROOT / "backend"))
PDF = ROOT / "g99_eval" / "g99_noannot.pdf"
DB_PATH = ROOT / "g99_eval" / "full_pipeline.db"
OUT = ROOT / "g99_eval" / "full_pipeline_result.json"
ISSUES_OUT = ROOT / "g99_eval" / "full_pipeline.issues.json"


def main():
    sys.path.insert(0, str(BACKEND))
    os.chdir(str(BACKEND))
    os.environ["DATABASE_URL"] = "sqlite:///" + str(DB_PATH)
    os.environ["REVIEW_PDF_VISUAL_VERIFY"] = "1"
    os.environ["REVIEW_VISUAL_PROVIDERS"] = "deepseek"
    os.environ.setdefault("REVIEW_PDF_VISUAL_VERIFY_LIMIT", "6")
    os.environ.setdefault("REVIEW_PDF_VISUAL_VERIFY_LAYOUT_LIMIT", "6")
    os.environ.setdefault("REVIEW_PDF_VISUAL_PAGE_BUDGET", "0")

    from app.database import Base, engine, SessionLocal
    from app.models.document import Document
    from app.models.issue import Issue
    from app.models.review import Review
    from app.models.rule import Rule
    from app.api.review import UPLOAD_DIR, _run_review_background
    from app.utils.document_parser import parse_pdf
    from init_data import init_data
    sys.path.insert(0, str(ROOT / "g99_eval"))
    from eval_common import issue_row_to_dict, load_annotations, score_channels

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    if db.query(Rule).count() == 0:
        init_data()
        db.commit()

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    upload_name = "g99_noannot_full_pipeline.pdf"
    dest = UPLOAD_DIR / upload_name
    if not dest.exists():
        shutil.copyfile(PDF, dest)

    print("parse_pdf start", flush=True)
    content = parse_pdf(str(PDF))
    print(f"parse_pdf chars={len(content)}", flush=True)

    document = Document(
        filename=upload_name,
        file_type="pdf",
        file_size=PDF.stat().st_size,
        content=content,
        status="ready",
        preview=content[:500],
        user_id=1,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    review = Review(document_id=document.id, mode="hybrid", provider="deepseek", status="pending")
    db.add(review)
    db.commit()
    db.refresh(review)
    review_id = review.id
    document_id = document.id
    db.close()

    print(f"run review_id={review_id} document_id={document_id}", flush=True)
    _run_review_background(review_id, document_id, "hybrid", provider="deepseek")

    db = SessionLocal()
    review = db.query(Review).filter(Review.id == review_id).first()
    rows = db.query(Issue).filter(Issue.review_id == review_id).all()
    issues = [issue_row_to_dict(row) for row in rows]
    db.close()

    annotations = load_annotations()
    channels = score_channels(issues, annotations)
    payload = {
        "review_id": review_id,
        "document_id": document_id,
        "status": getattr(review, "status", None),
        "summary": getattr(review, "summary", None),
        "provider_note": (
            "视觉通道使用 DeepSeek；默认 kimi/qwen 凭据不可用。"
            "本结果计入视觉能力，不把不可用 provider 包装成算法提升。"
        ),
        "issue_total": len(issues),
        "channels": channels,
    }
    ISSUES_OUT.write_text(json.dumps(issues, ensure_ascii=False), encoding="utf-8")
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(channels, ensure_ascii=False, indent=1), flush=True)
    print(f"saved {OUT}", flush=True)


if __name__ == "__main__":
    main()
