"""同词多 occurrence 独立落 issue：位置不相交的重复文本不得折叠。

背景：T7 EN R03 人工批注对照发现 3 条「部分命中」共性根因——
requirment 只报 TOC 漏正文标题、DNB Make Buffer 只报 p113 漏 p105、
Enzymefrom 只报 p105 漏 p90。三个去重点（跨 chunk、跨模型、按原文）
此前仅凭 original_text 折叠，页码/char 位置完全不参与判定。
"""

import json

from app.api.review import (
    _char_spans_disjoint,
    _dedup_across_chunks,
    _issue_char_span,
    _locate_issue_in_chunk,
    _merge_multi_provider_results,
    dedupe_issues_by_original,
)


def _pos(start, end=None):
    return json.dumps({"char_start": start, "char_end": end if end is not None else start + 20})


def _issue(text, start, rule="SPELL", chapter="", provider=None, source="ai"):
    issue = {
        "rule": rule,
        "category": "拼写",
        "chapter": chapter,
        "original_text": text,
        "position": _pos(start),
        "severity": "general",
        "confidence": 80,
        "source": source,
    }
    if provider:
        issue["_provider"] = provider
    return issue


class TestIssueCharSpan:
    def test_dict_position(self):
        assert _issue_char_span({"position": {"char_start": 10, "char_end": 25}}) == (10, 25)

    def test_json_string_position(self):
        assert _issue_char_span({"position": _pos(7, 30)}) == (7, 30)

    def test_missing_returns_none(self):
        assert _issue_char_span({"position": ""}) is None
        assert _issue_char_span({}) is None

    def test_swapped_ends_normalized(self):
        assert _issue_char_span({"position": {"char_start": 30, "char_end": 10}}) == (10, 30)


class TestCharSpansDisjoint:
    def test_far_apart_disjoint(self):
        assert _char_spans_disjoint((0, 50), (5000, 5050))

    def test_overlap_not_disjoint(self):
        assert not _char_spans_disjoint((0, 100), (50, 150))

    def test_adjacent_within_slack_not_disjoint(self):
        # 80 字符容差内的紧邻不算不相交
        assert not _char_spans_disjoint((0, 100), (150, 200))

    def test_unknown_span_conservative(self):
        assert not _char_spans_disjoint(None, (0, 10))
        assert not _char_spans_disjoint((0, 10), None)


class TestDedupAcrossChunks:
    def test_same_word_different_occurrence_kept(self):
        issues = [
            _issue("requirment", 100, chapter="TOC"),
            _issue("requirment", 50000, chapter="Making DNBs"),
        ]
        result = _dedup_across_chunks(issues)
        assert len(result) == 2

    def test_same_occurrence_folded(self):
        issues = [
            _issue("requirment", 100, chapter="TOC"),
            _issue("requirment", 110, chapter="TOC"),
        ]
        result = _dedup_across_chunks(issues)
        assert len(result) == 1
        assert result[0].get("dedupe_reason") == "same_identity_key"

    def test_no_position_still_folds(self):
        # 位置未知时保守折叠（可能重复），不因缺定位而放出重复
        a = _issue("requirment", 100)
        b = _issue("requirment", 50000)
        for it in (a, b):
            it["position"] = ""
        result = _dedup_across_chunks([a, b])
        assert len(result) == 1


class TestMergeMultiProviderResults:
    def test_distinct_occurrences_kept(self):
        merged, _meta = _merge_multi_provider_results(
            {
                "qwen": [_issue("Remove Conversion Enzymefrom storage", 9000, provider="qwen")],
                "deepseek": [
                    _issue("Remove Conversion Enzymefrom storage", 45000, provider="deepseek")
                ],
            },
            ["qwen", "deepseek"],
        )
        assert len(merged) == 2

    def test_same_occurrence_cross_validated(self):
        merged, _meta = _merge_multi_provider_results(
            {
                "qwen": [_issue("requirment", 100, provider="qwen")],
                "deepseek": [_issue("requirment", 105, provider="deepseek")],
            },
            ["qwen", "deepseek"],
        )
        assert len(merged) == 1
        assert merged[0]["cross_validated"] is True
        assert "deepseek" in merged[0]["providers"]
        assert merged[0]["confidence"] > 80

    def test_overlapping_text_same_occurrence_folds(self):
        long_text = "the library concentration requirment must be documented"
        short_text = "concentration requirment must be documented"  # 包含比 43/55 > 0.7
        merged, _meta = _merge_multi_provider_results(
            {
                "qwen": [_issue(long_text, 100, provider="qwen")],
                "deepseek": [_issue(short_text, 110, provider="deepseek")],
            },
            ["qwen", "deepseek"],
        )
        assert len(merged) == 1


class TestDedupeIssuesByOriginal:
    def test_same_word_different_page_positions_kept(self):
        issues = [
            _issue("requirment", 100, source="rule"),
            _issue("requirment", 50000, source="rule"),
        ]
        result = dedupe_issues_by_original(issues)
        assert len(result) == 2

    def test_same_position_folds_preferring_higher_rank(self):
        ai = _issue("requirment", 100, source="ai")
        rule = _issue("requirment", 105, source="rule")
        result = dedupe_issues_by_original([ai, rule])
        assert len(result) == 1
        assert result[0]["source"] == "rule"

    def test_different_text_never_folds(self):
        issues = [
            _issue("requirment", 100, source="rule"),
            _issue("requriement", 100, source="rule"),
        ]
        assert len(dedupe_issues_by_original(issues)) == 2


class TestLocateIssueInChunk:
    TEXT = "alpha requirment beta. gamma requirment delta."

    def test_single_occurrence(self):
        assert _locate_issue_in_chunk("only requirment here", "requirment") == 5

    def test_not_found(self):
        assert _locate_issue_in_chunk("nothing here", "requirment") == -1

    def test_no_context_returns_first(self):
        assert _locate_issue_in_chunk(self.TEXT, "requirment") == 6

    def test_context_anchors_second_occurrence(self):
        # 两次 occurrence 相距足够远（>120 字符窗口），邻域才可区分
        text = "filler " * 40 + "requirment" + " padding " * 30 + "gamma requirment delta"
        ctx = "closing sentence gamma requirment delta appears near section end"
        pos = _locate_issue_in_chunk(text, "requirment", ctx)
        assert pos == text.rfind("requirment")  # 命中第二次出现
