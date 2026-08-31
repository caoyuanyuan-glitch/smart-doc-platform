"""Audit-basis provenance for review results."""

from __future__ import annotations

from datetime import datetime, timezone
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
    review_id=None,
    issue_id=None,
    candidate_id=None,
    rule_id: str = "",
    basis_query: str = "",
    provider: str = "",
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
        "review_id": review_id,
        "issue_id": issue_id,
        "candidate_id": candidate_id,
        "rule_id": rule_id,
        "basis_query": basis_query,
        "basis_documents": labels,
        "provider": provider,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ok" if sections else "empty",
        "basis_source": source,
        "basis_signature": _signature(sections),
        "basis_labels": labels,
        "basis_version": "review-basis-v1",
        "es_available": bool(es_available),
        "fallback": bool(fallback),
        "fallback_reason": str(fallback_reason or ""),
    }
