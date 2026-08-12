from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
WHITELIST_FILE = BACKEND_DIR / 'app' / 'data' / 'whitelist.json'
