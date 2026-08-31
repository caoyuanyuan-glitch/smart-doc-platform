"""PDF visual verification status helpers."""

from __future__ import annotations

import os

VISUAL_STATUSES = {"verified", "rejected", "skipped", "failed", "provider_unavailable"}


def visual_provider_chain() -> list[str]:
    raw = str(os.getenv("REVIEW_VISUAL_PROVIDERS", "kimi,qwen") or "")
    providers = []
    seen = set()
    for item in raw.split(","):
        name = item.strip().lower()
        if name and name not in seen:
            seen.add(name)
            providers.append(name)
    return providers or ["kimi"]


def map_visual_status(decision: str, reason: str = "") -> str:
    value = str(decision or "").strip().lower()
    why = str(reason or "").strip().lower()
    if value == "confirm":
        return "verified"
    if value == "reject":
        return "rejected"
    if value in {"error", "failed"}:
        return "failed"
    if value in {"skipped", "provider_unavailable"} or "unavailable" in why:
        if "unavailable" in why or value == "provider_unavailable":
            return "provider_unavailable"
        return "skipped"
    if value in VISUAL_STATUSES:
        return value
    return "skipped"


def is_verified_status(status: str) -> bool:
    return str(status or "").strip().lower() == "verified"
