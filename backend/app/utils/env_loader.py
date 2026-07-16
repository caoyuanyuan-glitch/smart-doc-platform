import os
from pathlib import Path

from dotenv import load_dotenv


def load_runtime_env() -> list[str]:
    """Load environment variables from repo and machine-level config files."""
    backend_dir = Path(__file__).resolve().parents[2]
    candidate_paths = [
        backend_dir / ".env",
        backend_dir / "runtime.env",
    ]

    explicit_env_file = os.getenv("SMART_DOC_ENV_FILE")
    if explicit_env_file:
        candidate_paths.append(Path(explicit_env_file).expanduser())

    home_dir = Path.home()
    candidate_paths.append(home_dir / ".smart-doc-platform" / "runtime.env")

    if os.name != "nt":
        candidate_paths.append(Path("/etc/smart-doc-platform/runtime.env"))

    loaded = []
    seen = set()
    for path in candidate_paths:
        normalized = str(path)
        if normalized in seen:
            continue
        seen.add(normalized)
        if path.exists():
            load_dotenv(path, override=True)
            loaded.append(normalized)

    if loaded:
        print(f"[env] Loaded runtime env files: {', '.join(loaded)}")
    return loaded
