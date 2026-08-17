from app import paths


def test_get_whitelist_file_uses_configured_server_path(monkeypatch, tmp_path):
    configured_file = tmp_path / "persistent" / "whitelist.json"
    monkeypatch.setenv("WHITELIST_DATA_FILE", str(configured_file))

    assert paths.get_whitelist_file() == configured_file


def test_get_whitelist_file_uses_default_for_local_development(monkeypatch):
    monkeypatch.delenv("WHITELIST_DATA_FILE", raising=False)

    assert paths.get_whitelist_file() == paths.DEFAULT_WHITELIST_FILE
