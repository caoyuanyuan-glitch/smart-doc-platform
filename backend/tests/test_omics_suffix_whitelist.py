"""组学（-omics）词族白名单测试（TDD）。

对应《代码修订指令》改动 2。改动落地前 `proteomics` 等会失败，属预期。

说明：后缀规则会同时命中 `comics` / `economics` 这类合法英文词，
但它们本身就在基础词典里，豁免与否结果一致，属无害重叠，此处显式记录。
"""

import pytest

from app.utils import spell_checker as sc


@pytest.mark.parametrize(
    "term",
    [
        "omics",
        "genomics",
        "proteomics",
        "metabolomics",
        "lipidomics",
        "epigenomics",
        "glycomics",
        "transcriptomics",
        "metagenomics",
        "spatial",  # 对照组：已在白名单中的既有词
    ],
)
def test_omics_family_is_whitelisted(term):
    assert sc.is_whitelisted(term) is True, f"{term} 应作为组学词族/既有术语被豁免"


@pytest.mark.parametrize("term", ["comics", "economics"])
def test_benign_suffix_overlap_is_harmless(term):
    """合法英文词与 -omics 后缀重叠：豁免无害（本就不会被判错），仅作记录。

    这里不断言 True/False，只断言"不会因此被误判为拼写错误"。
    """
    result = sc.check_spelling(f"The {term} section is complete.", file_type="pdf")
    hits = [i for i in result if str(i.get("original_text", "")).lower() == term]
    assert not hits, f"{term} 是合法英文词，不应被报拼写错误"


def test_unrelated_word_is_not_whitelisted():
    """后缀豁免不能无限放宽：无关词仍不在白名单。"""
    assert sc.is_whitelisted("zzqxnotaterm") is False


def test_omics_sentence_has_no_spelling_issue():
    """回归：spatial omics 整句零拼写误报。"""
    result = sc.check_spelling(
        "The spatial omics pipeline supports metabolomics and lipidomics analysis.",
        file_type="pdf",
    )
    assert not result, f"组学相关句子不应产生拼写问题，实际：{result}"
