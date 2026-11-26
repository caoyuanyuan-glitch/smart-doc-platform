from app.api.review import _build_compare_audit_payload, _compare_values_match
from app.review_engine.bilingual_align import (
    bilingual_value_status,
    bilingual_values_match,
    build_bilingual_rows,
    detect_doc_language,
    extract_headings,
    is_bilingual_compare,
)


CN_MANUAL = """
第一章 产品介绍
货号 MGI-100
储存于 2–8℃

第二章 操作流程
1. 开机
2. 加载试剂
3. 运行程序
"""

EN_MANUAL = """
Chapter 1 Product Introduction
Catalog No. MGI-100
Store at 2–8°C

Chapter 2 Operating Procedure
1. Power on
2. Load reagents
3. Run the program
"""

EN_MANUAL_MISMATCH = """
Chapter 1 Product Introduction
Catalog No. MGI-200
Store at 2–8°C

Chapter 2 Operating Procedure
1. Power on
2. Load reagents
"""


def test_detect_doc_language():
    assert detect_doc_language("这是中文说明书，包含储存条件和操作步骤说明。") == "cn"
    assert detect_doc_language("This is an English user manual with storage conditions.") == "en"


def test_is_bilingual_compare_requires_both_languages():
    assert is_bilingual_compare(CN_MANUAL, [EN_MANUAL]) is True
    assert is_bilingual_compare(CN_MANUAL, [CN_MANUAL]) is False
    assert is_bilingual_compare(EN_MANUAL, [EN_MANUAL]) is False


def test_chapter_heading_not_dropped_as_toc():
    headings = extract_headings("Chapter 1 Product Introduction\nBody text about storage.")
    assert headings
    assert headings[0]["number"] == "1"
    assert "Product Introduction" in headings[0]["title"]


def test_chinese_and_english_chapters_share_numbers():
    cn_headings = {item["number"] for item in extract_headings(CN_MANUAL)}
    en_headings = {item["number"] for item in extract_headings(EN_MANUAL)}
    assert cn_headings == {"1", "2"}
    assert en_headings == {"1", "2"}


def test_bilingual_temperature_values_match():
    assert bilingual_values_match("储存于 2–8℃", "Store at 2–8°C") is True
    assert _compare_values_match("储存于 2–8℃", "Store at 2–8°C", bilingual=True) is True
    assert _compare_values_match("储存于 2–8℃", "Store at 2–8°C") is False


def test_translation_only_names_are_pending():
    assert bilingual_value_status("华大智造", "MGI Tech") == "translation"


def test_catalog_mismatch_is_p0():
    rows = build_bilingual_rows(
        {"filename": "cn.md", "text": CN_MANUAL},
        [{"filename": "en.md", "text": EN_MANUAL_MISMATCH}],
        enable_ai=False,
    )
    catalog_rows = [row for row in rows if row.get("level") == "P0"]
    assert catalog_rows
    assert any("mgi-100" in (row.get("main_value") or "").casefold() for row in catalog_rows)


def test_missing_english_chapter_is_p1():
    rows = build_bilingual_rows(
        {"filename": "cn.md", "text": CN_MANUAL},
        [{"filename": "en.md", "text": "Chapter 1 Product Introduction\nCatalog No. MGI-100\n"}],
        enable_ai=False,
    )
    assert any(row.get("parameter_name") == "章节 2" and row.get("level") == "P1" for row in rows)


def test_aligned_manuals_keep_matching_facts():
    rows = build_bilingual_rows(
        {"filename": "cn.md", "text": CN_MANUAL},
        [{"filename": "en.md", "text": EN_MANUAL}],
        enable_ai=False,
    )
    assert rows
    assert all(row.get("level") != "P0" for row in rows)


def test_compare_payload_enables_bilingual_mode():
    payload = _build_compare_audit_payload(
        {
            "filename": "cn.md",
            "text": CN_MANUAL,
            "params": [
                {"name": "货号", "value": "MGI-100"},
                {"name": "储存条件", "value": "2–8℃"},
            ],
        },
        [
            {
                "filename": "en.md",
                "text": EN_MANUAL,
                "params": [
                    {"name": "Catalog Number", "value": "MGI-100"},
                    {"name": "Storage", "value": "2–8°C"},
                ],
            }
        ],
        "both",
    )
    assert payload["summary"]["bilingual"] is True
    assert payload["main_document"]["language"] == "cn"
    assert any(row.get("kind") == "bilingual" for row in payload["compare_rows"])
    catalog_row = next(row for row in payload["compare_rows"] if row.get("parameter_name") == "货号")
    assert catalog_row["level"] == "一致"


def test_same_language_compare_skips_bilingual_rows():
    payload = _build_compare_audit_payload(
        {"filename": "a.md", "text": CN_MANUAL, "params": [{"name": "货号", "value": "MGI-100"}]},
        [{"filename": "b.md", "text": CN_MANUAL, "params": [{"name": "货号", "value": "MGI-100"}]}],
        "both",
    )
    assert payload["summary"]["bilingual"] is False
    assert all(row.get("kind") != "bilingual" for row in payload["compare_rows"])


