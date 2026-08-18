import os
from pathlib import Path

from app.utils.runtime_config import bootstrap_runtime_env


bootstrap_runtime_env()


BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_WHITELIST_FILE = BACKEND_DIR / 'app' / 'data' / 'whitelist.json'


def get_whitelist_file() -> Path:
    configured_path = os.getenv('WHITELIST_DATA_FILE', '').strip()
    if configured_path:
        return Path(configured_path).expanduser()
    return DEFAULT_WHITELIST_FILE


WHITELIST_FILE = get_whitelist_file()
