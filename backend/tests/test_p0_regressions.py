# -*- coding: utf-8 -*-
"""P0 新增能力的回归测试。

覆盖本轮 P0 的四块改动：
  1. parse_pdf 空页占位（页码不失真）
  2. SPELL-TRANS 英文换位拼写检测
  3. REF-STYLE 交叉引用写法规范
  4. DET-SPACE 数值与单位写法/间距一致性
"""
from __future__ import annotations

import json
import os
import sys
import types

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.review_engine.reference_index import check_reference_style  # noqa: E402
from app.review_engine.unit_spacing import (  # noqa: E402
    check_number_unit_spacing,
    check_unit_consistency,
    check_units_and_spacing,
)


# ======================================================================
# 1. parse_pdf 空页占位
# ======================================================================

class _FakePage:
    def __init__(self, text):
        self._text = text

    def get_text(self, *args, **kwargs):
        return self._text


class _FakeDoc:
    def __init__(self, pages):
        self._pages = pages

    def __iter__(self):
        return iter(self._pages)

    def close(self):
        pass


@pytest.fixture()
def parser_module(monkeypatch):
    import app.utils.document_parser as DP
    return DP


def _patch_extract(monkeypatch, DP, page_texts):
    monkeypatch.setattr(
        DP, "extract_pdf",
        lambda path: {"page_texts": list(page_texts), "full_text": "\f".join(page_texts)},
    )


def test_parse_pdf_keeps_empty_page_placeholder(monkeypatch, parser_module, tmp_path):
    """空页必须保留占位，否则后续所有页码整体前移。"""
    DP = parser_module
    # 第 2 页清洗后为空（只有页脚数字被 clean 掉）
    _patch_extract(monkeypatch, DP, ["page one text", "   \n  ", "page three text"])
    monkeypatch.setattr(DP, "_remove_repeated_page_noise", lambda pages: list(pages))
    monkeypatch.setattr(DP, "clean_pdf_text", lambda t: t.strip())

    target = tmp_path / "x.pdf"
    target.write_bytes(b"%PDF-1.4")

    content = DP.parse_pdf(str(target))
    segments = content.split("\f")
    assert len(segments) == 3, "空页被丢弃，分段数会变少"
    assert segments[1].strip() == "", "空页占位应保留为空段"
    assert "page three text" in segments[2]


def test_parse_pdf_page_offset_stable_across_empty_pages(monkeypatch, parser_module, tmp_path):
    """修复后：后段页码不因前段空页而前移。"""
    DP = parser_module
    _patch_extract(monkeypatch, DP, ["a", "b", "", "d", "e"])
    monkeypatch.setattr(DP, "_remove_repeated_page_noise", lambda pages: list(pages))
    monkeypatch.setattr(DP, "clean_pdf_text", lambda t: t.strip())

    target = tmp_path / "y.pdf"
    target.write_bytes(b"%PDF-1.4")
    content = DP.parse_pdf(str(target))

    offset = content.index("e")
    assert content[:offset].count("\f") + 1 == 5, "第 5 段内容应在第 5 页"


# ======================================================================
# 2. SPELL-TRANS 英文换位拼写检测
# ======================================================================

def _install_fake_spell(monkeypatch, module, words):
    """替换模块级全局 spell 对象（生产代码用的是 `spell = SpellChecker(...)`）。

    语义对齐 spellchecker 库：
      unknown(words: list) -> list  返回不在词表中的词
      known(word)        -> set   返回词中字符（spellchecker 库的真实语义）
    """

    class FakeSpell:
        def __init__(self):
            self._words = {w.lower() for w in words}

        def known(self, word):
            return set(str(word).lower())

        def unknown(self, words):
            if isinstance(words, str):
                words = [words]
            return [w for w in words if str(w).lower() not in self._words]

        def __contains__(self, word):
            return str(word).lower() in self._words

    monkeypatch.setattr(module, "spell", FakeSpell(), raising=True)
    return FakeSpell


def test_transposition_spelling_detected(monkeypatch):
    """相邻字母换位拼写错误应被检出。

    判定前提：同一文档内同时存在合法写法（作为内部参照）与错拼写法。
    这里使用真实 spellchecker 词典，不打桩 —— 桩无法复现模块导入时的
    `_load_whitelist_into_dictionary(reset=True)` 重建行为。
    """
    import app.utils.spell_checker as SC
    text = "Status: Idle Sequence. Later the panel shows Status: Ilde Sequence."
    issues = SC.check_spelling(text, file_type="pdf")
    trans = [i for i in issues if str(i.get("rule")) == "SPELL-TRANS"]
    assert trans, "应检出换位拼写错误"
    assert trans[0]["original_text"].lower() == "ilde"
    assert "idle" in (trans[0].get("suggestion") or "").lower()


def test_transposition_not_reported_for_valid_word():
    """正常词不得被误报为换位拼写错误。"""
    import app.utils.spell_checker as SC
    text = "Status: Idle Sequence. Later the panel shows Status: Idle Sequence."
    issues = SC.check_spelling(text, file_type="pdf")
    trans = [i for i in issues if str(i.get("rule")) == "SPELL-TRANS"]
    assert not trans, f"正常词被误报：{[i.get('original_text') for i in trans]}"


