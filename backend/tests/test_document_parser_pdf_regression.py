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
