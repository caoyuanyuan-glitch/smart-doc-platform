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

    result = spell_check_api.process_text("foo.\n\nbar", file_type="pdf")

    assert captured == {"content": "foo.\n\nbar", "file_type": "pdf"}
    assert result["total_count"] == 0


def test_merge_soft_wrapped_lines_joins_pdf_visual_line_breaks():
    text = (
        "4. If the selected recipe includes the barcode length, tap the Barcode list to\n\n"
        "select a barcode file.\n\n"
        "5. If the selected recipe includes the barcode length, you need to select whether\n\n"
        "to split barcode. Yes is selected by default."
    )

    merged = spell_check_api._merge_soft_wrapped_lines(text)

    assert merged == (
        "4. If the selected recipe includes the barcode length, tap the Barcode list to select a barcode file.\n\n"
        "5. If the selected recipe includes the barcode length, you need to select whether to split barcode. "
        "Yes is selected by default."
    )


def test_merge_soft_wrapped_lines_keeps_paragraphs_lists_and_mid_word_fragments():
    text = (
        "Revision history\n\nDate\n\nVersion\n\n"
        "a. Select Yes. The Exiting interface is displayed.\n\n"
        "MGI has t\n\naken measures to ensure the correctness of this manual.\n\n"
        "Use 200 uL wide-\n\ntip pipette tips."
    )

    merged = spell_check_api._merge_soft_wrapped_lines(text)

    assert merged == (
        "Revision history\n\nDate\n\nVersion\n\n"
        "a. Select Yes. The Exiting interface is displayed.\n\n"
        "MGI has taken measures to ensure the correctness of this manual.\n\n"
        "Use 200 uL wide-tip pipette tips."
    )


def test_process_text_keeps_line_breaks_outside_pdf():
    text = "foo\n\nbar"

    assert spell_check_api.process_text(text)["text"] == "foo\n\nbar"
    assert spell_check_api.process_text(text, file_type="pdf")["text"] == "foo bar"


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


def test_check_spelling_reports_fixed_pdf_phrase_typos(monkeypatch):
    monkeypatch.setattr(spell_checker_utils, "_should_skip_spelling_issue", lambda word, context, file_type=None: False)

    issues = spell_checker_utils.check_spelling("Filter the sample until it is lees than 60 μm and typed of beads.", file_type="pdf")

    assert [issue["original_text"] for issue in issues] == ["lees than", "typed of"]
    assert issues[0]["suggestion"] == "less than"
    assert issues[1]["suggestion"] == "types of"


def test_check_spelling_reports_common_pdf_typos(monkeypatch):
    monkeypatch.setattr(spell_checker_utils, "_should_skip_spelling_issue", lambda word, context, file_type=None: False)

    issues = spell_checker_utils.check_spelling("The power suppy waster container is dispalyed and the password shoud be consitent.", file_type="pdf")

    assert {issue["original_text"] for issue in issues} == {"power suppy", "waster container", "dispalyed", "shoud", "consitent", "suppy"}
    assert len(issues) == 6
    suggestions = {issue["original_text"]: issue["suggestion"] for issue in issues}
    assert suggestions["power suppy"] == "power supply"
    assert suggestions["waster container"] == "waste container"
    assert suggestions["dispalyed"] == "displayed"
    assert suggestions["shoud"] == "should"
    assert suggestions["consitent"] == "consistent"
    assert suggestions["suppy"] == "supply"


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


def test_is_vowel_sound_judges_all_caps_wordlike_terms_by_whole_word_sound():
    # all-caps 可读词按整词读音判定：HOME 读 /h/，不按字母名 H(/eɪtʃ/) 判为元音音。
    assert spell_checker_utils._is_vowel_sound('HOME') is False
    assert spell_checker_utils._is_vowel_sound('END') is True
    assert spell_checker_utils._is_vowel_sound('OPEN') is True
    # all-caps 缩写仍按字母名判定：MRI 读 /ɛm/、USB 读 /juː/。
    assert spell_checker_utils._is_vowel_sound('MRI') is True
    assert spell_checker_utils._is_vowel_sound('UPS') is False
    assert spell_checker_utils._is_vowel_sound('USB') is False
    # 小写词与混合大小写走首字母读音。
    assert spell_checker_utils._is_vowel_sound('home') is False
    assert spell_checker_utils._is_vowel_sound('Home') is False


