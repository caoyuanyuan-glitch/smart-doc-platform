from app.api import spell_check as spell_check_api
from app.utils import spell_checker as spell_checker_utils


def test_spell_check_process_text_passes_file_type_to_rule_engine(monkeypatch):
    captured = {}

    def fake_run_spelling_and_grammar_check(content, file_type=None):
        captured["content"] = content
        captured["file_type"] = file_type
        return []

    monkeypatch.setattr(spell_check_api, "run_spelling_and_grammar_check", fake_run_spelling_and_grammar_check)
    monkeypatch.setattr(spell_check_api, "_collect_low_level_rule_issues", lambda text, document_language: [])
    monkeypatch.setattr(spell_check_api, "_collect_consistency_issues", lambda text, document_language: [])

    result = spell_check_api.process_text("foo\n\nbar", file_type="pdf")

    assert captured == {"content": "foo\n\nbar", "file_type": "pdf"}
    assert result["total_count"] == 0


def test_guess_file_type_from_text_detects_markdown():
    assert spell_check_api._guess_file_type_from_text("```py\nprint('x')\n```") == "md"


def test_check_spelling_reports_each_occurrence_for_suggestion_based_typos(monkeypatch):
    class FakeSpell:
        def unknown(self, words):
            return {"wrng"}

        def candidates(self, word):
            return {"wrong"}

    monkeypatch.setattr(spell_checker_utils, "spell", FakeSpell())
    monkeypatch.setattr(spell_checker_utils, "is_whitelisted", lambda word: False)
    monkeypatch.setattr(spell_checker_utils, "_is_technical_term", lambda word: False)
    monkeypatch.setattr(spell_checker_utils, "_is_domain_abbreviation", lambda word: False)
    monkeypatch.setattr(spell_checker_utils, "_is_extraction_artifact", lambda word: False)
    monkeypatch.setattr(spell_checker_utils, "_should_skip_match_word", lambda word: False)
    monkeypatch.setattr(spell_checker_utils, "_should_skip_spelling_issue", lambda word, context, file_type=None: False)
    monkeypatch.setattr(spell_checker_utils, "_extract_chapter", lambda content, start: "")

    issues = spell_checker_utils.check_spelling("wrng text and wrng again")

    assert len(issues) == 2
    assert [issue["position"] for issue in issues] == ["0-4", "14-18"]
    assert all(issue["suggestion"] == "wrong" for issue in issues)


def test_get_spelling_suggestions_filters_equivalent_and_duplicate_candidates(monkeypatch):
    class FakeSpell:
        def candidates(self, word):
            return ["wrng", "wrong", "wrong", "Wrong", "wring", "wrung"]

    monkeypatch.setattr(spell_checker_utils, "spell", FakeSpell())

    suggestions = spell_checker_utils._get_spelling_suggestions("wrng")

    assert suggestions == ["wrong", "wring", "wrung"]


def test_collect_word_matches_reuses_normalized_word_occurrences():
    matches = spell_checker_utils._collect_word_matches("Wrng text and wrng again")

    assert list(matches.keys()) == ["wrng", "text", "and", "again"]
    assert [match.group(0) for match in matches["wrng"]] == ["Wrng", "wrng"]


def test_markdown_noise_masker_removes_code_and_links():
    content = "Keep `wrng` and [wrng](https://example.com) in docs.```python\nwrng\n```"
    masked = spell_checker_utils._mask_markdown_noise(content)

    assert masked.count("wrng") == 0


def test_runtime_whitelist_term_persists_in_memory_and_dictionary(monkeypatch):
    assert spell_checker_utils.add_runtime_whitelist_term("AlphaTool") is True
    assert spell_checker_utils.is_whitelisted("AlphaTool") is True


def test_runtime_whitelist_is_case_sensitive(monkeypatch):
    spell_checker_utils.add_runtime_whitelist_term("RNAs")

    assert spell_checker_utils.is_whitelisted("RNAs") is True
    assert spell_checker_utils.is_whitelisted("rnas") is False


def test_process_text_appends_legacy_grammar_issues(monkeypatch):
    monkeypatch.setattr(spell_check_api, "run_spelling_and_grammar_check", lambda content, file_type=None: [])
    monkeypatch.setattr(spell_check_api, "_collect_low_level_rule_issues", lambda text, document_language: [])
    monkeypatch.setattr(spell_check_api, "_collect_consistency_issues", lambda text, document_language: [])

    result = spell_check_api.process_text("It indicates that the icon are grayed out.")

    assert any(error["type"] == "grammar" and error["word"] == "are" for error in result["errors"])


def test_check_grammar_patterns_keeps_a_unified_phrase_valid():
    issues = spell_checker_utils.check_grammar_patterns("a unified FOV")

    assert issues == []


def test_find_term_variant_issues_skips_when_correct_form_exists_in_document():
    issues = spell_checker_utils._find_term_variant_issues(
        "The High-throughput workflow is supported. Another note mentions highthroughput only in OCR text.",
        set(),
    )

    assert all(issue["original_text"].lower() != "highthroughput" for issue in issues)


def test_has_correct_term_variant_in_document_matches_hyphenated_pdf_form():
    content = "Use the wide-\nbore pipette for transfer."

    assert spell_checker_utils._has_correct_term_variant_in_document(content, "wide-bore") is True


def test_should_skip_spelling_issue_skips_mixedly_false_positive():
    assert spell_checker_utils._should_skip_spelling_issue("mixedly", "Samples were mixedly distributed.", file_type="pdf") is True


def test_should_skip_spelling_issue_skips_nonfiltered_technical_term():
    assert spell_checker_utils._should_skip_spelling_issue("nonfiltered", "Use nonfiltered pipette tips for transfer.", file_type="pdf") is True
