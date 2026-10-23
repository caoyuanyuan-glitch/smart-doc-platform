from __future__ import annotations

import re

from app.review_engine.matching.normalize import normalize_text


_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
_UNIT_RE = re.compile(r"\b(?:ul|μl|ml|mol|mm|cm|kg|g|min|sec|rpm)\b", re.IGNORECASE)
_MODEL_RE = re.compile(r"\b[A-Z]{1,6}\d{1,4}[A-Z0-9-]{0,8}\b")
_NEGATION_RE = re.compile(r"(不|勿|禁止|不要|do not|don't|never)", re.IGNORECASE)


def extract_protected_literals(text: str) -> dict[str, list[str]]:
    value = normalize_text(text)
    return {
        "numbers": _NUMBER_RE.findall(value),
        "units": [item.lower() for item in _UNIT_RE.findall(value)],
        "models": _MODEL_RE.findall(value),
        "negations": [item.lower() for item in _NEGATION_RE.findall(value)],
    }


def protected_literal_signature(text: str) -> str:
    literals = extract_protected_literals(text)
    return "|".join(
        ",".join(literals[key]) for key in ("numbers", "units", "models", "negations")
    )


def protected_literal_diff(left: str, right: str) -> list[str]:
    a = extract_protected_literals(left)
    b = extract_protected_literals(right)
    diffs = []
    for key in a:
        if a[key] != b[key]:
            diffs.append(key)
    return diffs