def test_check_grammar_patterns_article_for_home_and_ups():
    # 正确搭配不报。
    assert spell_checker_utils.check_grammar_patterns("used in a HOME HEALTHCARE ENVIRONMENT") == []
    assert spell_checker_utils.check_grammar_patterns("use a UPS for backup power") == []

    # 错误搭配报出，并给出正确冠词。
    home_issues = spell_checker_utils.check_grammar_patterns("used in an HOME HEALTHCARE ENVIRONMENT")
    assert [(i["original_text"], i["suggestion"]) for i in home_issues] == [
        ("an HOME", "建议改为: a HOME")
    ]

    ups_issues = spell_checker_utils.check_grammar_patterns("use an UPS for backup power")
    assert [(i["original_text"], i["suggestion"]) for i in ups_issues] == [
        ("an UPS", "建议改为: a UPS")
    ]


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


def test_run_grammar_accepts_plural_subjects_in_proprietary_notice():
    text = (
        "This manual and the information contained herein are proprietary to Qingdao MGI Tech Co., Ltd., "
        "and are intended solely for the contractual use of its customers. "
        "Figures in this manual are for illustrative purpose only. "
        "Trademarks, product, service, and company names mentioned in this manual are the property "
        "of their respective companies."
    )
    errors = []

    spell_check_api.run_grammar(text, errors)

    assert errors == []


def test_run_grammar_accepts_modifiers_between_subject_and_verb():
    # 主语与动词之间夹入介词短语、并列成分、关系从句或结尾为 -ss 的单数名词时，不应报主谓不一致。
    cases = [
        "Once the pre-run wash and maintenance wash are completed, run another wash.",
        "The chip and universal sequencing reaction kit are not used immediately.",
        "A message that indicates the exceptions is displayed if the test fails.",
        "This process is suitable for the extraction.",
        "The data are analyzed automatically.",
    ]
    for text in cases:
        errors = []

        spell_check_api.run_grammar(text, errors)

        assert errors == [], text


def test_run_grammar_does_not_treat_line_break_fragments_as_pronouns():
    errors = []

    spell_check_api.run_grammar("Transfer the supernatant to a new tube.", errors)

    assert errors == []


def test_run_grammar_still_reports_provable_agreement_errors():
    cases = {
        "The tube are ready.": "are",
        "The tubes is ready.": "is",
        "It indicates that the icon are grayed out.": "are",
        "There is many samples.": "is",
    }
    for text, expected in cases.items():
        errors = []

        spell_check_api.run_grammar(text, errors)

        assert [text[e["start"]:e["end"]] for e in errors] == [expected], text


def test_run_grammar_uses_noun_head_after_there_be():
    cases = [
        "If there are any special insert size requirements for the kit, contact us.",
        "There is no sound of cracked ice during shaking.",
        "There are many samples in the rack.",
        "There is ice in the cartridge.",
    ]
    for text in cases:
        errors = []

        spell_check_api.run_grammar(text, errors)

        assert errors == [], text


def test_run_grammar_accepts_irregular_plural_subjects():
    # 不规则复数不以 -s/-es 结尾，不得被当成单数而与 are/were 冲突。
    cases = [
        "The people are waiting outside.",
        "The children are playing in the yard.",
        "Several mice are in the cage.",
        "The women are here.",
        "The police are investigating.",
    ]
    for text in cases:
        errors = []

        spell_check_api.run_grammar(text, errors)

        assert errors == [], text

    # 确实用错单数动词时仍要报。
    flagged = []
    spell_check_api.run_grammar("The people is waiting outside.", flagged)
    assert len(flagged) == 1


