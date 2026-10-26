import os

import fitz

from app.api.compare import (
    _align_chapter_ranges,
    _diff_page_boxes,
    _lookup_peer_page,
    _pdf_chapter_ranges,
)

PDF_A = os.path.join(os.path.dirname(__file__), "..", "static", "preview", "task_7_a.pdf")
PDF_B = os.path.join(os.path.dirname(__file__), "..", "static", "preview", "task_7_b.pdf")


def test_front_matter_and_safety_align():
    if not os.path.exists(PDF_A) or not os.path.exists(PDF_B):
        return
    ranges_a = _pdf_chapter_ranges(PDF_A)
    ranges_b = _pdf_chapter_ranges(PDF_B)
    front_a = [r["heading"] for r in ranges_a if r["page_start"] < 8]
    assert "封面" in front_a
    assert "关于说明书" in front_a
    assert "版本记录" in front_a
    assert "目录" in front_a
    pairs = _align_chapter_ranges(ranges_a, ranges_b)
    peer1, heading1 = _lookup_peer_page(pairs, 1, "a")
    assert peer1 == 1
    assert heading1 in ("封面", "产品说明书")
    peer4, heading4 = _lookup_peer_page(pairs, 4, "a")
    assert peer4 == 4
    assert heading4 == "目录"
    peer8, heading8 = _lookup_peer_page(pairs, 8, "a")
    assert peer8 == 8
    assert heading8 == "安全"


def _kinds(path_a, page_a, path_b, page_b, side):
    da = fitz.open(path_a)
    db = fitz.open(path_b)
    try:
        return [k for _, k in _diff_page_boxes(da[page_a - 1], db[page_b - 1], side)]
    finally:
        da.close()
        db.close()


def test_wrapped_same_paragraph_is_not_delete_insert():
    if not os.path.exists(PDF_A) or not os.path.exists(PDF_B):
        return
    kinds_a = _kinds(PDF_A, 50, PDF_B, 56, "a")
    kinds_b = _kinds(PDF_A, 50, PDF_B, 56, "b")
    assert "del" not in kinds_a
    assert kinds_b.count("ins") >= 1


def test_fastq_case_change_is_modify():
    if not os.path.exists(PDF_A) or not os.path.exists(PDF_B):
        return
    kinds_a = _kinds(PDF_A, 52, PDF_B, 58, "a")
    kinds_b = _kinds(PDF_A, 52, PDF_B, 58, "b")
    assert "chg" in kinds_a
    assert "chg" in kinds_b
    assert "del" not in kinds_a
    assert "ins" not in kinds_b
