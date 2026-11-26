"""compare-audit 模式分流回归：both 保持原行为，bilingual 产出中英对照问题。"""

from app.api.review import (
    COMPARE_ALLOWED_MODES,
    _build_compare_audit_payload,
    _build_compare_issue_payloads,
)

CN_TEXT = "图 1 简介\n警告: 请勿混用\n图 2 操作步骤\n1. 加入 400 μL 试剂\n表 1 参数"
EN_TEXT = "Figure 1 Introduction\n2 Procedure\n1. Add 400 uL reagent\nTable 1 Parameters"


def _docs():
    return (
        {"filename": "cn.pdf", "text": CN_TEXT, "params": [{"name": "产品名称", "value": "试剂套装"}]},
        [{"filename": "en.pdf", "text": EN_TEXT, "params": [{"name": "Product Name", "value": "Reagent Kit"}]}],
    )


def test_allowed_modes_include_bilingual():
    assert COMPARE_ALLOWED_MODES == {"both", "bilingual"}


def test_both_mode_keeps_legacy_rows():
    main_doc, refs = _docs()
    payload = _build_compare_audit_payload(main_doc, refs, "both")
    kinds = {row["kind"] for row in payload["compare_rows"]}
    assert {"parameter", "flow"} <= kinds
    assert not any(str(kind).startswith("bilingual_") for kind in kinds)
    assert payload["summary"]["bilingual_row_count"] == 0


def test_bilingual_mode_emits_bilingual_rows_and_language_summary():
    main_doc, refs = _docs()
    payload = _build_compare_audit_payload(main_doc, refs, "bilingual")
    assert payload["summary"]["mode"] == "bilingual"
    assert payload["summary"]["pair_languages"] == {"main": "zh", "references": ["en"]}
    assert payload["summary"]["bilingual_row_count"] == len(payload["compare_rows"])
    assert all(str(row["kind"]).startswith("bilingual_") for row in payload["compare_rows"])


def test_bilingual_issue_payload_has_bidirectional_evidence_and_sync_hint():
    # 直接构造 payload，不触发 LLM——验 issue 映射层，不验语义产出
    payload = {
        "compare_rows": [{
            "dimension": "中英对照", "parameter_name": "警示缺失", "level": "P1",
            "kind": "bilingual_safety", "main_value": "【该侧未检出】",
            "reference_values": [{"filename": "en.pdf", "value": "Do not swallow"}],
            "evidence": "中文第0行: 【该侧未检出】\n英文第12行: Do not swallow",
            "conclusion": "英文有吞咽警示中文无",
        }]
    }
    issues = _build_compare_issue_payloads(review_id=1, compare_payload=payload)
    assert len(issues) == 1
    issue = issues[0]
    assert issue.source == "compare_bilingual"
    assert issue.category == "中英对照"
    assert "双向举证" in issue.context
    assert "中↔英同步" in issue.suggestion
