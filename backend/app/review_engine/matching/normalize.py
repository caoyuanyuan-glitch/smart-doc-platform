from __future__ import annotations

import re
import unicodedata


def normalize_text(text: str) -> str:
    value = unicodedata.normalize("NFKC", str(text or ""))
    value = value.replace("\u3000", " ")
    value = re.sub(r"[ \t]+", " ", value)
    return value.strip()


def canonical_span(text: str) -> str:
    return normalize_text(text).lower()