def test_transposition_ignores_short_word_gate_only():
    """豁免的只是 PDF 场景的 <=4 字符门槛，其他误报防线仍应生效。"""
    import app.utils.spell_checker as SC
    # `Ilde` 长度 4 —— 修正前会被 PDF 短词门槛整体拦下
    text = "Status: Idle Sequence. Later the panel shows Status: Ilde Sequence."
    issues = SC.check_spelling(text, file_type="pdf")
    assert any(str(i.get("rule")) == "SPELL-TRANS" for i in issues), \
        "长度 4 的换位词应被检出（门槛豁免只针对长度）"


def test_spell_checker_survives_non_iterable_dictionary(monkeypatch):
    """词表对象不支持 `in` 运算时，拼写链路不得整体崩溃。"""
    import app.utils.spell_checker as SC

    class WeirdSpell:
        def known(self, word):
            return True

        def unknown(self, words):
            # 刻意返回非可迭代对象，验证生产代码有 TypeError 容错
            return None

    monkeypatch.setattr(SC, "spell", WeirdSpell(), raising=True)
    issues = SC.check_spelling("Status: Ilde Sequence", file_type="pdf")
    assert isinstance(issues, list)


# ======================================================================
# 3. REF-STYLE 交叉引用写法规范
# ======================================================================

def test_ref_style_detects_table_with_page():
    """`Table N on Page M` 属于写法不规范，应产出 REF-STYLE。"""
    text = "Intro text\fTable 3 Result\r\nvalue\fSee Table 3 on Page 2 for details.\f"
    issues = check_reference_style(text)
    assert issues, "应检出 Table N on Page M 写法"
    issue = issues[0]
    assert issue["rule"] == "REF-STYLE"
    assert "Table 3 on Page 2" in issue["original_text"]
    assert issue["position"], "必须带 position 以便反推页码"


def test_ref_style_position_contains_page():
    """页码必须落在 position JSON 内，而不是顶层字段。"""
    text = "Intro text\fTable 3 Result\r\nvalue\fSee Table 3 on Page 2 for details.\f"
    issues = check_reference_style(text)
    meta = json.loads(issues[0]["position"])
    assert meta.get("page") == 3, f"页码应为 3，实际 {meta.get('page')}"
    assert meta.get("target_page") == 2


def test_ref_style_ignores_plain_reference():
    """不带页码的正常引用不得误报。"""
    text = "Intro text\fTable 3 Result\r\nvalue\fSee Table 3 for details.\f"
    assert not check_reference_style(text)


def test_ref_style_ignores_missing_target():
    """引用目标页越界属引用完整性（REF-001/002），REF-STYLE 不重复上报。"""
    text = "Intro text\fTable 3 Result\r\nvalue\fSee Table 9 on Page 99 for details.\f"
    assert not check_reference_style(text)


def test_ref_style_detects_step_reference_to_table_page():
    """步骤级引用指向表格页（`Make X on Page N`）应被检出。"""
    text = ("Intro\fTable 5 Reagents\r\nBuffer\f"
            "Make DNB reaction mixture 1 on Page 2 and fill it.\f")
    issues = check_reference_style(text)
    assert any(i["rule"] == "REF-STYLE" for i in issues), \
        "指向表格页的步骤级引用应被检出"


def test_ref_style_empty_input():
    assert check_reference_style("") == []
    assert check_reference_style("text", parsed=False) == []


# ======================================================================
# 4. DET-SPACE 数值与单位写法/间距
# ======================================================================

def test_unit_mixed_forms_reported():
    """同一单位多种书写形式并存应被检出。"""
    text = "Add 100 μL of buffer. Then add 100 uL of buffer."
    issues = check_unit_consistency(text)
    assert issues, "μL / uL 混用应被检出"
    assert issues[0]["rule"] == "DET-SPACE-UNIT"


def test_unit_single_form_not_reported():
    """全文只有一种写法时不得上报。"""
    text = "Add 100 μL of buffer. Then add 200 μL of buffer."
    assert not check_unit_consistency(text)


def test_temperature_code_point_mix_reported():
    """`℃`(U+2103) 与 `°C` 码位不同，混用应被检出。"""
    text = "Incubate at 95 ℃ then 95 °C for 5 min."
    issues = check_unit_consistency(text)
    assert issues, "温度单位码位混用应被检出"
    assert issues[0]["rule"] == "DET-SPACE-UNIT"


def test_temperature_single_code_point_not_reported():
    """只有一种温度写法时不得上报。"""
    text = "Incubate at 95 ℃ then 70 ℃ for 5 min."
    assert not check_unit_consistency(text)


def test_number_unit_spacing_uses_document_baseline():
    """多数写法带空格时，紧贴写法才上报。"""
    text = ("Add 10 mL of A, 20 mL of B, 30 mL of C, 40 mL of D, 50 mL of E, "
            "then 5mL of F.")
    issues = check_number_unit_spacing(text)
    assert issues, "少数派紧贴写法应被检出"
    assert issues[0]["rule"] == "DET-SPACE-GAP"


def test_number_unit_spacing_respects_document_style():
    """全文一律紧贴（既定风格）时不得上报。"""
    text = "Add 10mL of A, 20mL of B, 30mL of C, 40mL of D."
    assert not check_number_unit_spacing(text)


def test_units_and_spacing_entry():
    text = "Add 100 μL then 100 uL. Also 10 mL and 20 mL and 30 mL and 40 mL and 5mL."
    issues = check_units_and_spacing(text)
    assert isinstance(issues, list)
    assert any(i["rule"].startswith("DET-SPACE") for i in issues)
