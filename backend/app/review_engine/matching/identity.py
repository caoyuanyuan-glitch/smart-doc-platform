from __future__ import annotations


import json

from app.review_engine.matching.normalize import canonical_span
from app.review_engine.matching.protected_literals import protected_literal_signature
from app.review_engine.matching.structure import extract_structure


def _page_token(issue: dict) -> str:
    page = issue.get("page") or issue.get("page_number")
    if page not in (None, ""):
        return str(page)
    position = issue.get("position")
    if isinstance(position, dict):
        return str(position.get("page") or position.get("page_number") or "")
    text = str(position or "").strip()
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except Exception:
            return ""
        if isinstance(data, dict):
            return str(data.get("page") or data.get("page_number") or "")
    return ""


def issue_identity_key(issue: dict) -> tuple:
    original = str((issue or {}).get("original_text") or "")
    return (
        str((issue or {}).get("rule") or "").upper(),
        str((issue or {}).get("category") or (issue or {}).get("type") or ""),
        str((issue or {}).get("chapter") or "").strip(),
        _page_token(issue or {}),
        canonical_span(original),
        protected_literal_signature(original),
        extract_structure(original).get("signature") or "",
    )
