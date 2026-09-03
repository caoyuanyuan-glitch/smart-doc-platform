import json
from pathlib import Path

from tests.review_eval_harness import evaluate_all


REQUIRED_FIELDS = {
    "sample_id",
    "review_mode",
    "actual_status",
    "raw_rule_candidates",
    "raw_ai_candidates",
    "final_issues",
    "true_positives",
    "false_positives",
    "false_negatives",
    "duplicates",
    "ai_call_count",
    "elapsed_ms",
    "summary_total",
    "issues_total",
}


def test_review_eval_baseline_emits_required_fields(tmp_path):
    report = evaluate_all("snippet:rule")
    assert report["samples"], "fixed eval samples must exist"
    for row in report["samples"]:
        missing = REQUIRED_FIELDS - set(row)
        assert not missing, missing
        assert row["summary_total"] == row["issues_total"]
        assert row["actual_status"] == "completed"

    (Path(tmp_path) / "baseline_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    totals = report["totals"]
    print(
        "BASELINE",
        f"P={totals['precision']}",
        f"R={totals['recall']}",
        f"F1={totals['f1']}",
        f"TP={totals['true_positives']}",
        f"FP={totals['false_positives']}",
        f"FN={totals['false_negatives']}",
        f"ms={totals['elapsed_ms']}",
    )
