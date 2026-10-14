import json
import re
from pathlib import Path

from difflib import SequenceMatcher

import pytest

from app.utils import document_parser


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
REGRESSION_SUITE = WORKSPACE_ROOT / ".monkeycode" / "docs" / "ifu-pdf-regression-cases-20260819.json"
BASELINE_PDF = WORKSPACE_ROOT / "H-020-001371-00 DNBelab C Series High-throughput Single-cell 5'RNA&V(D)J Library Preparation Set V2.0 Instructions for Use_English_RUO_QD_R01.pdf"
CANDIDATE_PDF = WORKSPACE_ROOT / "H-020-001371-00 DNBelab C Series High-throughput Single-cell 5'RNA&V(D)J Library Preparation Set V2 Tina..pdf"


def _load_regression_cases():
    payload = json.loads(REGRESSION_SUITE.read_text(encoding="utf-8"))
    return payload["cases"]


def _operator_spacing_consistent(reference: str, candidate: str) -> bool:
    return document_parser.clean_pdf_text(reference) == document_parser.clean_pdf_text(candidate)


def _rowspan_group_preserved(reference: str, candidate: str) -> bool:
    candidate_lines = [line.strip() for line in candidate.splitlines() if line.strip()]
    repeated_group_lines = 0
    for line in candidate_lines:
        cells = [cell.strip() for cell in line.split("|") if cell.strip()]
        if len(cells) >= 2 and cells[0] == cells[1]:
            repeated_group_lines += 1
    return repeated_group_lines == 0 and len(candidate_lines) <= len([line for line in reference.splitlines() if line.strip()]) + 1


def _figure_anchor_present(reference: str, candidate: str) -> bool:
    reference_has_anchor = "Figure" in reference or "Fig." in reference
    reference_has_image_signal = "[IMAGE]" in reference or "image placeholder" in reference.lower()
    candidate_has_anchor = "Figure" in candidate or "Fig." in candidate
    candidate_has_image_signal = "[IMAGE]" in candidate or "image placeholder" in candidate.lower()
    return reference_has_anchor and reference_has_image_signal and candidate_has_anchor and candidate_has_image_signal


def _short_window_fuzzy_ok(reference: str, candidate: str, threshold: float = 0.96) -> bool:
    ratio = SequenceMatcher(None, reference, candidate).ratio()
    extra_single_char_tokens = [
        token
        for token in re.findall(r"[A-Za-z]+", candidate)
        if len(token) == 1 and token not in re.findall(r"[A-Za-z]+", reference)
    ]
    return ratio >= threshold and not extra_single_char_tokens


def _sentence_alignment_gap_free(reference: str, candidate: str) -> bool:
    ref_sentences = [item.strip() for item in re.split(r"(?<=[.!?])\s+", reference) if item.strip()]
    cand_sentences = [item.strip() for item in re.split(r"(?<=[.!?])\s+", candidate) if item.strip()]
    missing = [sentence for sentence in ref_sentences if sentence not in cand_sentences]
    return not missing


def test_clean_pdf_text_normalizes_operator_spacing_and_units():
    raw = "Cytoactivity<5%\n6μL\nCat.No.: ABC-001\n4℃"

    cleaned = document_parser.clean_pdf_text(raw)

    assert "Cytoactivity < 5%" in cleaned
    assert "6 μL" in cleaned
    assert "Cat. No.: ABC-001" in cleaned
    assert "4℃" in cleaned


def test_clean_pdf_text_removes_toc_dot_lines_and_merges_hyphen_breaks():
    raw = "Chapter 1........12\nhigh-\nthroughput workflow\n\nKeep this paragraph."

    cleaned = document_parser.clean_pdf_text(raw)

    assert "Chapter 1........12" not in cleaned
    assert "highthroughput workflow" in cleaned
    assert "Keep this paragraph." in cleaned


def test_clean_pdf_text_keeps_form_feed_page_breaks():
    raw = "Background 91, 100\n206\fB\n\n保险丝 3, 6\n207\fQ\n\n清洗类型 114\n208"

    cleaned = document_parser.clean_pdf_text(raw)

    assert cleaned.count("\f") == 2
    assert "Background 91, 100" in cleaned.split("\f")[0]
    assert "保险丝 3, 6" in cleaned.split("\f")[1]


def test_clean_pdf_text_joins_cjk_wrapped_lines_without_space():
    # 中文折行拼接不应插入空格，否则审核会误报「中文文字间多余空格」
    raw = "分析软件完成数据处理和分析后，再通\n过ZLIMS Lite 查看分析结果。"

    cleaned = document_parser.clean_pdf_text(raw)

    assert "再通过ZLIMS Lite" in cleaned
    assert "再通 过" not in cleaned
    # 英文折行仍需保留空格分隔
    english = document_parser.clean_pdf_text("the workflow\ncontinues here")
    assert "workflow continues here" in english


