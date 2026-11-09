import time
from pathlib import Path

from openpyxl import Workbook

from app.services.terminology import (
    load_terminology,
    pack_to_term_dict,
    reset_terminology_cache,
    run_term_check_v2,
    trim_terms_for_ai_v2,
)

REAL_V30 = (
    Path(__file__).resolve().parents[1]
    / "seed"
    / "knowledge"
    / "资源库"
    / "术语库"
    / "术语&固定表达-V3.0.xlsx"
)


def _write_pack(path: Path):
    wb = Workbook()
    ws = wb.active
    ws.append([
        "zh-CN", "source", "note", "description", "extra", "extra2",
        "en-US", "source", "note", "description", "extra", "extra2",
    ])
    ws.append([
        "IT产品与服务", "体系通用模板", "体系名称/部门名称", "", "", "",
        "IT product & service", "体系通用模板", "", "", "", "",
    ])
    ws.append([
        "%1:机械臂归零", "R3", "", "", "", "",
        "%1: robotic arm back to zero", "R3", "", "", "", "",
    ])
    ws.append([
        "清洗", "T7", "禁止写成【清洗】", "", "", "",
        "Wash", "T7", "", "", "", "",
    ])
    ws.append([
        "【清洗】", "T7", "", "", "", "",
        "WashX", "T7", "", "", "", "",
    ])
    wb.save(path)


def test_load_terminology_uses_header_blocks(tmp_path):
    reset_terminology_cache()
    path = tmp_path / "术语&固定表达-V3.0.xlsx"
    _write_pack(path)
    pack = load_terminology(str(path))
    assert pack is not None
    assert pack["zh_index"]["%1:机械臂归零"] == ["%1: robotic arm back to zero"]
    assert pack["zh_index"]["IT产品与服务"] == ["IT product & service"]
    mapping = pack_to_term_dict(pack)
    assert mapping["IT产品与服务"] == "IT product & service"
    assert mapping["%1:机械臂归零"] != "R3"

    t0 = time.perf_counter()
    again = load_terminology(str(path))
    elapsed = time.perf_counter() - t0
    assert again is pack
    assert elapsed < 0.05


def test_load_terminology_missing_and_bad_header(tmp_path):
    reset_terminology_cache()
    assert load_terminology(str(tmp_path / "nope.xlsx")) is None
    bad = tmp_path / "bad.xlsx"
    wb = Workbook()
    wb.active.append(["foo", "bar"])
    wb.save(bad)
    assert load_terminology(str(bad)) is None


def test_run_term_check_v2_reports_inconsistency_and_forbidden(tmp_path):
    reset_terminology_cache()
    path = tmp_path / "术语.xlsx"
    _write_pack(path)
    pack = load_terminology(str(path))
    content = "请执行清洗，同时【清洗】完成。IT产品与服务 paired with WashX nearby."
    issues = run_term_check_v2(content, pack, lang="zh")
    rules = {item["rule"] for item in issues}
    assert "TERM-INCONSIST" in rules or "TERM-PAIR" in rules or "TERM-FORBIDDEN" in rules
    trimmed = trim_terms_for_ai_v2(pack, "%1:机械臂归零", max_items=2)
    assert any(item["zh"] == "%1:机械臂归零" for item in trimmed)


def test_real_v30_pack_parses_5506_pairs():
    assert REAL_V30.is_file()
    reset_terminology_cache()
    pack = load_terminology(str(REAL_V30))
    assert pack is not None
    assert len(pack["pairs"]) == 5506
    assert pack["zh_index"]["%1:机械臂归零"] == ["%1: robotic arm back to zero"]
    assert pack["zh_index"]["IT产品与服务"] == ["IT product & service"]
    mapping = pack_to_term_dict(pack)
    assert mapping["%1:机械臂归零"] != "R3"
    assert mapping["IT产品与服务"] != "体系文件通用模板"