def test_run_grammar_there_be_ignores_trailing_modifier_or_verb():
    # there be 之后的名词短语常跟形容词或动词，中心语是短语内的名词而不是它们。
    cases = [
        "There are several options available.",
        "If there are any temperature alarms, contact technical support.",
        "If there are questions, contact us.",
        "Verify that there are no bubbles remaining.",
    ]
    for text in cases:
        errors = []

        spell_check_api.run_grammar(text, errors)

        assert errors == [], text


def test_low_level_acronym_spacing_rule_ignores_math_and_ui_labels():
    text = "Library input V(μL)= c(ng/μL)×106 N(bp)\n\nMetrics\nProgress(10/302)\n"

    issues = spell_check_api._collect_low_level_rule_issues(text, "english")

    assert all("缩写与括号" not in issue["description"] for issue in issues)


def test_low_level_acronym_spacing_rule_still_flags_real_acronyms():
    text = "Extract the DNA(1 μg) sample and run PCR(2 cycles)."

    issues = spell_check_api._collect_low_level_rule_issues(text, "english")

    flagged = [issue["original_text"] for issue in issues if "缩写与括号" in issue["description"]]
    assert flagged == ["DNA(", "PCR("]


def test_collect_punctuation_spacing_issues_flags_missing_space_after_period():
    text = "Cool the lid to operating temperature.For these cyclers, wait."

    issues = spell_check_api._collect_punctuation_spacing_issues(text)

    assert [issue["original_text"] for issue in issues] == ["temperature.For"]
    assert issues[0]["suggestion"] == "temperature. For"


def test_collect_punctuation_spacing_issues_keeps_legal_abbreviations():
    text = "Use e.g. this kit, the U.S. Army standard, and Fig.1 as shown in V3.0."

    assert spell_check_api._collect_punctuation_spacing_issues(text) == []


def test_collect_split_word_issues_uses_document_consistency():
    text = "DNBSEQ-E25RS High-throughput Sequencing Set and DNBSEQ-E25RS High-throu ghput kit."

    issues = spell_check_api._collect_split_word_issues(text)

    assert [issue["original_text"] for issue in issues] == ["High-throu ghput"]
    assert issues[0]["suggestion"] == "High-throughput"


def test_collect_split_word_issues_keeps_normal_modifier_phrases():
    text = "Displays real-time sequencing temperature and one-stop single-cell workflow."

    assert spell_check_api._collect_split_word_issues(text) == []


def test_collect_numeric_plural_issues_flags_prose_number_one():
    text = "Rotate the cartridge upright and swing downward 1 times to bring the reagent up."

    issues = spell_check_api._collect_numeric_plural_issues(text)

    assert [issue["original_text"] for issue in issues] == ["1 times"]
    assert issues[0]["suggestion"] == "1 time"


def test_collect_numeric_plural_issues_keeps_tables_sizes_and_invariant_nouns():
    text = (
        "Reaction Buffer 100 uL/tube\u00d71 months Cat. No.: 940-0029; "
        "size 4.1 inches; only 1 series is needed; repeat 1 time."
    )

    assert spell_check_api._collect_numeric_plural_issues(text) == []


def test_run_grammar_flags_compound_subject_but_not_coordinated_list():
    flagged = []
    spell_check_api.run_grammar("If no report is generated, and Task exception are displayed.", flagged)

    assert len(flagged) == 1

    listed = []
    spell_check_api.run_grammar(
        "Flow cell ID, Throughput, and Expiration date are automatically filled in.", listed
    )

    assert listed == []


def test_build_response_merges_same_start_duplicates():
    text = "Disgestive\n\nBuffer 250 μL"
    issues = [
        {
            "position": "0-18",
            "category": "拼写/用词错误",
            "source": "spellcheck",
            "original_text": "Disgestive\n\nBuffer",
            "description": "疑似错误词",
        },
        {
            "position": "0-10",
            "category": "拼写/用词错误",
            "source": "spellcheck",
            "original_text": "Disgestive",
            "description": "疑似错误词",
        },
    ]

    result = spell_check_api._build_response(text, issues)

    assert len(result["errors"]) == 1
    assert result["errors"][0]["word"] == "Disgestive"
