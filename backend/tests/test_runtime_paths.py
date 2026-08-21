from pathlib import Path

from app.utils import runtime_paths


def test_runtime_db_path_prefers_repo_database(monkeypatch, tmp_path):
    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    repo_db = backend_dir / "app.db"
    repo_db.write_text("db", encoding="utf-8")

    monkeypatch.setattr(runtime_paths, "_BACKEND_DIR", backend_dir)
    monkeypatch.setattr(runtime_paths, "_RUNTIME_ROOT", tmp_path / "runtime")

    assert runtime_paths.runtime_db_path() == repo_db


def test_runtime_db_path_falls_back_to_runtime_directory(monkeypatch, tmp_path):
    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    runtime_root = tmp_path / "runtime"

    monkeypatch.setattr(runtime_paths, "_BACKEND_DIR", backend_dir)
    monkeypatch.setattr(runtime_paths, "_RUNTIME_ROOT", runtime_root)

    assert runtime_paths.runtime_db_path() == runtime_root / "app.db"