def test_should_soft_join_only_same_line_continuation():
    from app.utils.document_parser import TextBlock

    page_width = 595.0
    # 单行正文排到页面右侧，下一块在同一行内缩进续写：应合并
    prev = TextBlock("本系统将根据所设定的配置", 1, "body", (79.6, 574.4, 578.3, 603.0))
    cont = TextBlock("信息治理符合条件的数据。", 1, "body", (93.5, 588.4, 213.0, 617.0))
    assert document_parser._should_soft_join(prev, cont, page_width) is True

    # 目录条目（前块含换行且未排到右侧）不应合并
    toc_prev = TextBlock("通用安全\n2", 1, "body", (161.6, 209.8, 578.3, 241.2))
    toc_next = TextBlock("电气安全\n2", 1, "body", (161.6, 228.5, 578.3, 259.9))
    assert document_parser._should_soft_join(toc_prev, toc_next, page_width) is False

    # 流程图节点（前块靠左，未排到右侧）不应合并
    node_prev = TextBlock("数据类型", 1, "body", (303.7, 385.8, 339.7, 411.5))
    node_next = TextBlock("混合", 1, "body", (312.3, 406.4, 330.3, 432.1))
    assert document_parser._should_soft_join(node_prev, node_next, page_width) is False

    # 上一块以句末标点结尾：视为独立句子，不应合并
    end_prev = TextBlock("这是完整的一句。", 1, "body", (79.6, 500.0, 578.3, 528.0))
    end_next = TextBlock("下一句开始", 1, "body", (93.5, 514.0, 213.0, 542.0))
    assert document_parser._should_soft_join(end_prev, end_next, page_width) is False


def test_clean_pdf_text_keeps_break_for_repeated_boundary_tokens():
    # 表格相邻单元格/相邻条目重复时不应被拼成「宿主判定宿主判定」这类伪重复
    raw = "MPS序列过滤\n宿主判定\n宿主判定\nSMS序列过滤"
    cleaned = document_parser.clean_pdf_text(raw)
    assert "宿主判定宿主判定" not in cleaned

    # 2x2 表格按 token 交错重复（状态/空闲/状态/空闲）同样不应被拼合
    grid = document_parser.clean_pdf_text("状态\n空闲\n状态\n空闲\n清洗")
    assert "状态空闲状态空闲" not in grid

    caption = document_parser.clean_pdf_text("图 6　全部应用界面\n界面信息说明如下：")
    assert "界面界面" not in caption
    assert "界面信息说明如下" in caption


@pytest.mark.skipif(not BASELINE_PDF.exists() or not CANDIDATE_PDF.exists(), reason="IFU PDF samples not present in workspace")
def test_parse_pdf_keeps_ifu_pair_text_equivalent():
    baseline = document_parser.parse_pdf(str(BASELINE_PDF))
    candidate = document_parser.parse_pdf(str(CANDIDATE_PDF))

    assert baseline == candidate
    assert "Cytoactivity < 5%" in baseline
    assert "vortex mixer to mix thoroughly" in baseline


@pytest.mark.parametrize("case", _load_regression_cases(), ids=lambda case: case["id"])
def test_ifu_json_regression_cases_are_executable(case):
    reference = case["synthetic_reference"]
    candidate = case["synthetic_candidate"]
    strategy = case["strategy"]

    if strategy == "operator_spacing_consistency":
        assert _operator_spacing_consistent(reference, reference) is True
        assert _operator_spacing_consistent(reference, candidate) is True
        return

    if strategy == "rowspan_group_preservation":
        assert _rowspan_group_preserved(reference, reference) is True
        assert _rowspan_group_preserved(reference, candidate) is False
        return

    if strategy == "figure_anchor_presence":
        assert _figure_anchor_present(reference, reference) is True
        assert _figure_anchor_present(reference, candidate) is False
        return

    if strategy == "short_window_fuzzy_compare":
        assert _short_window_fuzzy_ok(reference, reference) is True
        assert _short_window_fuzzy_ok(reference, candidate) is False
        return

    if strategy == "sentence_alignment_gap_detection":
        assert _sentence_alignment_gap_free(reference, reference) is True
        assert _sentence_alignment_gap_free(reference, candidate) is False
        return

    raise AssertionError(f"Unhandled regression strategy: {strategy}")
