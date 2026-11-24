"""DET-VIS-TABLE-CONT-001（PDF 跨页表格表头连续性）单测。

合成 PDF 用 fitz 画线表格（bbox 由 find_tables 识别，文字用 ASCII
避免默认字体不支持中文变 '··' 干扰 clip 行序列判定）。
"""

from __future__ import annotations

import fitz
import pytest

from app.review_engine.pdf_table_continuity import check_pdf_table_continuity

COL_X = [72, 300, 520]


def _draw_table(page, rows, y0, y1):
    row_h = (y1 - y0) / len(rows)
    for i in range(len(rows) + 1):
        page.draw_line((COL_X[0], y0 + i * row_h), (COL_X[2], y0 + i * row_h))
    for x in COL_X:
        page.draw_line((x, y0), (x, y1))
    for i, row in enumerate(rows):
        for j, cell in enumerate(row):
            page.insert_text((COL_X[j] + 4, y0 + i * row_h + 16), cell)


def _make_pdf(path, p2_first_row, with_body_above=False):
    """页1 底部表格（Name/Desc 表头 + 数据行），页2 顶部表格。"""
    doc = fitz.open()
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((72, 100), "Chapter 1 Overview")
    _draw_table(p1, [("Name", "Desc"), ("DeviceA", "ForSeq")], 660, 780)
    p1.insert_text((280, 800), "1")

    p2 = doc.new_page(width=595, height=842)
    ty0 = 140 if with_body_above else 100
    if with_body_above:
        p2.insert_text((72, 100), "See parameters below:")
    _draw_table(p2, [p2_first_row, ("DeviceB", "ForLib")], ty0, ty0 + 120)
    p2.insert_text((280, 800), "2")
    doc.save(path)
    doc.close()


def _issue_pages(issues):
    import json

    return [json.loads(issue["position"]).get("page") for issue in issues]


def test_missing_header_repeat_is_reported(tmp_path):
    pdf = tmp_path / "missing_header.pdf"
    _make_pdf(str(pdf), ("DeviceC", "Param100"))
    issues = check_pdf_table_continuity(str(pdf))
    assert len(issues) == 1
    assert issues[0]["rule"] == "DET-VIS-TABLE-CONT-001"
    assert issues[0]["severity"] == "suggestion"
    assert issues[0]["confidence"] == 72
    assert issues[0]["source"] == "rule"
    assert _issue_pages(issues) == [2]


def test_repeated_header_not_reported(tmp_path):
    pdf = tmp_path / "repeated_header.pdf"
    _make_pdf(str(pdf), ("Name", "Desc"))
    assert check_pdf_table_continuity(str(pdf)) == []


def test_body_above_top_table_not_reported(tmp_path):
    pdf = tmp_path / "body_above.pdf"
    _make_pdf(str(pdf), ("DeviceC", "Param100"), with_body_above=True)
    assert check_pdf_table_continuity(str(pdf)) == []


def test_headerlike_first_rows_not_reported(tmp_path):
    """续页首行全是短列名（无数字、<8 字符）→ 视为独立表格列名，不报。"""
    pdf = tmp_path / "headerlike.pdf"
    _make_pdf(str(pdf), ("Mode", "Type"))
    assert check_pdf_table_continuity(str(pdf)) == []


def test_nonexistent_path_returns_empty(tmp_path):
    assert check_pdf_table_continuity(tmp_path / "nope.pdf") == []


def test_t7_goldset_pages_detected():
    """真实 goldset 冒烟：T7 R01 p69/p84 应命中（文件缺失时跳过）。"""
    pdf = r"C:/MyFileAudit/caoyuanyuan/2026-08/H-020-00xxxx-00 DNBSEQ-T7+RS 基因测序仪系统操作指南（适配V2.0版本试剂套装）_中文_RUO_WH R01 Tina.pdf"
    from pathlib import Path

    if not Path(pdf).exists():
        pytest.skip("T7 goldset PDF 不在本机")
    issues = check_pdf_table_continuity(pdf)
    pages = set(_issue_pages(issues))
    assert {69, 84} <= pages
