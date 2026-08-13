from app.api import whitelist as whitelist_api
from app.utils import spell_checker as spell_checker_utils


def test_add_terms_to_whitelist_refreshes_runtime_spellcheck(monkeypatch):
    saved = {}

    monkeypatch.setattr(whitelist_api, "load_whitelist", lambda: {"terms": []})
    monkeypatch.setattr(whitelist_api, "save_whitelist", lambda data: saved.setdefault("data", data))
    monkeypatch.setattr(whitelist_api, "_refresh_spellchecker_whitelist", lambda: saved.setdefault("refreshed", True))

    added = whitelist_api.add_terms_to_whitelist(["Stereo-seq", "Stereo-seq", "STOmics"])

    assert [item["word"] for item in added] == ["Stereo-seq", "STOmics"]
    assert saved["refreshed"] is True
    assert [item["word"] for item in saved["data"]["terms"]] == ["Stereo-seq", "STOmics"]


def test_runtime_whitelist_terms_apply_to_spellcheck_across_formats(monkeypatch):
    monkeypatch.setattr(spell_checker_utils.spell.word_frequency, "load_words", lambda words: None)

    spell_checker_utils.add_runtime_whitelist_terms(["Oligo"])

    assert spell_checker_utils.is_whitelisted("Oligo") is True
    assert spell_checker_utils.is_whitelisted("oligo") is False


def test_add_terms_to_whitelist_preserves_case_variants(monkeypatch):
    saved = {}

    monkeypatch.setattr(whitelist_api, "load_whitelist", lambda: {"terms": [{"word": "RNAs"}]})
    monkeypatch.setattr(whitelist_api, "save_whitelist", lambda data: saved.setdefault("data", data))
    monkeypatch.setattr(whitelist_api, "_refresh_spellchecker_whitelist", lambda: saved.setdefault("refreshed", True))

    added = whitelist_api.add_terms_to_whitelist(["rnas", "RNAs", "RNas"])

    assert [item["word"] for item in added] == ["rnas", "RNas"]


def test_get_all_items_returns_words_in_sorted_order(monkeypatch):
    monkeypatch.setattr(whitelist_api, "load_whitelist", lambda: {
        "terms": [
            {"id": "2", "word": "beta", "category": "专业术语", "description": ""},
            {"id": "1", "word": "Alpha", "category": "专业术语", "description": ""},
        ]
    })

    items = whitelist_api.get_all_items()

    assert [item["word"] for item in items] == ["Alpha", "beta"]


def test_import_whitelist_preserves_case_sensitive_duplicates(monkeypatch):
    saved = {}

    monkeypatch.setattr(whitelist_api, "load_whitelist", lambda: {"terms": [{"word": "RNAs"}]})
    monkeypatch.setattr(whitelist_api, "save_whitelist", lambda data: saved.setdefault("data", data))
    monkeypatch.setattr(whitelist_api, "_refresh_spellchecker_whitelist", lambda: saved.setdefault("refreshed", True))

    items = [
        whitelist_api.WhitelistItem(word="RNAs", category="生化术语", description=""),
        whitelist_api.WhitelistItem(word="rnas", category="生化术语", description=""),
    ]

    result = __import__('asyncio').run(whitelist_api.import_whitelist(items))

    assert result["added_count"] == 1
    assert saved["data"]["terms"][-1]["word"] == "rnas"
