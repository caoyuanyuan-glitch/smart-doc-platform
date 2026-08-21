from pathlib import Path

from app.utils import runtime_paths


def test_runtime_db_path_prefers_repo_database(monkeypatch, tmp_path):
    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    runtime_root = tmp_path / "runtime"

    monkeypatch.setattr(runtime_paths, "_BACKEND_DIR", backend_dir)
    monkeypatch.setattr(runtime_paths, "_RUNTIME_ROOT", runtime_root)

    assert runtime_paths.runtime_db_path() == runtime_root / "app.db"


def test_runtime_db_path_falls_back_to_runtime_directory(monkeypatch, tmp_path):
    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    runtime_root = tmp_path / "runtime"

    monkeypatch.setattr(runtime_paths, "_BACKEND_DIR", backend_dir)
    monkeypatch.setattr(runtime_paths, "_RUNTIME_ROOT", runtime_root)

    assert runtime_paths.runtime_db_path() == runtime_root / "app.db"


def test_ensure_runtime_db_path_migrates_legacy_repo_database(monkeypatch, tmp_path):
    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    runtime_root = tmp_path / "runtime"
    repo_db = backend_dir / "app.db"
    repo_db.write_text("legacy-db", encoding="utf-8")

    monkeypatch.setattr(runtime_paths, "_BACKEND_DIR", backend_dir)
    monkeypatch.setattr(runtime_paths, "_RUNTIME_ROOT", runtime_root)

    runtime_db = runtime_paths.ensure_runtime_db_path()

    assert runtime_db == runtime_root / "app.db"
    assert runtime_db.read_text(encoding="utf-8") == "legacy-db"


def test_ensure_runtime_db_path_keeps_existing_runtime_database(monkeypatch, tmp_path):
    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    runtime_root = tmp_path / "runtime"
    repo_db = backend_dir / "app.db"
    repo_db.write_text("legacy-db", encoding="utf-8")
    runtime_root.mkdir()
    runtime_db = runtime_root / "app.db"
    runtime_db.write_text("runtime-db", encoding="utf-8")

    monkeypatch.setattr(runtime_paths, "_BACKEND_DIR", backend_dir)
    monkeypatch.setattr(runtime_paths, "_RUNTIME_ROOT", runtime_root)

    assert runtime_paths.ensure_runtime_db_path() == runtime_db
    assert runtime_db.read_text(encoding="utf-8") == "runtime-db"
