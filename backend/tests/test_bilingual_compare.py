"""中英配对审核确定性规则的回归测试。"""

from app.review_engine.bilingual_compare import (
    build_bilingual_rows,
    detect_language,
    extract_caption_numbers,
    extract_measure_tokens,
    extract_safety_items,
    extract_section_profile,
)

CN_TEXT = """1 简介
2 注意事项
警告: 请勿混用试剂
3 操作步骤
1. 加入 400 μL 试剂
2. 于 -20 ℃ 保存
表 1 参数
图 2 结构
"""

EN_TEXT = """1 Introduction
2 Precautions
WARNING: Do not mix reagents
3 Procedure
1. Add 400 uL reagent
Table 1 Parameters
Figure 3 Structure
"""


def _main(text=CN_TEXT):
    return {"filename": "cn.pdf", "text": text}


def _ref(text=EN_TEXT):
    return {"filename": "en.pdf", "text": text}


def test_detect_language_zh_en_unknown():
    assert detect_language(CN_TEXT) == "zh"
    assert detect_language(EN_TEXT) == "en"
    assert detect_language("") == "unknown"


def test_extract_measure_tokens_normalizes_units_and_whitespace():
    cn = extract_measure_tokens(CN_TEXT)
    en = extract_measure_tokens(EN_TEXT)
    assert "400μl" in cn and "400μl" in en  # μL/uL/空格 归一
    assert "-20℃" in cn  # ℃ 前空格与码位归一


def test_extract_safety_items_requires_marker_prefix():
    items = extract_safety_items(CN_TEXT)
    assert len(items["WARNING"]) == 1
    assert items["WARNING"][0]["line_no"] == 3
    # 「2 注意事项」是章节标题，不应被计为 CAUTION 条目
    assert items["CAUTION"] == []


def test_extract_caption_numbers_normlizes_zh_en_prefix():
    assert extract_caption_numbers(CN_TEXT) == {"figure": {"2"}, "table": {"1"}}
    assert extract_caption_numbers(EN_TEXT) == {"figure": {"3"}, "table": {"1"}}


def test_flow_categories_reuse_zh_en_equivalents():
    cn = extract_section_profile(CN_TEXT)["categories"]
    en = extract_section_profile(EN_TEXT)["categories"]
    assert cn == en  # 注意事项/操作步骤 vs Precautions/Procedure 同类别，不误报缺章


def test_missing_warning_is_p0_with_bidirectional_evidence():
    rows = build_bilingual_rows(_main(), [_ref(EN_TEXT.replace("WARNING: Do not mix reagents\n", ""))])
    warning_rows = [row for row in rows if row["kind"] == "bilingual_safety" and "警告" in row["parameter_name"]]
    assert len(warning_rows) == 1
    assert warning_rows[0]["level"] == "P0"
    assert warning_rows[0]["main_evidence"]
    assert "参考文件" in warning_rows[0]["evidence"]


def test_measure_token_mismatch_is_p1_and_allows_product_difference():
    rows = build_bilingual_rows(_main(), [_ref(EN_TEXT)])
    measure = next(row for row in rows if row["kind"] == "bilingual_measure")
    assert measure["level"] == "P1"
    assert "-20℃" in measure["main_value"]
    assert "人工裁定" in measure["conclusion"]  # 不把产品配置差异定性为错误


def test_caption_mismatch_is_p2_pending_adjudication():
    rows = build_bilingual_rows(_main(), [_ref(EN_TEXT)])
    caption = next(row for row in rows if row["kind"] == "bilingual_caption")
    assert caption["level"] == "P2"
    assert "人工" in caption["conclusion"]


def test_same_language_pair_does_not_emit_issue():
    rows = build_bilingual_rows(_main(), [_ref(CN_TEXT)])
    assert len(rows) == 1
    assert rows[0]["level"] == "一致"
    assert "未识别到中英配对" in rows[0]["conclusion"]


def test_no_objective_difference_emits_consistent_row():
    en_matched = EN_TEXT.replace("Figure 3", "Figure 2").replace(
        "1. Add 400 uL reagent", "1. Add 400 uL reagent\n2. Store at -20°C"
    )
    rows = build_bilingual_rows(_main(), [_ref(en_matched)])
    assert all(row["level"] == "一致" for row in rows)


# 以下 3 条来自 H-T-163/H-T-164 真实 PDF 离线验证发现的误报，防止回归。
def test_measure_regex_does_not_truncate_after_cjk_or_decimal_point():
    tokens = extract_measure_tokens("准备0.05% Tween-20；各孔装有2.60 mL 抗体；于 -20 ℃ 保存")
    assert "0.05%" in tokens
    assert "2.60ml" in tokens
    assert "05%" not in tokens and "5%" not in tokens and "60ml" not in tokens


def test_section_profile_does_not_treat_process_line_as_heading():
    text = "15. 将载片浸泡于含0.5% Triton X-100 的PBS 溶液中，室温静置15 分钟\n9.4 注意事项"
    profile = extract_section_profile(text)
    assert "15" not in profile["top_level"]
    assert "9.4" in {item["number"] for item in profile["headings"]}


def test_real_pair_no_spurious_numeric_or_section_noise():
    cn = "9.4 注意事项\n准备0.05% Tween-20\n2.60 mL 抗体"
    en = "9.4 Precautions\nPrepare 0.05% Tween-20\n2.60 mL antibody"
    rows = build_bilingual_rows(_main(cn), [_ref(en)])
    assert not any(row["kind"] == "bilingual_measure" for row in rows)
    assert not any(row["parameter_name"] == "章节结构" for row in rows)


def test_chinese_time_units_and_troubleshooting_synonyms_match_english():
    cn = "第11 章 故障处理\n室温静置15 分钟，放置24 小时"
    en = "Chapter 11 Troubleshooting\nIncubate for 15 min at room temperature for 24 h"
    rows = build_bilingual_rows(_main(cn), [_ref(en)])
    assert not any(row["kind"] == "bilingual_measure" for row in rows)
    assert not any(row["parameter_name"] == "流程章节覆盖" for row in rows)


# PMIF-20RS 中英真实 PDF 验证暴露的 4 类误报，逐条锁定。
def test_measure_not_extracted_across_line_break():
    assert extract_measure_tokens("水化 32 \n\nX\nStitching 25 \n\nW") == {}


def test_measure_accepts_chinese_char_after_unit():
    tokens = extract_measure_tokens("各静置20 分钟进行水化；24 小时内完成；37 °C的 PBS")
    assert {"20min", "24h", "37℃"} <= set(tokens)


def test_chinese_safety_accepts_dash_and_comma_but_not_heading():
    items = extract_safety_items("警告—打开时有3B 类激光辐射\n小心，烫伤指示\n注意事项")
    assert len(items["WARNING"]) == 1
    assert len(items["CAUTION"]) == 1


def test_section_profile_ignores_toc_page_numbers():
    # 目录页「标题 + 页码」被提取成孤立数字；无显式「第 N 章」时不应给出顶层编号。
    text = "1 通用安全 2\n4 外箱 4\n37\n83"
    assert extract_section_profile(text)["top_level"] == set()