def test_volume_lines_are_not_headings():
    headings = extract_headings("1.5 mL centrifuge tube\n8.5 mL 1 M NaCl + 0.05% Tween-20\n42.8 inches(W) × 29.8 inches(D)")
    assert headings == []


def test_fuse_and_postal_codes_are_not_catalog_tokens():
    rows = build_bilingual_rows(
        {"filename": "cn.md", "text": "第一章 规格\n250VAC10A 保险丝\n货号 PMIF-20RS"},
        [{"filename": "en.md", "text": "Chapter 1 Specifications\n250VAC 10A fuse\nCat. No. PMIF-20RS\nLV-2167, Latvia"}],
        enable_ai=False,
    )
    p0_rows = [row for row in rows if row.get("level") == "P0"]
    assert p0_rows == []


def test_junk_param_values_are_ignored():
    from app.api.review import _extract_compare_field_value, COMPARE_PARAM_DEFINITIONS

    spec = next(field for field in COMPARE_PARAM_DEFINITIONS if field["name"] == "规格")
    storage = next(field for field in COMPARE_PARAM_DEFINITIONS if field["name"] == "储存条件")
    catalog = next(field for field in COMPARE_PARAM_DEFINITIONS if field["name"] == "货号")
    assert _extract_compare_field_value([{"name": "Specifications", "value": "User manual"}], spec) == ""
    assert _extract_compare_field_value([{"name": "storage devices.", "value": "Restarting the device"}], storage) == ""
    assert _extract_compare_field_value([{"name": "Cat. No.", "value": "534056-4L"}], catalog) == "534056-4L"


def test_toc_titles_ignore_trailing_index():
    from app.review_engine.bilingual_align import extract_toc_titles

    text = "\n".join([
        "通用安全 2",
        "电气安全 3",
        "适用范围 8",
        "工作原理 8",
        "结构组成 8",
        "制造商信息 63",
        "APPAPEIL À LASER DE CLASSE 1",
        "保险丝 3",
    ])
    assert extract_toc_titles(text) == ["通用安全", "电气安全", "适用范围", "工作原理", "结构组成", "制造商信息"]


def test_section_titles_align_by_glossary():
    from app.review_engine.bilingual_align import align_section_titles

    pairs = align_section_titles(
        ["适用范围", "工作原理", "结构组成", "前视图", "制造商信息"],
        [
            "Conventions used in this manual",
            "Intended use",
            "Working principle",
            "Structural composition",
            "Front view",
            "Symbols",
            "Manufacturer information",
        ],
    )
    matched = {(item["main"], item["peer"]) for item in pairs if item["main"] and item["peer"]}
    assert ("适用范围", "Intended use") in matched
    assert ("工作原理", "Working principle") in matched
    assert any(item["peer"] == "Symbols" and item["main"] is None for item in pairs)
    assert any(item["peer"] == "Conventions used in this manual" and item["main"] is None for item in pairs)


def test_named_sections_report_missing_english_toc():
    cn_text = "\n".join([
        "通用安全 2",
        "电气安全 3",
        "适用范围 8",
        "工作原理 8",
        "结构组成 8",
        "制造商信息 63",
        "",
        "适用范围",
        "该产品仅供科研使用，货号 MGI-100。",
        "工作原理",
        "基于免疫荧光染色。",
        "结构组成",
        "由主机和工作站组成。",
        "通用安全",
        "请佩戴防护用品。",
        "电气安全",
        "使用 220V 电源。",
        "制造商信息",
        "武汉华大智造科技有限公司",
    ])
    en_text = "\n".join([
        "Conventions used in this manual 2",
        "General safety 2",
        "Electrical safety 4",
        "Intended use 12",
        "Working principle 12",
        "Structural composition 12",
        "Manufacturer information 79",
        "",
        "Conventions used in this manual",
        "This section explains warning symbols.",
        "Intended use",
        "This product is for research use only. Cat. No. MGI-100.",
        "Working principle",
        "Immunofluorescence staining.",
        "Structural composition",
        "The product consists of a host and a workstation.",
        "General safety",
        "Wear protective equipment.",
        "Electrical safety",
        "Use a 220V power supply.",
        "Manufacturer information",
        "Wuhan MGI Tech Co., Ltd.",
    ])
    rows = build_bilingual_rows(
        {"filename": "cn.pdf", "text": cn_text},
        [{"filename": "en.pdf", "text": en_text}],
        enable_ai=False,
    )
    assert any("Conventions used in this manual" in (row.get("reference_summary") or "") for row in rows if row.get("level") == "P1")
    assert any(row.get("parameter_name") == "已对齐目录章节" for row in rows)
