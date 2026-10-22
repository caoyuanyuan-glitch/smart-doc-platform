"""F12：ENG-CN-001 只跳过试剂盒标签式全角冒号，中文残留与正文误用仍上报。"""

import pytest

from app.api import review as review_api

EN = (
    "This user manual describes the sequencing workflow, reagent storage, "
    "instrument maintenance, and sample preparation steps in detail. "
)

LABEL_SNIPPETS = [
    "Cartridge REF：XXX-1",
    "MODEL：XXX XX",
    "EXP：XXXX",
    "Exp：XXXX",
    "Ref：A1",
    "LOT：XXXXX",
    "SN：XXXXXXXXXXXXX",
    "Cat：XXX",
    "Vol：1 mL",
]

REPORT_SNIPPETS = [
    "警告：请勿触摸",
    "操作：打开盖子",
    "Heating：95",
    "Note：Check",
    "at：this node",
    "Status：Ready",
    "Completion at：",
    "WARNING：",
]


def _eng_cn_issues(snippet):
    issues = review_api._run_manual_engineering_audit(EN + snippet, file_type="pdf")
    return [item for item in issues if item.get("rule") == "ENG-CN-001"]


@pytest.mark.parametrize("snippet", LABEL_SNIPPETS)
def test_label_fullwidth_colon_is_skipped(snippet):
    issues = _eng_cn_issues(snippet)
    colon_hits = [item for item in issues if "：" in str(item.get("original_text") or "")]
    assert colon_hits == []


@pytest.mark.parametrize("snippet", REPORT_SNIPPETS)
def test_non_label_fullwidth_colon_is_reported(snippet):
    issues = _eng_cn_issues(snippet)
    assert issues


def test_chinese_residual_count_unchanged():
    content = EN + "警告 打开时有 类激光辐射 避免光束照射 Store reagents at room temperature."
    issues = review_api._run_manual_engineering_audit(content, file_type="pdf")
    residual = [
        item for item in issues
        if item.get("rule") == "ENG-CN-001" and int(item.get("confidence") or 0) == 95
    ]
    assert len(residual) == 4
