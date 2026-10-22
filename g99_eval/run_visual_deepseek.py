"""G99 视觉通道：DeepSeek 复核规则链 issue + 分层疑点页。"""
import json
import os
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(os.environ.get("SDP_ROOT", Path(__file__).resolve().parents[1]))
BACKEND = Path(os.environ.get("SDP_BACKEND", ROOT / "backend"))
PDF = ROOT / "g99_eval" / "g99_noannot.pdf"
GOLD = BACKEND / "goldset" / "human_baseline_DNBSEQ-G99RS&DNBSEQ-G99ARSSystemGuide(StandardMPS2.0)_V9.0_R01Lijuan.json"
ISSUES_PATH = ROOT / "g99_eval" / "ab_p1.db.issues.json"
OUT = ROOT / "g99_eval" / "ab_visual_deepseek.json"

LAYOUT_PAGES = {69, 70, 76, 79, 90, 158, 159, 213}


def main():
    sys.path.insert(0, str(BACKEND))
    os.chdir(str(BACKEND))
    os.environ.setdefault("DATABASE_URL", "sqlite:///" + str(ROOT / "g99_eval" / "ab_p1.db"))
    os.environ["REVIEW_PDF_VISUAL_VERIFY"] = "1"
    os.environ["REVIEW_VISUAL_PROVIDERS"] = "deepseek"
    os.environ.setdefault("REVIEW_PDF_VISUAL_VERIFY_LAYOUT_LIMIT", "168")

    import fitz
    from app.api import review as R
    from app.review_engine.annotation_baseline import HumanAnnotation, evaluate_against_annotations
    from app.review_engine.visual import visual_provider_chain

    R._get_document_upload_path = lambda document: PDF
    R.set_progress = lambda *args, **kwargs: print(f"[progress] {args} {kwargs}", flush=True)

    print("visual_chain", visual_provider_chain(), "deepseek", R._visual_provider_available("deepseek"), flush=True)

    issues = json.loads(ISSUES_PATH.read_text(encoding="utf-8"))
    doc = fitz.open(PDF)
    pages = [p.get_text() for p in doc]
    content = "\f".join(pages)
    doc.close()
    filled = R._backfill_issue_page_numbers(issues, content)
    print(f"page_backfill={filled}", flush=True)

    document = SimpleNamespace(file_type="pdf", filename=PDF.name, id=0)
    page_metadata = R._extract_pdf_page_metadata(document, content)
    suspicious = R._collect_pdf_suspicious_pages(page_metadata)
    layout_limit = R._review_pdf_visual_verify_layout_limit()
    picked = R._select_visual_page_candidates(
        suspicious.get("candidates") or [],
        layout_limit,
        int(page_metadata.get("page_count") or 0),
    )
    picked_pages = {int(item.get("page_number") or 0) for item in picked}
    print(
        f"layout_limit={layout_limit} picked={len(picked_pages)} "
        f"picked_gold={sorted(LAYOUT_PAGES & picked_pages)}",
        flush=True,
    )
    print(
        f"rule_issues={len(issues)} suspicious={suspicious.get('candidate_count')} "
        f"pages={page_metadata.get('page_count')}",
        flush=True,
    )

    merged, diagnostics = R._apply_pdf_visual_verification(
        review_id=0,
        document=document,
        content=content,
        issues=list(issues),
        suspicious_pages=suspicious,
    )

    visual_issues = [item for item in merged if str(item.get("rule") or "") == "PDF-VISUAL-001"]
    visual_pages = []
    for item in visual_issues:
        chapter = str(item.get("chapter") or "")
        page = chapter.replace("第", "").replace("页", "")
        visual_pages.append(int(page or 0))

    anns = [HumanAnnotation(**item) for item in json.loads(GOLD.read_text(encoding="utf-8-sig")).get("annotations", [])]
    res = evaluate_against_annotations(merged, anns)
    compact_items = []
    for item in diagnostics.get("items") or []:
        compact_items.append({
            "page_number": item.get("page_number"),
            "decision": item.get("decision"),
            "reason": str(item.get("reason") or "")[:180],
            "visual_status": item.get("visual_status"),
            "page_candidate": item.get("page_candidate"),
            "candidate_reasons": item.get("candidate_reasons"),
            "provider": item.get("provider"),
        })

    payload = {
        "issue_total": res["issue_total"],
        "human_total": res["human_total"],
        "recall": res["recall"],
        "precision": res["precision"],
        "strict_recall": res["strict_recall"],
        "strict_precision": res["strict_precision"],
        "manual_issue_count": res["manual_issue_count"],
        "manual_review_ratio": res["manual_review_ratio"],
        "strict_matched": res["strict_matched"],
        "strict_missed": res["strict_missed"],
        "matched": res["matched"],
        "pdf_visual_001_count": len(visual_issues),
        "pdf_visual_001_pages": visual_pages,
        "diagnostics_reason": diagnostics.get("reason"),
        "diagnostics_confirmed": diagnostics.get("confirmed_count"),
        "diagnostics_rejected": diagnostics.get("rejected_count"),
        "diagnostics_uncertain": diagnostics.get("uncertain_count"),
        "diagnostics_skipped": diagnostics.get("skipped_count"),
        "diagnostics_page_candidate_count": diagnostics.get("page_candidate_count"),
        "diagnostics_page_issue_count": diagnostics.get("page_issue_count"),
        "layout_gold_confirmed": sorted(
            LAYOUT_PAGES.intersection({int(item.get("page_number") or 0) for item in compact_items if item.get("decision") == "confirm"})
        ),
        "items": compact_items,
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
        f"visual_issues={len(visual_issues)} confirmed={diagnostics.get('confirmed_count')} "
        f"rejected={diagnostics.get('rejected_count')}",
        flush=True,
    )
    print("visual pages", visual_pages, flush=True)
    print("layout gold confirmed", payload["layout_gold_confirmed"], flush=True)
    print(f"saved {OUT}", flush=True)


if __name__ == "__main__":
    main()
