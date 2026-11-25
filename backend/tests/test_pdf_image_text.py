# -*- coding: utf-8 -*-
"""图内文字提取通路测试（园园 2026-11-24 裁定：截图/流程图内文字应可识别）。

覆盖：diff 归一化/独有行筛选、图片型页面挑选、无 key 零成本降级、
mock VL 提取全链路拼接。真实 VL 调用待园园补 key 后人工验证。
"""
import os
import tempfile

import fitz
import pytest

from app.review_engine import pdf_image_text
from app.review_engine.pdf_image_text import (
    _diff_image_only_lines,
    _norm_line,
    augment_pdf_image_text,
    select_image_pages,
)


def _png_bytes(w=80, h=60, value=120) -> bytes:
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, w, h))
    pix.clear_with(value)
    return pix.tobytes("png")


def _pdf_with_image_page() -> str:
    """p1 = 大图页（图占 80% 面积），p2 = 纯文本页。"""
    doc = fitz.open()
    page1 = doc.new_page()
    img = _png_bytes()
    page1.insert_image(fitz.Rect(36, 36, 540, 760), stream=img)  # 占满页
    page2 = doc.new_page()
    page2.insert_text((72, 72), "plain text page only", fontsize=10)
    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    doc.save(path)
    doc.close()
    return path


class TestNormLine:
    def test_space_and_case_insensitive(self):
        assert _norm_line("Wash Buffer  Add") == _norm_line("wash buffer add")

    def test_nfkc_fullwidth(self):
        assert _norm_line("ＰＣＲ管") == _norm_line("PCR管")


class TestDiffImageOnlyLines:
    def test_image_only_kept(self):
        # 子串口径：VLM 行是文本层行的子串 → 正文已有，丢弃（图内"Workspace"
        # 而正文有"Workspace 完整拼写"时不重复报）；图内独有词保留
        kept = _diff_image_only_lines("Workspace\nFaceID", "Workspace 完整拼写")
        assert kept == ["FaceID"]
        kept2 = _diff_image_only_lines("Workpace", "Wash Buffer 添加")
        assert kept2 == ["Workpace"]

    def test_text_layer_dup_dropped(self):
        kept = _diff_image_only_lines("测序运行\nStop Sequencing Run", "测序运行 开始")
        assert kept == ["Stop Sequencing Run"]

    def test_single_char_noise_dropped(self):
        assert _diff_image_only_lines("a\n1\nOK", "") == ["OK"]

    def test_duplicate_vlm_lines_dedup(self):
        assert _diff_image_only_lines("FlowChart\nFlowChart", "") == ["FlowChart"]


class TestSelectImagePages:
    def test_image_page_selected_text_page_not(self):
        path = _pdf_with_image_page()
        try:
            doc = fitz.open(path)
            pages = select_image_pages(doc, limit=10, min_ratio=0.15)
            doc.close()
            assert pages == [1]
        finally:
            os.unlink(path)

    def test_limit_respected(self):
        path = _pdf_with_image_page()
        try:
            doc = fitz.open(path)
            pages = select_image_pages(doc, limit=0, min_ratio=0.15)
            doc.close()
            assert pages == []
        finally:
            os.unlink(path)


class TestAugmentNoKey:
    def test_disabled_by_env(self, monkeypatch):
        monkeypatch.setenv("REVIEW_PDF_IMAGE_TEXT_EXTRACT", "0")
        text, diag = augment_pdf_image_text("Z:/no/such.pdf")
        assert text == "" and diag["status"] == "disabled"

    def test_unavailable_provider_short_circuits(self, monkeypatch):
        """无视觉 key：第一次调用即 unavailable，直接返回空串不继续烧页。"""
        path = _pdf_with_image_page()
        try:
            monkeypatch.setenv("REVIEW_PDF_IMAGE_TEXT_EXTRACT", "1")

            class FakeClient:
                def extract_page_text_from_image(self, png, **kw):
                    return {"status": "unavailable", "reason": "kimi_unavailable", "text": ""}

            import app.utils.ai_client as mod
            monkeypatch.setattr(mod, "ai_client", FakeClient())
            text, diag = augment_pdf_image_text(path)
            assert text == ""
            assert diag["status"] == "kimi_unavailable"
            assert diag["pages_selected"] == [1]
        finally:
            os.unlink(path)


class TestAugmentMockExtraction:
    def test_full_pipeline_appends_page_sections(self, monkeypatch):
        path = _pdf_with_image_page()
        try:
            monkeypatch.setenv("REVIEW_PDF_IMAGE_TEXT_EXTRACT", "1")

            class FakeClient:
                def extract_page_text_from_image(self, png, page_number=None, **kw):
                    # p1 是纯图页（无文本层），VLM 读出图内文字
                    if page_number == 1:
                        return {"status": "ok", "text": "Workpace 工作区"}
                    return {"status": "unavailable", "reason": "no_provider", "text": ""}

            import app.utils.ai_client as mod
            monkeypatch.setattr(mod, "ai_client", FakeClient())
            text, diag = augment_pdf_image_text(path)
            assert diag["status"] == "ok"
            assert diag["pages_extracted"] == [1]
            assert diag["image_only_lines"] == 1
            assert "【第 1 页 图片内文字" in text
            assert "Workpace 工作区" in text
        finally:
            os.unlink(path)


class TestReviewWiring:
    def test_review_py_calls_augment(self):
        import inspect
        from app.api import review
        src = inspect.getsource(review)
        assert "augment_pdf_image_text" in src
