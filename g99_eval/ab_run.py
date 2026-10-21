"""G99 严格评测：去批注 PDF + 当前 backend 规则链 + goldset。

由附件 `_ab_run.py` 改到本机路径。只跑当前代码（p1），不切基线副本。
"""
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path("/workspace")
BACKEND = ROOT / "backend"
PDF = ROOT / "g99_eval" / "g99_noannot.pdf"
GOLD = BACKEND / "goldset" / "human_baseline_DNBSEQ-G99RS&DNBSEQ-G99ARSSystemGuide(StandardMPS2.0)_V9.0_R01Lijuan.json"
OUT = ROOT / "g99_eval" / "ab_result.json"
DB_PATH = ROOT / "g99_eval" / "ab_p1.db"
ISSUES_PATH = Path(str(DB_PATH) + ".issues.json")


def run_variant():
    env = dict(os.environ)
    env["AB_BACKEND"] = str(BACKEND)
    env["AB_DB"] = str(DB_PATH)
    env["AB_PDF"] = str(PDF)
    env["PYTHONIOENCODING"] = "utf-8"
    env["REVIEW_PDF_VISUAL_VERIFY"] = "0"
    env["DATABASE_URL"] = "sqlite:///" + str(DB_PATH)
    code = r'''
import os, sys, json
sys.path.insert(0, os.environ["AB_BACKEND"])
os.environ["DATABASE_URL"] = "sqlite:///" + os.environ["AB_DB"]
os.environ.setdefault("REVIEW_PDF_VISUAL_VERIFY", "0")
import fitz
doc = fitz.open(os.environ["AB_PDF"])
pages = [p.get_text() for p in doc]
content = "\f".join(pages)
doc.close()
print("PAGES", len(pages), "CHARS", len(content), flush=True)
from app.database import Base, engine, SessionLocal
import app.models.document, app.models.rule  # noqa
Base.metadata.create_all(bind=engine)
from app.models.rule import Rule
from init_data import init_data
db = SessionLocal()
if db.query(Rule).count() == 0:
    init_data()
    db.commit()
from app.api import review as R
from app.crud.rule import get_rules
from app.crud.term import get_terms
rules = get_rules(db)
terms = get_terms(db)
issues = []
issues += R.run_rule_audit(content, rules, None, "pdf")
print("after rule_audit", len(issues), flush=True)
issues += R.run_term_check(content, terms)
print("after term_check", len(issues), flush=True)
issues += R.run_spelling_and_grammar_check(content, "pdf")
print("after spelling", len(issues), flush=True)
issues += R._run_english_heuristic_audit(content, "pdf")
print("after heuristic", len(issues), flush=True)
issues += R._run_manual_engineering_audit(content, "pdf")
print("after engineering", len(issues), flush=True)
issues += R._run_pdf_structure_audit(content)
print("after pdf_structure", len(issues), flush=True)
issues += R._run_reference_and_term_consistency_audit(db, content)
print("after reference", len(issues), flush=True)
issues += R._run_logic_integrity_audit(content)
print("after logic", len(issues), flush=True)
issues += R._run_safety_compliance_audit(content, "en")
print("after safety", len(issues), flush=True)
issues += R._run_cross_reference_audit(content)
print("after xref", len(issues), flush=True)
filled = R._backfill_issue_page_numbers(issues, content)
print("after page_backfill", filled, flush=True)
db.close()
out = os.environ["AB_DB"] + ".issues.json"
json.dump(issues, open(out, "w", encoding="utf-8"), ensure_ascii=False)
print("ISSUES", len(issues), flush=True)
'''
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=str(BACKEND),
    )
    print(result.stdout)
    if result.returncode != 0 or not ISSUES_PATH.exists():
        print(result.stderr, file=sys.stderr)
        raise SystemExit(f"variant failed rc={result.returncode}")
    issues = json.loads(ISSUES_PATH.read_text(encoding="utf-8"))
    print(f"[p1] issues={len(issues)}")
    return issues


def score(issues):
    sys.path.insert(0, str(BACKEND))
    from app.review_engine.annotation_baseline import (
        HumanAnnotation,
        evaluate_against_annotations,
    )
    data = json.loads(GOLD.read_text(encoding="utf-8-sig"))
    anns = [HumanAnnotation(**item) for item in data.get("annotations", [])]
    return evaluate_against_annotations(issues, anns), anns


def main():
    if not PDF.exists():
        raise SystemExit(f"missing PDF: {PDF}")
    issues = run_variant()
    res, anns = score(issues)
    payload = {
        "issue_total": res["issue_total"],
        "human_total": res["human_total"],
        "recall": res["recall"],
        "precision": res["precision"],
        "f1": res["f1"],
        "strict_recall": res["strict_recall"],
        "strict_precision": res["strict_precision"],
        "strict_f1": res["strict_f1"],
        "strict_matched": res["strict_matched"],
        "strict_missed": res["strict_missed"],
        "matched": res["matched"],
        "unmatched_issue_count": res["unmatched_issue_count"],
        "strict_unmatched_issue_count": res["strict_unmatched_issue_count"],
        "by_rule": dict(Counter(str(item.get("rule")) for item in issues).most_common()),
        "by_category": dict(Counter(str(item.get("category")) for item in issues).most_common()),
        "strict_misses": res["strict_misses"],
    }
    print(
        f"  recall={res['recall']} strict_recall={res['strict_recall']} "
        f"precision={res['precision']} strict_precision={res['strict_precision']} "
        f"issues={res['issue_total']} unmatched={res['unmatched_issue_count']}"
    )
    print(f"  strict_matched={res['strict_matched']}/{res['human_total']}")
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"saved {OUT}")


if __name__ == "__main__":
    main()
