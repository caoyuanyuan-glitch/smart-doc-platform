# -*- coding: utf-8 -*-
"""P1 拼写证据分级与专有名词拼写的回归测试。

覆盖本轮 P1 改动的四条主线：

  1. is_confirmed_spelling_issue：确证型 vs 猜测型的判定边界；
  2. value_score：确证型拼写加分、猜测型拼写扣分——这正是
     真实拼写错误曾被 value_score 阈值误杀的根因；
  3. find_proper_noun_spelling_issues：SPELL-PROP 的确证能力
     与三类误报防线（合法复数 / 词典词 / PDF 折行伪影）；
  4. check_term_baseline：文档内术语基线比对（DET-TERM-BASELINE-001）。

回归动机：人工批注 #9 明确指出 `Intergra` 应为 `Integra`，
但改动前该问题在 value_score 阶段被筛掉，从未进入报告。
"""
from __future__ import annotations

import os
import sys

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.review_engine.pipeline import (  # noqa: E402
    is_confirmed_spelling_issue,
    value_score,
)
from app.review_engine.proper_noun_spelling import (  # noqa: E402
    find_proper_noun_spelling_issues,
    reload_proper_nouns,
)
from app.review_engine.term_baseline import check_term_baseline  # noqa: E402


def _issue(**kwargs):
    base = {
        "rule": "SPELL",
        "severity": "general",
        "confidence": 80,
        "source": "spellcheck",
        "category": "拼写/用词错误",
        "original_text": "intergra",
        "context": "some context",
        "suggestion": "Integra",
    }
    base.update(kwargs)
    return base


# ======================================================================
# 1. is_confirmed_spelling_issue 判定边界
# ======================================================================

@pytest.mark.parametrize(
    "rule",
    ["SPELL-TRANS", "SPELL-PROP", "SPELL-INS", "SPELL-SPLIT", "SPELL-PHRASE"],
)
def test_dedicated_confirmed_rules_are_treated_as_confirmed(rule):
    """有独立确证依据的规则，无论 confidence 高低都算确证型。"""
    assert is_confirmed_spelling_issue(_issue(rule=rule, confidence=60)) is True


def test_guessed_spelling_is_not_confirmed():
    """普通词典猜测（SPELL, confidence=80）不算确证。"""
    assert is_confirmed_spelling_issue(_issue(rule="SPELL", confidence=80)) is False


def test_high_confidence_spelling_is_confirmed():
    """命中人工错拼映射表的 SPELL（confidence=95）算确证。"""
    assert is_confirmed_spelling_issue(_issue(rule="SPELL", confidence=95)) is True


def test_serious_guessed_spelling_is_confirmed():
    """serious 级别的 SPELL 视为确证。"""
    assert is_confirmed_spelling_issue(
        _issue(rule="SPELL", severity="serious", confidence=80)
    ) is True


def test_spell_term_guessed_is_not_confirmed():
    assert is_confirmed_spelling_issue(_issue(rule="SPELL-TERM", confidence=80)) is False


def test_non_spelling_rule_is_not_confirmed():
    assert is_confirmed_spelling_issue(_issue(rule="DOC-TERM-001", confidence=99)) is False


# ======================================================================
# 2. value_score：确证型加分 / 猜测型扣分
# ======================================================================

def test_confirmed_spelling_scores_higher_than_guessed():
    """核心回归：确证型拼写的分数必须高于猜测型。

    改动前二者同扣 18 分，真实错误（Intergra）与猜测（词典候选）
    一样被阈值筛掉，确证型必须能凭 +14 越过阈值。
    """
    confirmed = value_score(
        _issue(rule="SPELL-PROP", severity="serious", confidence=96)
    )
    guessed = value_score(_issue(rule="SPELL", severity="general", confidence=80))

    assert confirmed > guessed
    assert confirmed >= 80
    assert guessed < 60


def test_transposition_spelling_is_not_penalised():
    """文档内换位拼写（SPELL-TRANS）不再被 -18 压制。"""
    score = value_score(_issue(rule="SPELL-TRANS", severity="serious", confidence=90))
    assert score >= 70


def test_guessed_spelling_still_penalised():
    """猜测型拼写仍维持降噪：分数必须被压低。"""
    score = value_score(_issue(rule="SPELL", severity="general", confidence=80))
    assert score < 50


# ======================================================================
# 3. SPELL-PROP 专有名词拼写
# ======================================================================

def test_proper_noun_typo_is_detected():
    """`Intergra` 应被判为 `Integra` 的错拼（人工批注 #9）。"""
    issues = find_proper_noun_spelling_issues(
        "The pipette was manufactured by Intergra Biosciences."
    )
    matched = [i for i in issues if i["original_text"] == "Intergra"]
    assert matched, f"未检出 Intergra，实际结果：{issues}"
    assert matched[0]["rule"] == "SPELL-PROP"
    assert "Integra" in matched[0]["suggestion"]


def test_proper_noun_correct_spelling_is_not_reported():
    """正确写法不能被报。"""
    issues = find_proper_noun_spelling_issues(
        "The pipette was manufactured by Integra Biosciences."
    )
    assert not [i for i in issues if i["original_text"] == "Integra"]


