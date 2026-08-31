"""PDF visual verification status helpers."""

from __future__ import annotations

from datetime import datetime, timezone
import os


VISUAL_STATUSES = {"verified", "rejected", "skipped", "failed", "provider_unavailable", "not_required"}


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
    if value == "not_required":
        return "not_required"
    if value == "confirm":
        return "verified"
    if value == "reject":
        return "rejected"
    if value in {"error", "failed"} or "render" in why:
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


def build_visual_verification(
    *,
    status: str,
    provider: str = "",
    attempts=1,
    error_code=None,
    verified_at=None,
    evidence_page=None,
    **extra,
) -> dict:
    mapped = map_visual_status(status, str(error_code or extra.get("reason") or ""))
    if mapped not in VISUAL_STATUSES:
        mapped = "skipped"
    attempt_count = attempts if isinstance(attempts, int) else len(attempts or [])
    payload = {
        "status": mapped,
        "provider": provider or "",
        "attempts": attempt_count,
        "error_code": error_code,
        "verified_at": verified_at or (datetime.now(timezone.utc).isoformat() if mapped == "verified" else None),
        "evidence_page": evidence_page,
        "visual_status": mapped,
    }
    if isinstance(attempts, list):
        payload["attempt_log"] = attempts
    payload.update({key: value for key, value in extra.items() if value is not None})
    return payload


def apply_visual_verification(issue: dict, verification: dict) -> dict:
    payload = dict(issue or {})
    visual = build_visual_verification(**{
        "status": verification.get("status") or verification.get("visual_status") or verification.get("decision") or "skipped",
        "provider": verification.get("provider") or "",
        "attempts": verification.get("attempts") if verification.get("attempts") is not None else 1,
        "error_code": verification.get("error_code") or verification.get("reason"),
        "verified_at": verification.get("verified_at"),
        "evidence_page": verification.get("evidence_page") or verification.get("page_number") or verification.get("page"),
        "decision": verification.get("decision"),
        "reason": verification.get("reason"),
        "is_extraction_artifact": verification.get("is_extraction_artifact"),
        "page_candidate": verification.get("page_candidate"),
    })
    payload["visual_verification"] = visual
    status = visual.get("status")
    if status == "verified" and str(payload.get("status") or "") == "confirmed":
        return payload
    if status in {"failed", "provider_unavailable", "skipped"} and str(payload.get("status") or "") not in {"false_positive", "ignored", "confirmed"}:
        payload["status"] = "pending" if status == "skipped" else "blocked"
    return payload
