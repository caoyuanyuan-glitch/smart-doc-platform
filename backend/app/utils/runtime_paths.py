from pathlib import Path


_BACKEND_DIR = Path(__file__).resolve().parents[2]
_RUNTIME_ROOT = Path.home() / ".smart-doc-platform"


def ensure_runtime_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def runtime_root() -> Path:
    return ensure_runtime_dir(_RUNTIME_ROOT)


def repo_db_path() -> Path:
    return _BACKEND_DIR / "app.db"


def runtime_db_path() -> Path:
    legacy_repo_db = repo_db_path()
    if legacy_repo_db.exists():
        return legacy_repo_db
    return runtime_root() / "app.db"


def runtime_knowledge_dir() -> Path:
    return ensure_runtime_dir(runtime_root() / "knowledge")


def runtime_memory_seed_dir() -> Path:
    return ensure_runtime_dir(runtime_root() / "knowledge-seed")


def repo_seed_dir() -> Path:
    return _BACKEND_DIR / "seed" / "knowledge"
