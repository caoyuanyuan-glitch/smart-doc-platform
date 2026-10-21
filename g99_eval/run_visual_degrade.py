"""G99 视觉降级口径：复用规则链 issue，强制 provider 不可用。"""
import json
import os
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

ROOT = Path("/workspace")
BACKEND = ROOT / "backend"
PDF = ROOT / "g99_eval" / "g99_noannot.pdf"
GOLD = BACKEND / "goldset" / "human_baseline_DNBSEQ-G99RS&DNBSEQ-G99ARSSystemGuide(StandardMPS2.0)_V9.0_R01Lijuan.json"
ISSUES_PATH = ROOT / "g99_eval" / "ab_p1.db.issues.json"
OUT = ROOT / "g99_eval" / "ab_visual_degrade.json"

LAYOUT_PAGES = {69, 70, 76, 79, 90, 158, 159, 213}


def main():
    sys.path.insert(0, str(BACKEND))
    os.environ.setdefault("DATABASE_URL", "sqlite:////workspace/g99_eval/ab_p1.db")
    os.environ["REVIEW_PDF_VISUAL_VERIFY"] = "1"

    import fitz
    from app.api import review as R
    from app.review_engine.annotation_baseline import HumanAnnotation, evaluate_against_annotations

    R._visual_provider_available = lambda provider: False
    R._get_document_upload_path = lambda document: PDF

    issues = json.loads(ISSUES_PATH.read_text(encoding="utf-8"))
    doc = fitz.open(PDF)
    pages = [p.get_text() for p in doc]
    content = "\f".join(pages)
    doc.close()

    document = SimpleNamespace(file_type="pdf", filename=PDF.name, id=0)
    page_metadata = R._extract_pdf_page_metadata(document, content)
    suspicious = R._collect_pdf_suspicious_pages(page_metadata)
    merged, diagnostics = R._apply_pdf_visual_verification(
        review_id=0,
        document=document,
        content=content,
        issues=list(issues),
        suspicious_pages=suspicious,
    )

    candidate_pages = sorted({
        int(item.get("page_number") or 0)
        for item in (suspicious.get("candidates") or [])
        if int(item.get("page_number") or 0) > 0
    })
    visual_issues = [item for item in merged if str(item.get("rule") or "") == "PDF-VISUAL-001"]
    visual_pages = sorted({
        int((item.get("chapter") or "").replace("第", "").replace("页", "") or 0)
        for item in visual_issues
    })

    anns = [HumanAnnotation(**item) for item in json.loads(GOLD.read_text(encoding="utf-8-sig")).get("annotations", [])]
    res = evaluate_against_annotations(merged, anns)
    payload = {
        "issue_total": res["issue_total"],
        "human_total": res["human_total"],
        "recall": res["recall"],
        "precision": res["precision"],
        "strict_recall": res["strict_recall"],
        "strict_precision": res["strict_precision"],
        "strict_matched": res["strict_matched"],
        "strict_missed": res["strict_missed"],
        "matched": res["matched"],
        "pdf_visual_001_count": len(visual_issues),
        "pdf_visual_001_pages": visual_pages,
        "suspicious_candidate_count": suspicious.get("candidate_count"),
        "layout_gold_pages_in_candidates": sorted(LAYOUT_PAGES.intersection(candidate_pages)),
        "layout_gold_pages_missing_from_candidates": sorted(LAYOUT_PAGES.difference(candidate_pages)),
        "diagnostics_reason": diagnostics.get("reason"),
        "diagnostics_page_issue_count": diagnostics.get("page_issue_count"),
        "diagnostics_page_candidate_count": diagnostics.get("page_candidate_count"),
        "by_rule": dict(Counter(str(item.get("rule")) for item in merged).most_common(20)),
        "strict_misses": [
            {
                "page": item.get("page"),
                "category": item.get("category"),
                "expected_rule": item.get("expected_rule"),
                "comment": item.get("comment"),
            }
            for item in res["strict_misses"]
        ],
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(
        f"strict_recall={res['strict_recall']} strict_matched={res['strict_matched']}/{res['human_total']} "
        f"visual_issues={len(visual_issues)} reason={diagnostics.get('reason')}"
    )
    print("layout in candidates", payload["layout_gold_pages_in_candidates"])
    print("layout missing", payload["layout_gold_pages_missing_from_candidates"])
    print("visual pages", visual_pages)
    print(f"saved {OUT}")


if __name__ == "__main__":
    main()
