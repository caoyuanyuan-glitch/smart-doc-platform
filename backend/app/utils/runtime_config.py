import os
from pathlib import Path

from dotenv import load_dotenv


_BOOTSTRAPPED = False
_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _non_empty(value):
    return bool(value and str(value).strip())


def _configured(value):
    text = str(value or "").strip()
    if not text:
        return False
    return "your-" not in text.lower()


def _load_env_file(path: Path, override: bool):
    if path.exists() and path.is_file():
        load_dotenv(path, override=override)


def bootstrap_runtime_env():
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return

    _load_env_file(_BACKEND_DIR / ".env", override=False)
    _load_env_file(_BACKEND_DIR / "runtime.env", override=True)
    _load_env_file(Path("/root/.codingmatrix/smart-doc-runtime.env"), override=False)
    _load_env_file(Path.home() / ".smart-doc-platform" / "runtime.env", override=True)

    custom_env_file = os.getenv("SMART_DOC_ENV_FILE") or os.getenv("ENV_FILE")
    if _non_empty(custom_env_file):
        _load_env_file(Path(custom_env_file).expanduser(), override=True)

    apply_ai_secret_aliases()
    _BOOTSTRAPPED = True


def _read_secret_file(path: Path):
    try:
        content = path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return content


def _resolve_secret_value(env_names, file_env_names=(), fallback_files=()):
    for env_name in env_names:
        value = os.getenv(env_name)
        if _configured(value):
            return str(value).strip()

    for env_name in file_env_names:
        file_path = os.getenv(env_name)
        if not _non_empty(file_path):
            continue
        secret = _read_secret_file(Path(file_path).expanduser())
        if _configured(secret):
            return secret

    for file_path in fallback_files:
        secret = _read_secret_file(Path(file_path).expanduser())
        if _configured(secret):
            return secret

    return ""


def apply_ai_secret_aliases():
    secrets_dir = os.getenv("AI_SECRETS_DIR", "").strip()
    fallback_files = [
        _BACKEND_DIR / "runtime.secrets" / "kimi_api_key",
        _BACKEND_DIR / "runtime.secrets" / "moonshot_api_key",
        Path("/run/secrets/kimi_api_key"),
        Path("/run/secrets/moonshot_api_key"),
        Path("/var/run/secrets/kimi_api_key"),
        Path("/var/run/secrets/moonshot_api_key"),
    ]
    if secrets_dir:
        secrets_path = Path(secrets_dir).expanduser()
        fallback_files = [
            secrets_path / "kimi_api_key",
            secrets_path / "moonshot_api_key",
            *fallback_files,
        ]

    kimi_key = _resolve_secret_value(
        env_names=("KIMI_API_KEY", "MOONSHOT_API_KEY"),
        file_env_names=("KIMI_API_KEY_FILE", "MOONSHOT_API_KEY_FILE"),
        fallback_files=fallback_files,
    )
    if _configured(kimi_key):
        os.environ["KIMI_API_KEY"] = kimi_key


def get_kimi_api_key():
    bootstrap_runtime_env()
    return os.getenv("KIMI_API_KEY", "").strip()
