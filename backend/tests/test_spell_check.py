from app.api import spell_check as spell_check_api
from app.utils import spell_checker as spell_checker_utils
from app.utils import grammar_engine


class _FakeWordFrequency:
    def load_words(self, words):
        return None


class _FakeSpellWithWordFrequency:
    def __init__(self):
        self.word_frequency = _FakeWordFrequency()


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


def test_check_spelling_keeps_original_case_for_each_occurrence(monkeypatch):
    class FakeSpell:
        def unknown(self, words):
            return {"oligox"}

        def candidates(self, word):
            return {"oligo"}

    monkeypatch.setattr(spell_checker_utils, "spell", FakeSpell())
    monkeypatch.setattr(spell_checker_utils, "is_whitelisted", lambda word: False)
    monkeypatch.setattr(spell_checker_utils, "_is_technical_term", lambda word: False)
    monkeypatch.setattr(spell_checker_utils, "_is_domain_abbreviation", lambda word: False)
    monkeypatch.setattr(spell_checker_utils, "_is_extraction_artifact", lambda word: False)
    monkeypatch.setattr(spell_checker_utils, "_should_skip_match_word", lambda word: False)
    monkeypatch.setattr(spell_checker_utils, "_should_skip_spelling_issue", lambda word, context, file_type=None: False)
    monkeypatch.setattr(spell_checker_utils, "_extract_chapter", lambda content, start: "")

    issues = spell_checker_utils.check_spelling("OligoX requires validation.")

    assert len(issues) == 1
    assert issues[0]["original_text"] == "OligoX"
    assert issues[0]["suggestion"] == "oligo"


def test_markdown_noise_masker_removes_code_and_links():
    content = "Keep `wrng` and [wrng](https://example.com) in docs.```python\nwrng\n```"
    masked = spell_checker_utils._mask_markdown_noise(content)

    assert masked.count("wrng") == 0


def test_runtime_whitelist_term_persists_in_memory_and_dictionary(monkeypatch):
    monkeypatch.setattr(spell_checker_utils, "spell", _FakeSpellWithWordFrequency())

    assert spell_checker_utils.add_runtime_whitelist_term("AlphaTool") is True
    assert spell_checker_utils.is_whitelisted("AlphaTool") is True


def test_runtime_whitelist_is_case_sensitive(monkeypatch):
    monkeypatch.setattr(spell_checker_utils, "spell", _FakeSpellWithWordFrequency())

    spell_checker_utils.add_runtime_whitelist_term("RNAs")

    assert spell_checker_utils.is_whitelisted("RNAs") is True
    assert spell_checker_utils.is_whitelisted("rnas") is False


def test_process_text_appends_legacy_grammar_issues(monkeypatch):
    monkeypatch.setattr(spell_check_api, "run_spelling_and_grammar_check", lambda content, file_type=None: [])
    monkeypatch.setattr(spell_check_api, "_collect_low_level_rule_issues", lambda text, document_language: [])
    monkeypatch.setattr(spell_check_api, "_collect_consistency_issues", lambda text, document_language: [])
    monkeypatch.setattr(spell_check_api, "_append_languagetool_issues", lambda text, issues, document_language: None)

    result = spell_check_api.process_text("It indicates that the icon are grayed out.")

    assert any(error["type"] == "grammar" and error["word"] == "are" for error in result["errors"])


def test_process_text_appends_languagetool_issues_for_english(monkeypatch):
    monkeypatch.setattr(spell_check_api, "run_spelling_and_grammar_check", lambda content, file_type=None: [])
    monkeypatch.setattr(spell_check_api, "_collect_low_level_rule_issues", lambda text, document_language: [])
    monkeypatch.setattr(spell_check_api, "_collect_consistency_issues", lambda text, document_language: [])

    def fake_languagetool(text, issues, document_language):
        assert document_language == "english"
        issues.append({
            "severity": "warning",
            "category": "grammar",
            "source": "languagetool",
            "original_text": "has",
            "context": text,
            "description": "LanguageTool issue",
            "suggestion": "have",
            "position": "17-20",
        })

    monkeypatch.setattr(spell_check_api, "_append_legacy_grammar_issues", lambda text, issues: None)
    monkeypatch.setattr(spell_check_api, "_append_languagetool_issues", fake_languagetool)

    result = spell_check_api.process_text("These documents clearly has several major errors today.")

    assert result["grammar_count"] == 1
    assert result["errors"][0]["word"] == "has"
    assert result["errors"][0]["suggestions"] == ["have"]


def test_is_whitelisted_builtin_exact_match_is_case_sensitive():
    assert spell_checker_utils.is_whitelisted("guanggu") is True
    assert spell_checker_utils.is_whitelisted("Guanggu") is False


def test_reload_whitelist_from_disk_rebuilds_runtime_terms(tmp_path, monkeypatch):
    whitelist_file = tmp_path / "whitelist.json"
    whitelist_file.write_text('{"terms": [{"word": "Oligo"}]}', encoding="utf-8")
    monkeypatch.setattr(spell_checker_utils, "WHITELIST_FILE", whitelist_file)

    spell_checker_utils.reload_whitelist_from_disk()
    assert "Oligo" in spell_checker_utils.get_exact_whitelist_snapshot()

    whitelist_file.write_text('{"terms": []}', encoding="utf-8")
    spell_checker_utils.reload_whitelist_from_disk()

    assert "Oligo" not in spell_checker_utils.get_exact_whitelist_snapshot()
    assert spell_checker_utils.is_whitelisted("Oligo") is False


def test_languagetool_post_filter_is_case_sensitive():
    issues = [
        {"_word": "Oligo", "position": "0-5"},
        {"_word": "oligo", "position": "6-11"},
    ]

    filtered = grammar_engine._post_filter_whitelist(issues, {"Oligo"})

    assert filtered == [{"_word": "oligo", "position": "6-11"}]


def test_languagetool_selfhosted_url_uses_v2_check(monkeypatch):
    monkeypatch.setenv("LT_BASE_URL", "http://localhost:8010")

    assert grammar_engine._get_check_url("selfhosted") == "http://localhost:8010/v2/check"


def test_check_grammar_patterns_keeps_a_unified_phrase_valid():
    issues = spell_checker_utils.check_grammar_patterns("a unified FOV")

    assert issues == []
