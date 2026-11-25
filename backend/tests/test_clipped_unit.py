# -*- coding: utf-8 -*-
"""园园 2026-11-24 裁定：T7RS R02 #15/#16 不是「mL 缺空格」，而是可见文字少了 L。

证据链：
1. Tina 批注 p180/p181 comment='mL'，框内='m' → 把「1.8 m」改成「1.8 mL」；
2. 渲染页 P5 行显示「1.8 m」，P1–P4 均「1.8 mL」；
3. PDF 内容流含 L，但被裁剪未渲染；平台解析器 flags=2 读到「1.8 mL」，
   默认提取读到「1.8 m」——文本层规则看不到，必须走渲染层比对。

覆盖：
- 文本层 DET-CN-UNITTRUNC（无裁剪字符的文档，多数写法锚定 + 米单位防误报）
- 渲染层 pdf_clipped_unit._scan_page / detect_clipped_unit_chars（真实 fixture PDF）
- review.py 接线（此前有 dispatcher 替换失败导致规则没挂上的教训）
"""
from pathlib import Path

import pytest

from app.review_engine.cn_format_consistency import (
    check_cn_format_consistency,
    check_truncated_ml_unit,
)
from app.review_engine.pdf_clipped_unit import (
    _char_key,
    _scan_page,
    detect_clipped_unit_chars,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PDF = BACKEND_ROOT / "tests" / "fixtures" / "seed" / (
    "H-020-00xxxx-00 DNBSEQ-T7+RS 基因测序仪系统操作指南（适配V2.0版本试剂套装）_中文_RUO_WH Tina.pdf"
)


def _rawdict(*lines: str) -> dict:
    """构造最小 rawdict：每个字符给一个递增 x0，同一行 y 固定。"""
    blocks = []
    for li, text in enumerate(lines):
        chars = []
        x = 10.0 + li * 0.0
        for ch in text:
            chars.append({
                "c": ch,
                "bbox": (x, 100.0 + li * 20, x + 5.0, 112.0 + li * 20),
                "origin": (x, 110.0 + li * 20),
            })
            x += 5.0
        blocks.append({"type": 0, "lines": [{"spans": [{"chars": chars}]}]})
    return {"blocks": blocks}


def _with_clipped_l() -> tuple[dict, dict]:
    """文本层 P5 行「1.8 mL」，可见提取少 L；两行可见完整写法。"""
    full = _rawdict("P1：试剂1.8 mL", "P2：试剂1.8 mL", "P5：试剂1.8 mL")
    visible = _rawdict("P1：试剂1.8 mL", "P2：试剂1.8 mL", "P5：试剂1.8 m")
    return full, visible


class TestTextLayerUnitTrunc:
    def test_r02_like_two_hits(self):
        text = "\n".join([
            "P1：自定义二链测序引物工作液1.8 mL",
            "P2：自定义MDA引物工作液1.8 mL",
            "P3：自定义一链测序引物工作液1.8 mL",
            "P4：自定义Barcode引物工作液1.8 mL",
            "P5：自定义DualBarcode引物工作液1.8 m",
        ])
        issues = check_truncated_ml_unit(text)
        assert len(issues) == 1
        assert issues[0]["rule"] == "DET-CN-UNITTRUNC"
        assert issues[0]["original_text"] == "1.8 m"
        assert "1.8 mL" in issues[0]["suggestion"]

    def test_two_pages_not_deduped_here(self):
        text = ("P1：试剂1.8 mL\nP2：试剂1.8 mL\nP5：试剂1.8 m\n\f\n"
                "P1：试剂1.8 mL\nP2：试剂1.8 mL\nP5：试剂1.8 m")
        assert len(check_truncated_ml_unit(text)) == 2

    def test_meter_unit_not_reported(self):
        # 行中「1 m 具有…」非行尾，且无同族 mL 行 → 不报
        text = "最大声压是在正常使用时操作人员的位置上和离设备外壳1 m 具有最大声压级"
        assert check_truncated_ml_unit(text) == []

    def test_no_majority_form_not_reported(self):
        text = "P5：试剂1.8 m"
        assert check_truncated_ml_unit(text) == []

    def test_different_family_not_reported(self):
        # 前缀末尾汉字不同族（距离为 1.8 m vs 试剂 1.8 mL）→ 不报
        text = "试剂1.8 mL\n试剂1.8 mL\n距离为1.8 m"
        assert check_truncated_ml_unit(text) == []

    def test_platform_content_with_phantom_l_has_no_text_layer_hit(self):
        # 平台 document.content 读到含 L 的文本层 → 必须靠渲染层通道
        text = "P1：试剂1.8 mL\nP2：试剂1.8 mL\nP5：试剂1.8 mL"
        assert check_truncated_ml_unit(text) == []

    def test_entry_point_wired(self):
        text = "P1：试剂1.8 mL\nP2：试剂1.8 mL\nP5：试剂1.8 m"
        rules = [i["rule"] for i in check_cn_format_consistency(text)]
        assert "DET-CN-UNITTRUNC" in rules

    def test_parsed_false_short_circuit(self):
        assert check_truncated_ml_unit("P5：试剂1.8 m", parsed=False) == []


class TestRenderClippedUnit:
    def test_clipped_l_reported(self):
        full, visible = _with_clipped_l()
        issues = _scan_page(full, visible, 180)
        assert len(issues) == 1
        i = issues[0]
        assert i["rule"] == "DET-CN-UNITTRUNC"
        assert i["original_text"] == "1.8 m"
        assert i["position"]["page_number"] == 180
        assert i["position"]["start"] == -1
        assert "被裁剪未渲染" in i["description"]
        assert "1.8 mL" in i["suggestion"]

    def test_visible_l_not_reported(self):
        full = _rawdict("P1：试剂1.8 mL", "P2：试剂1.8 mL", "P5：试剂1.8 mL")
        assert _scan_page(full, full, 180) == []

    def test_single_sibling_not_reported(self):
        full = _rawdict("P1：试剂1.8 mL", "P5：试剂1.8 mL")
        visible = _rawdict("P1：试剂1.8 mL", "P5：试剂1.8 m")
        assert _scan_page(full, visible, 180) == []

    def test_char_key_uses_bbox_origin(self):
        c = {"c": "L", "bbox": (503.12, 612.44, 508.0, 624.1)}
        assert _char_key(c) == (503.1, 612.4, "L")

    def test_different_numeric_not_reported(self):
        # 完整写法是 2.0 mL，候选是 1.8 m → 该数值未确立多数形态
        full = _rawdict("P1：试剂2.0 mL", "P2：试剂2.0 mL", "P5：试剂1.8 mL")
        visible = _rawdict("P1：试剂2.0 mL", "P2：试剂2.0 mL", "P5：试剂1.8 m")
        assert _scan_page(full, visible, 180) == []

    @pytest.mark.skipif(not FIXTURE_PDF.exists(), reason="seed fixture PDF 不存在")
    def test_real_fixture_pdf_hits_p180_p181(self):
        issues = detect_clipped_unit_chars(FIXTURE_PDF)
        pages = sorted(i["position"]["page_number"] for i in issues)
        assert pages == [180, 181]
        assert all(i["original_text"] == "1.8 m" for i in issues)
        assert all(i["rule"] == "DET-CN-UNITTRUNC" for i in issues)

    def test_missing_file_returns_empty(self):
        assert detect_clipped_unit_chars("C:/definitely/not/exist.pdf") == []


class TestDispatcherWiring:
    def test_review_py_calls_both_detectors(self):
        src = (BACKEND_ROOT / "app" / "api" / "review.py").read_text(encoding="utf-8")
        assert "from app.review_engine.pdf_clipped_unit import detect_clipped_unit_chars" in src
        assert "detect_clipped_unit_chars(_get_document_upload_path(document))" in src
        assert "from app.review_engine.cn_format_consistency import check_cn_format_consistency" in src
