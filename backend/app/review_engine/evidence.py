"""Structured evidence and position helpers for review issues."""

from __future__ import annotations

import json
import re

from app.review_engine.document_model import DocumentModel, locate_text


_COORD_RE = re.compile(r"^\s*\(?\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?")


def _decode_position(raw) -> dict:
    if isinstance(raw, dict):
        return dict(raw)
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def location_quality_from_position(position: dict, original_text: str = "") -> str:
    if _COORD_RE.match(str(original_text or "")):
        return "unverified"
    start = position.get("char_start", position.get("start"))
    end = position.get("char_end", position.get("end"))
    try:
        start_i = int(start)
        end_i = int(end)
    except (TypeError, ValueError):
        return "unavailable"
    if end_i <= start_i:
        return "unavailable"
    if position.get("bbox") and not position.get("bbox_verified"):
        return "unverified"
    return "verified" if position.get("chapter") or start_i >= 0 else "unverified"


def enrich_issue_evidence(issue: dict, model: DocumentModel | None = None, source_format: str = "docx") -> dict:
    payload = dict(issue or {})
    original = str(payload.get("original_text") or "").strip()
    position = _decode_position(payload.get("position"))
    located = locate_text(model, original) if model is not None else None
    if located:
        if str(source_format or "").startswith("docx"):
            position["chapter"] = located["chapter"] or payload.get("chapter") or position.get("chapter") or ""
            position["paragraph_index"] = located["paragraph_index"]
            position["char_start"] = located["char_start"]
            position["char_end"] = located["char_end"]
            position["source"] = located["source"]
            position.pop("bbox", None)
        else:
            position.setdefault("chapter", located["chapter"] or payload.get("chapter") or "")
            position.setdefault("paragraph_index", located["paragraph_index"])
            position.setdefault("char_start", located["char_start"])
            position.setdefault("char_end", located["char_end"])
            position.setdefault("source", located["source"])
        if not payload.get("chapter"):
            payload["chapter"] = located["chapter"]
    position.setdefault("page", position.get("page_number") or position.get("page"))
    position.setdefault("chapter", payload.get("chapter") or "")
    position.setdefault("source", source_format)
    quality = location_quality_from_position(position, original)
    payload["source_format"] = payload.get("source_format") or source_format
    payload["evidence"] = {
        "text": original,
        "source_layer": "docx" if source_format.startswith("docx") else "pdf_text_layer",
        "location_quality": quality,
    }
    payload["position_object"] = {
        "page": position.get("page"),
        "chapter": position.get("chapter") or "",
        "paragraph_index": position.get("paragraph_index"),
        "char_start": position.get("char_start", position.get("start")),
        "char_end": position.get("char_end", position.get("end")),
        "bbox": position.get("bbox"),
        "source": position.get("source") or source_format,
    }
    payload["legacy_position"] = payload.get("position")
    if quality in {"unverified", "unavailable", "ambiguous"} and str(payload.get("status") or "") not in {"confirmed", "false_positive", "ignored"}:
        if str(payload.get("severity") or "").lower() in {"fatal", "serious"}:
            payload["status"] = "blocked"
    return payload