def test_legal_plural_form_is_not_reported():
    """`DNAs` 是 `DNA` 的合法复数，不能被误判成 `RNAs` 的错拼。"""
    issues = find_proper_noun_spelling_issues("Load 10 DNAs into the tube.")
    assert not [i for i in issues if i["original_text"] == "DNAs"]


def test_dictionary_word_is_not_reported():
    """普通英文词典词不能被当成专有名词错拼。"""
    issues = find_proper_noun_spelling_issues("The integral value is computed here.")
    assert not [i for i in issues if i["original_text"] == "integral"]


def test_pdf_line_wrap_artifact_is_not_reported():
    """PDF 折行伪影（`NBSEQ` 是 `DNBSEQ` 的真子串）不是拼写错误。"""
    content = "The DNBSEQ-G99RS system. In the table below the NBSEQ-G99RS model is listed."
    issues = find_proper_noun_spelling_issues(content)
    assert not [i for i in issues if i["original_text"] == "NBSEQ"]


def test_proper_noun_issue_carries_audit_metadata():
    """SPELL-PROP 必须带齐审计要素（依据、置信度、位置）。"""
    issues = find_proper_noun_spelling_issues(
        "The pipette was manufactured by Intergra Biosciences."
    )
    matched = [i for i in issues if i["original_text"] == "Intergra"]
    assert matched
    issue = matched[0]
    assert issue["audit_basis"]
    assert issue["confidence"] >= 90
    assert issue["position"]
    assert issue["severity"] == "serious"


def test_derived_form_is_not_treated_as_proper_noun_typo():
    """`OligoX` 是 `Oligo` 的派生形态（独立试剂名），不是 `Oligo` 的错拼。

    若按编辑距离 1 判为错拼，会与普通 SPELL 规则对同一处重复上报。
    """
    issues = find_proper_noun_spelling_issues("The OligoX reagent requires validation.")
    assert not [i for i in issues if i["original_text"] == "OligoX"]


def test_proper_noun_typo_produces_exactly_one_confirmed_issue():
    """同一处不得产出两条确证型拼写问题。

    `Intergra` 会被普通拼写规则捕获，但其建议是大小写错误的 `integra`；
    专有名词库给出的 `Integra` 才是正确写法。两条都产出时，
    低分那条会作为噪声进入中间结果。
    """
    from app.utils.spell_checker import check_spelling

    issues = check_spelling(
        "The pipette was manufactured by Intergra Biosciences.", file_type="pdf"
    )
    prop_issues = [i for i in issues if i["rule"] == "SPELL-PROP"]
    assert prop_issues, "Intergra 应由专有名词库确证"
    assert len(prop_issues) == 1
    assert "Integra" in prop_issues[0]["suggestion"]


# ======================================================================
# 4. 文档内术语基线（DET-TERM-BASELINE-001）
# ======================================================================

def _catalog_document() -> str:
    """构造一份满足「产品目录 + 型号前缀」判据的最小文档。

    模块的判据链（与真实 G99 文档一致）：
    1. 规范名需在产品目录表页出现（`Table N ... Set` 标题行，大小写不敏感）；
    2. 规范名全文出现 >= 3 次；
    3. 正文简写前需紧邻产品型号（如 `G99 FCL SE100`），否则属于泛指用法；
    4. 少数派门槛比较的是"带型号前缀的产品引用次数"，泛指用法不参与计数。
    """
    catalog = (
        "Table 1 Available sequencing sets\n"
        "Sequencing Reagent Set\n"
        "Sequencing Reagent Set\n"
        "Sequencing Reagent Set\n"
    )
    body = (
        "1.1 The G99 FCL SE100 Sequencing Reagent Set can perform SE35 sequencing.\n"
        "1.2 The G99 FCL SE100 Sequencing Reagent Set can perform SE50 sequencing.\n"
        "1.3 Prepare the G99 FCL SE100 sequencing set before the run.\n"
    )
    return f"{catalog}\f{body}"


def test_term_baseline_detects_lowercase_variant_of_catalog_term():
    """文档目录里是 `Sequencing Reagent Set`，正文简写成小写应被检出。"""
    issues = check_term_baseline(_catalog_document())
    baseline = [i for i in issues if i["rule"] == "DET-TERM-BASELINE-001"]
    assert baseline, f"未检出术语基线问题，实际结果：{issues}"
    assert "Sequencing Reagent Set" in baseline[0]["suggestion"]


def test_term_baseline_does_not_flag_consistent_usage():
    """全文写法一致时不得报术语基线问题。"""
    catalog = (
        "Table 1 Available sequencing sets\n"
        "Sequencing Reagent Set\n"
        "Sequencing Reagent Set\n"
        "Sequencing Reagent Set\n"
    )
    body = (
        "1.1 The G99 FCL SE100 Sequencing Reagent Set can perform SE35 sequencing.\n"
        "1.2 The G99 FCL SE100 Sequencing Reagent Set can perform SE50 sequencing.\n"
        "1.3 Prepare the G99 FCL SE100 Sequencing Reagent Set before the run.\n"
    )
    issues = check_term_baseline(f"{catalog}\f{body}")
    assert not [i for i in issues if i["rule"] == "DET-TERM-BASELINE-001"]


