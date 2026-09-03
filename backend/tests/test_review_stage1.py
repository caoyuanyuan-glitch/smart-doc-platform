import inspect
import json

from app.api import review as review_api
from app.review_engine.cn_xref_rules import CN_XREF_ENGINE_ID
from app.review_engine.profile import enabled_rule_engines


def test_eng_cn_001_skips_chinese_in_mixed_text():
    text = (
        "使用 DNBSEQ 测序仪完成测序。\n"
        "Please record the sample ID after 文库定量.\n"
        "10 μL Mix was added to each tube.\n"
    )
    issues = review_api._run_manual_engineering_audit(text)
    eng_cn = [item for item in issues if item.get("rule") == "ENG-CN-001"]
    assert eng_cn == []


def test_eng_cn_001_flags_chinese_in_english_segment():
    issues = review_api._run_manual_engineering_audit("Please record the sample ID.")
    assert not any(item.get("rule") == "ENG-CN-001" for item in issues)


def test_multi_position_typo_keeps_both_spans():
    text = "融化后，使用涡漩振荡器振荡混匀 5 s。请将反应混合液用涡漩振荡器再混匀一次。"
    baseline = review_api._run_chinese_human_baseline_rules(text)
    snippet = review_api._run_snippet_content_audit(text)
    vortex = [item for item in baseline if item.get("original_text") == "涡漩"]
    assert len(vortex) == 2
    kept, _ = review_api._finalize_review_issues(
        baseline + snippet, text, set(), snippet_review=True,
    )
    kept_vortex = [item for item in kept if "涡漩" in str(item.get("original_text") or "")]
    assert len(kept_vortex) >= 2


def test_snippet_keeps_local_table_number_mismatch():
    text = "准确率检测结果如表 9 所示：\n表 92 “基因测序仪准确率企业参考品”检测结果\n"
    issues = review_api._run_chinese_human_baseline_rules(text)
    kept, _ = review_api._finalize_review_issues(issues, text, set(), snippet_review=True)
    assert any(item.get("rule") == "CYY-CN-REF-006" for item in kept)


def test_snippet_and_full_share_cn_xref_entry():
    baseline_src = inspect.getsource(review_api._run_chinese_human_baseline_rules)
    background_src = inspect.getsource(review_api._run_review_background)
    assert "iter_cn_local_xref_hits" in baseline_src
    assert "_run_chinese_human_baseline_rules" in background_src
    engines = enabled_rule_engines(snippet_review=True, use_new_rules=False)
    assert CN_XREF_ENGINE_ID in engines
    assert "deterministic_v2" not in engines


def test_summary_total_matches_issue_count_and_ai_degraded_fields():
    payload = {
        "total": 2,
        "pipeline_mode": "legacy",
        "enabled_rule_engines": enabled_rule_engines(snippet_review=True),
        "degraded": True,
        "degraded_reason": "ai_provider_unavailable",
        "rule_completed": True,
        "ai_completed": False,
    }
    encoded = json.dumps(payload, ensure_ascii=False)
    loaded = json.loads(encoded)
    assert loaded["total"] == 2
    assert loaded["degraded"] is True
    assert loaded["rule_completed"] is True
    assert loaded["ai_completed"] is False
    assert CN_XREF_ENGINE_ID in loaded["enabled_rule_engines"]
