# -*- coding: utf-8 -*-
"""T7RS R02 人工批注差距驱动的修复验证（2026-11-24）。

覆盖三个新模块/改动：
1. ai_suggestion_anchor.should_drop_minority_target_issue —— AI 建议方向锚定守卫
2. cn_format_consistency.check_tight_degree_unit —— 多单位混合使用口径
3. ruled_false_positives.is_ruled_t7rs_table_concat —— 表格拼接伪影 3b
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.review_engine.ai_suggestion_anchor import should_drop_minority_target_issue
from app.review_engine.cn_format_consistency import check_tight_degree_unit
from app.review_engine.ruled_false_positives import should_drop_ruled_fp


# ── 1. AI 建议方向锚定守卫 ─────────────────────────────────────────
def _ai(cat, ot, sg):
    return {"source": "ai", "rule": "", "category": cat,
            "original_text": ot, "suggestion": sg, "description": "", "context": ""}


DOC = "全文使用阔口吸头。" * 3 + "DualBarcode 支持拆分。" * 3 + "试剂槽上盖请对齐。" * 3


def test_anchor_drops_absent_target_cjk():
    # 宽口吸头全文 0 处，阔口吸头 ≥2 处 → 拦
    assert should_drop_minority_target_issue(_ai("术语一致性", "阔口吸头", "宽口吸头"), DOC)


def test_anchor_drops_spacing_only_minority():
    # DualBarcode（紧贴 3 处）→ Dual Barcode（带空格 0 处）→ 拦
    assert should_drop_minority_target_issue(
        _ai("术语一致性", "DualBarcode", "Dual Barcode"),
        "DualBarcode 支持。" * 3,
    )


def test_anchor_keeps_majority_spacing_fix():
    # 原文少数派（紧贴 1 处）、建议为多数派写法 → 不拦（真问题）
    assert not should_drop_minority_target_issue(
        _ai("术语一致性", "手工制备DNB", "手工制备 DNB"),
        "手工制备 DNB 步骤。" * 3 + "手工制备DNB 一次。",
    )


def test_anchor_keeps_generic_word_replace():
    # 「文件→类型」通用词，且两者都高频存在 → 不拦
    doc = "选择的文件" * 3 + "选择的类型" * 3
    assert not should_drop_minority_target_issue(
        _ai("术语一致性", "测序时选择的Barcode 文件", "测序时选择的Barcode 类型"), doc)


def test_anchor_keeps_single_occurrence_typo():
    # ���文仅 1 处（多数派未确立），即使目标形式 0 处也不拦（保护真错）
    assert not should_drop_minority_target_issue(
        _ai("术语一致性", "Qubit ssDNA #1standard", "Qubit ssDNA #1 standard"),
        "Qubit ssDNA #1standard 出现一次。",
    )


def test_anchor_ignores_rephrase_categories():
    # 可读性/语法类是改写不是统一写法，不参与计数比较
    assert not should_drop_minority_target_issue(
        _ai("可读性", "阔口吸头", "宽口吸头"), DOC)


def test_anchor_ignores_rule_source():
    it = _ai("术语一致性", "阔口吸头", "宽口吸头")
    it["source"] = "rule"
    assert not should_drop_minority_target_issue(it, DOC)


# ── 2. DET-CN-UNITSPACE 多单位混合使用 ─────────────────────────────
def test_unitspace_mixed_usage_fires():
    # GB 紧贴 2 处 + 带空格 1 处 = 混用 → 报紧贴（Tina p41 裁定口径）
    text = "容量 0GB 与 8TB 备选，另有 1 GB 缓存。" + "常规内容。" * 5
    issues = check_tight_degree_unit(text)
    assert any(i["original_text"] == "0GB" for i in issues)
    assert any(i["original_text"] == "8TB" for i in issues)


def test_unitspace_uniform_tight_silent():
    # 全文一致紧贴 → 不报（风格统一）
    text = "容量 0GB 与 8TB 备选，缓存 1GB。" + "常规内容。" * 5
    assert not any(i["original_text"].endswith("GB") or i["original_text"].endswith("TB")
                   for i in check_tight_degree_unit(text) if "GB" in i["original_text"] or "TB" in i["original_text"])


def test_unitspace_degree_still_fires():
    text = "温度 2℃~8℃ 存储，其他 2 ℃ 环境。" + "常规内容。" * 5
    issues = check_tight_degree_unit(text)
    assert any(i["original_text"] == "2℃" for i in issues)


def test_unitspace_min_bp_covered():
    text = "读取 54min，片段 300bp，另有 60 min 与 500 bp。" + "常规内容。" * 5
    issues = check_tight_degree_unit(text)
    texts = [i["original_text"] for i in issues]
    assert "54min" in texts and "300bp" in texts


# ── 3. 表格拼接伪影 3b ─────────────────────────────────────────────
def _mk(**kw):
    base = {"source": "ai", "rule": "", "category": "格式排版", "description": "",
            "context": "", "original_text": "", "suggestion": ""}
    base.update(kw)
    return base


def test_t7rs_concat_spacing_insert_dropped():
    it = _mk(original_text="dsDNA 文库类型转换酶用量（μL）",
             suggestion="dsDNA 文库类型 转换酶用量（μL）")
    assert should_drop_ruled_fp(it, "dsDNA 文库类型转换酶用量（μL）")


def test_t7rs_concat_spacing_demand_dropped():
    it = _mk(original_text="产品货号产品名称产品型号版本文库类型理论产出数据量 （Gb/载片）",
             suggestion="表头各列之间应有分隔，且数据行应与表头列对应")
    assert should_drop_ruled_fp(it, "x")


def test_t7rs_concat_struct_defect_kept():
    it = _mk(original_text="产品货号产品名称产品型号版本文库类型理论产出数据量 （Gb/载片）",
             suggestion="表头各列之间应有分隔",
             description="表头缺失一列，结构不完整")
    assert not should_drop_ruled_fp(it, "x")


def test_t7rs_concat_unrelated_text_kept():
    it = _mk(original_text="按照实验室按要求及当地的法律法规要求处理废液",
             suggestion="按照实验室要求及当地法律法规要求处理废液")
    assert not should_drop_ruled_fp(it, "x")