def test_term_baseline_skips_generic_usage_without_model_prefix():
    """没有型号前缀的泛指用法（the sequencing set）不是对产品的具体引用，不报。"""
    body = (
        "1.1 Prepare the sequencing set before the run.\n"
        "1.2 Load the sequencing set into the instrument.\n"
    )
    issues = check_term_baseline(f"{_catalog_document()}\f{body}")
    assert not [i for i in issues if i["rule"] == "DET-TERM-BASELINE-001"]


def test_term_baseline_catalog_title_is_case_insensitive():
    """目录表标题是 `Table 1 Available sequencing sets`（小写 s），也须识别为目录页。

    真实 G99 文档的目录表标题就是小写 `sequencing sets`；若要求大写
    `Set`，整页目录会被漏判，规范名永远拿不到基线资格，
    人工批注 #4/#5/#6 三处术语问题会全部漏检。
    """
    issues = check_term_baseline(_catalog_document())
    assert [i for i in issues if i["rule"] == "DET-TERM-BASELINE-001"]


def test_term_baseline_generic_usage_does_not_outvote_product_reference():
    """泛指用法不得计入少数派比较。

    文档里 `A sequencing set includes a Sequencing Flow Cell` 这类泛指句
    数量往往多于真正的产品引用，若计入总数会让候选被当成多数派，
    真正该报的产品引用反而被门槛挡掉。
    """
    catalog = (
        "Table 1 Available sequencing sets\n"
        "Sequencing Reagent Set\n"
        "Sequencing Reagent Set\n"
        "Sequencing Reagent Set\n"
    )
    generic = (
        "A sequencing set includes a Sequencing Flow Cell.\n"
        "A sequencing set includes a Sequencing Reagent Cartridge.\n"
        "A sequencing set includes a Sequencing Flow Cell.\n"
        "A sequencing set includes a Sequencing Reagent Cartridge.\n"
    )
    product_ref = (
        "The G99 FCL SE100 Sequencing Reagent Set can perform SE35 sequencing.\n"
        "The G99 FCL SE100 Sequencing Reagent Set can perform SE50 sequencing.\n"
        "G99 FCL SE100 sequencing set can perform PE50 sequencing.\n"
    )
    issues = check_term_baseline(f"{catalog}\f{generic}{product_ref}")
    baseline = [i for i in issues if i["rule"] == "DET-TERM-BASELINE-001"]
    assert baseline, "泛指用法不应掩盖真正的产品引用不一致"


# ----------------------------------------------------------------------
# 外部规范写法库（DET-TERM-CANON-001）
#
# 人工批注 #6/#7 指出 `Pair-end` / `Single-end` 首字母应小写。
# 这类问题文档内部是自洽的（全文都写 Pair-end），只能靠外部规范判定。
# ----------------------------------------------------------------------


def test_canonical_writing_reports_departure_from_standard_form():
    """`Pair-end` / `Single-end` 应按通行写法小写。"""
    from app.review_engine.canonical_writing import check_canonical_writing

    issues = check_canonical_writing(
        "PE means Pair-end sequencing; SE means Single-end sequencing."
    )
    found = {i["original_text"] for i in issues}
    assert "Pair-end" in found
    assert "Single-end" in found
    for issue in issues:
        assert issue["rule"] == "DET-TERM-CANON-001"
        # 建议里必须给出对应的小写规范写法
        expected = "pair-end" if issue["original_text"].lower().startswith("pair") else "single-end"
        assert expected in issue["suggestion"]


def test_canonical_writing_accepts_correct_form():
    """已是规范写法时不得上报。"""
    from app.review_engine.canonical_writing import check_canonical_writing

    issues = check_canonical_writing("PE means pair-end sequencing; SE means single-end sequencing.")
    assert not [i for i in issues if i["original_text"] in {"Pair-end", "Single-end"}]


def test_canonical_writing_does_not_match_inside_longer_words():
    """`pair-ended` 这类更长词不得被 `pair-end` 规则误伤。"""
    from app.review_engine.canonical_writing import check_canonical_writing

    issues = check_canonical_writing("The pair-ended fragment was recovered.")
    assert not issues


def test_canonical_writing_distinguishes_local_vs_global_departure():
    """规范写法已出现时，描述应说明是"局部不一致"；未出现时说明"全文未出现规范写法"。"""
    from app.review_engine.canonical_writing import check_canonical_writing

    local = check_canonical_writing("Use pair-end here but Pair-end there.")
    assert local
    assert "已出现" in local[0]["description"]

    global_ = check_canonical_writing("Only Pair-end appears here.")
    assert global_
    assert "全文未出现规范写法" in global_[0]["description"]


def test_canonical_writing_caps_reports_per_pattern():
    """同一写法的上报次数应有上限，避免全篇刷屏。"""
    from app.review_engine.canonical_writing import check_canonical_writing

    text = " ".join(["Pair-end sequencing"] * 40)
    issues = check_canonical_writing(text)
    assert 0 < len(issues) <= 6
