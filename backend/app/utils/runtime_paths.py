import shutil
from pathlib import Path


_BACKEND_DIR = Path(__file__).resolve().parents[2]
_REPO_ROOT = _BACKEND_DIR.parent
_RUNTIME_ROOT = Path.home() / ".smart-doc-platform"


def ensure_runtime_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def runtime_root() -> Path:
    return ensure_runtime_dir(_RUNTIME_ROOT)


def data_dir() -> Path:
    """与 backend 同级的数据目录（仓库根 / data）。"""
    return ensure_runtime_dir(_REPO_ROOT / "data")


def repo_db_path() -> Path:
    """旧位置：backend/app.db（保留作迁移源）。"""
    return _BACKEND_DIR / "app.db"


def runtime_db_path() -> Path:
    """旧位置：~/.smart-doc-platform/app.db（保留作迁移源）。"""
    return runtime_root() / "app.db"


def repo_data_db_path() -> Path:
    """新默认位置：与 backend 同级目录 data 下的 app.db。"""
    return data_dir() / "app.db"


def ensure_runtime_db_path() -> Path:
    """返回当前应使用的 SQLite 数据库路径。

    优先级：data/app.db（新默认） → 旧 backend/app.db → 旧 ~/.smart-doc-platform/app.db。
    旧库存在时自动复制迁移到 data/app.db，避免历史数据丢失。
    """
    primary = repo_data_db_path()
    if primary.exists():
        return primary
    for legacy in (repo_db_path(), runtime_db_path()):
        if legacy.exists():
            try:
                shutil.copy2(legacy, primary)
            except OSError:
                # 迁移失败不阻断启动，回退使用新位置空库
                pass
            return primary
    return primary


def runtime_knowledge_dir() -> Path:
    return ensure_runtime_dir(runtime_root() / "knowledge")


def runtime_memory_seed_dir() -> Path:
    return ensure_runtime_dir(runtime_root() / "knowledge-seed")


def repo_seed_dir() -> Path:
    return _BACKEND_DIR / "seed" / "knowledge"
