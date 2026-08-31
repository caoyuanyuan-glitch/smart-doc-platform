"""Audit-basis provenance for review results."""

from __future__ import annotations

import hashlib


def _signature(sections) -> str:
    rows = []
    for section in sections or []:
        if isinstance(section, dict):
            rows.append("||".join([
                str(section.get("label") or ""),
                str(section.get("text") or "")[:200],
                str(section.get("basis_type") or ""),
            ]))
        else:
            rows.append(str(section)[:200])
    raw = "\n".join(rows)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16] if raw else ""


def build_basis_trace(
    *,
    sections=None,
    es_available: bool = False,
    es_hit: bool = False,
    fallback: bool = False,
    fallback_reason: str = "",
) -> dict:
    labels = []
    for section in sections or []:
        if isinstance(section, dict):
            label = str(section.get("label") or "").strip()
        else:
            label = str(section or "").strip()
        if label:
            labels.append(label)
    if not sections:
        source = "none"
    elif es_hit:
        source = "es"
    elif fallback:
        source = "local_fallback"
    else:
        source = "local"
    return {
        "basis_source": source,
        "basis_signature": _signature(sections),
        "basis_labels": labels,
        "basis_version": "review-basis-v1",
        "es_available": bool(es_available),
        "fallback": bool(fallback),
        "fallback_reason": str(fallback_reason or ""),
    }
