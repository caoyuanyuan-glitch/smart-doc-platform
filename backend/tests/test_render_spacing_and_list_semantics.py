# -*- coding: utf-8 -*-
"""T7RS R02 园园裁定第二轮：渲染层字符间距 / 列表语义 fewshot / 模板 10b。

2026-11-24 园园裁定：
1. 「54 min/300 bp 文本层带空格但渲染紧贴」是纯文本可判信息（字符坐标就在
   内容流里）——新增 pdf_char_spacing 渲染层通道，报 DET-CN-UNITSPACE。
2. 「有序列表改无序」属写作风格/语义层面 → fewshot 回流（R02 p145 批注）
   + CN 模板 10b 列表语义指令。
"""
import json
import os
import tempfile

import fitz
import pytest

from app.review_engine.fewshot_corpus import select_fewshot_examples
from app.review_engine.pdf_char_spacing import detect_render_tight_units


def _make_pdf(lines: list[str]) -> str:
    """合成 PDF：每行用 helvCID 等基础字体绘制（中文用 fitz 内置 cid 也可省略，
    这里只用 ASCII 保证兼容）。"""
    doc = fitz.open()
    page = doc.new_page()
    y = 72
    for text in lines:
        page.insert_text((72, y), text, fontsize=10)
        y += 20
    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    doc.save(path)
    doc.close()
    return path


class TestRenderTightUnits:
    def test_tight_reported(self):
        pdf = _make_pdf(["wash takes about 54min", "fragments >300bp"])
        try:
            issues = detect_render_tight_units(pdf)
            texts = {i["original_text"] for i in issues}
            assert "54min" in texts
            assert "300bp" in texts
        finally:
            os.unlink(pdf)

    def test_spaced_not_reported(self):
        pdf = _make_pdf(["wash takes about 54 min", "fragments >300 bp"])
        try:
            assert detect_render_tight_units(pdf) == []
        finally:
            os.unlink(pdf)

    def test_page_number_and_fields(self):
        pdf = _make_pdf(["system disk 960GB/SATA"])
        try:
            issues = detect_render_tight_units(pdf)
            assert len(issues) == 1
            it = issues[0]
            assert it["rule"] == "DET-CN-UNITSPACE"
            assert it["source"] == "rule"
            assert it["position"]["page_number"] == 1
            assert "空格" in it["suggestion"]
        finally:
            os.unlink(pdf)

    def test_wide_gap_not_reported(self):
        """内容流紧贴但作者用字符定位拉开了视觉空格 → 不报。"""
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "54", fontsize=10)
        page.insert_text((100, 72), "min", fontsize=10)  # 手工拉开 20pt
        fd, path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        doc.save(path)
        doc.close()
        try:
            assert detect_render_tight_units(path) == []
        finally:
            os.unlink(path)

    def test_missing_file_safe(self):
        assert detect_render_tight_units(r"Z:/no/such/file.pdf") == []

    def test_unit_inside_word_not_reported(self):
        """数字后单位词后面还跟着字母 → 非单位写法，不报。"""
        pdf = _make_pdf(["id 5minutes later"])
        try:
            assert detect_render_tight_units(pdf) == []
        finally:
            os.unlink(pdf)


class TestFewshotListStyle:
    """R02 p145 列表批注回流（人工意见回流工作流）。"""

    def test_anchor_gated_hit(self):
        picked = select_fewshot_examples(
            "如初始dsDNA 文 1. 初始dsDNA 2. 初始dsDNA 求货号"
        )
        codes = [r["label_code"] for r in picked]
        assert "C8" in codes

    def test_irrelevant_chunk_clean(self):
        assert select_fewshot_examples("与列表无关的段落内容") == []

    def test_new_row_wellformed(self):
        from app.review_engine.fewshot_corpus import _FEWSHOT_FILE
        rows = [json.loads(l) for l in open(_FEWSHOT_FILE, encoding="utf-8") if l.strip()]
        hits = [
            r for r in rows
            if r.get("doc") == "H-020-001408-00" and r.get("page") == "145"
            and "无序列表" in r.get("comment", "")
        ]
        assert len(hits) == 1
        assert hits[0]["anchor"] == "初始dsDNA"


class TestCnTemplateListRule:
    def test_template_has_list_semantics_rule(self):
        from app.api import review_rules
        src = review_rules.SYSTEM_PROMPT_TEMPLATE
        assert "10b" in src and "无序列表" in src


class TestR001ColonGuard:
    """R001 防小数守卫收窄到紧邻 2 字符（T7RS p113「界面:」后方 40 字符内
    有 IP "192.168" 被整条跳过的漏报修复）。"""

    def _skip(self, content, pattern):
        import re
        from types import SimpleNamespace
        from app.api.review import _should_skip_rule_match
        rule = SimpleNamespace(rule_no="R001")
        m = re.search(pattern, content)
        assert m
        return _should_skip_rule_match(rule, m, content, "cn", "pdf")

    def test_zhims_colon_not_skipped(self):
        content = (
            "1. 打开Chrome 浏览器，输入下述IP 地址，按【Enter】键，"
            "进入ZLIMS 登录界面:\n\n192.168.100.50"
        )
        assert self._skip(content, r"界面:") is False

    def test_decimal_still_skipped(self):
        assert self._skip("用量为 3.5 mL 时，请确认。其余说明文字若干。", r"(?<=3)\.(?=5)") is True

    def test_ip_still_skipped(self):
        assert self._skip("请输入 192.168.100.50 地址进入系统。", r"(?<=192)\.(?=168)") is True
