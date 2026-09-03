"""Minimal staged review pipeline for snippet audits.

Flow: rules -> A/B/C split -> limited AI windows -> evidence check -> adjudicate.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from app.review_engine.language_segments import (
    PROTECTED_LITERAL_RE,
    segment_text_by_language,
)


MAX_AI_WINDOWS = 20
MAX_HIGH_RISK_PER_PARAGRAPH = 1

DETERMINISTIC_PREFIXES = (
    "SPELL",
    "UNIT-",
    "CYY-CN-SPELL",
    "CYY-CN-UNIT",
    "CYY-CN-TYPO",
    "CYY-CN-REF-006",
    "CYY-CN-REF-007",
    "CYY-CN-REF-008",
    "HR",
    "PUNCT-",
    "DOC-SPACE-",
    "DOC-TM-",
)
AMBIGUOUS_MARKERS = (
    "GRAMMAR",
    "TERM",
    "CONSIST",
    "STYLE",
    "MIXED",
    "CYY-CN-GRAMMAR",
)
HIGH_RISK_RE = re.compile(
    r"\b(?:must|should|shall|do not|don't|only if|before|after)\b"
    r"|启动|停止|打开|关闭|继续|禁止|确认"
    r"|\d+(?:\.\d+)?\s*(?:°C|℃|rpm|μL|µL|uL|mL|min|h|小时|分钟)"
    r"|浓度|体积|转速|型号|版本"
    r"|如图|见表|章节|页码|Figure|Table"
    r"|步骤|失败|警告|caution|warning",
    re.IGNORECASE,
)
STYLE_ONLY_RE = re.compile(
    r"more (?:concise|readable)|style preference|更(?:简洁|通顺)|可读性|润色建议",
    re.IGNORECASE,
)
UNIT_TOKEN_RE = re.compile(
    r"\d+(?:\.\d+)?\s*(?:μL|µL|uL|mL|rpm|°C|℃|min|s|mm)",
    re.IGNORECASE,
)


def resolve_pipeline_mode(snippet_review: bool = False) -> str:
    raw = str(os.getenv("REVIEW_PIPELINE_MODE") or "").strip().lower()
    if not snippet_review:
        return "legacy"
    if raw in {"legacy", "staged"}:
        return raw
    return "staged"


def extract_protected_literals(text: str) -> list[str]:
    found = []
    seen = set()
    for match in PROTECTED_LITERAL_RE.finditer(str(text or "")):
        value = match.group(0)
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        found.append(value)
    return found


def _issue_get(issue: Any, key: str, default: Any = "") -> Any:
    if isinstance(issue, dict):
        return issue.get(key, default)
    return getattr(issue, key, default)


def _as_dict(issue: Any) -> dict[str, Any]:
    if isinstance(issue, dict):
        return dict(issue)
    if hasattr(issue, "to_mapping"):
        return issue.to_mapping()
    payload = {}
    for key in (
        "source", "rule", "category", "severity", "original_text", "suggestion",
        "description", "audit_basis", "confidence", "position", "chapter",
        "context", "status", "evidence", "start", "end", "paragraph_index",
    ):
        if hasattr(issue, key):
            payload[key] = getattr(issue, key)
    return payload


def parse_span(issue: Any, source_text: str = "") -> tuple[int, int]:
    start = _issue_get(issue, "start", None)
    end = _issue_get(issue, "end", None)
    try:
        if start is not None and end is not None and int(end) > int(start):
            return int(start), int(end)
    except (TypeError, ValueError):
        pass
    raw = _issue_get(issue, "position", "")
    data = {}
    if isinstance(raw, dict):
        data = raw
    else:
        text = str(raw or "").strip()
        if text.startswith("{"):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    data = parsed
            except Exception:
                data = {}
        else:
            match = re.match(r"(-?\d+)\s*-\s*(-?\d+)", text)
            if match:
                return int(match.group(1)), int(match.group(2))
    try:
        start_i = int(data.get("start", data.get("char_start", 0)) or 0)
        end_i = int(data.get("end", data.get("char_end", 0)) or 0)
        if end_i > start_i:
            return start_i, end_i
    except (TypeError, ValueError):
        pass
    original = str(_issue_get(issue, "original_text", "") or "")
    if original and source_text:
        found = source_text.find(original)
        if found >= 0:
            return found, found + len(original)
    return -1, -1


def rule_family(issue: Any) -> str:
    rule = str(_issue_get(issue, "rule", "") or "").upper()
    if rule.startswith("CYY-CN-"):
        parts = rule.split("-")
        return "-".join(parts[:3]) if len(parts) >= 3 else rule
    if "-" in rule:
        return rule.split("-", 1)[0]
    if rule.startswith("SPELL"):
        return "SPELL"
    category = str(_issue_get(issue, "category", "") or "").lower()
    if "spell" in category or "拼写" in category or "错别字" in category:
        return "SPELL"
    if "grammar" in category or "语法" in category:
        return "GRAMMAR"
    if "unit" in category or "单位" in category:
        return "UNIT"
    return rule or "OTHER"


def _has_evidence(issue: Any) -> bool:
    evidence = _issue_get(issue, "evidence", "")
    if isinstance(evidence, dict):
        evidence = evidence.get("text") or evidence.get("reason") or evidence.get("basis") or ""
    text = " ".join(
        str(item or "")
        for item in (
            evidence,
            _issue_get(issue, "audit_basis", ""),
            _issue_get(issue, "description", ""),
        )
    ).strip()
    return bool(text)


def is_deterministic_candidate(issue: Any) -> bool:
    payload = _as_dict(issue)
    rule = str(payload.get("rule") or "").upper()
    source = str(payload.get("source") or "").lower()
    original = str(payload.get("original_text") or "").strip()
    suggestion = str(payload.get("suggestion") or "").strip()
    if not original:
        return False
    if any(marker in rule for marker in AMBIGUOUS_MARKERS):
        return False
    if source in {"ai"}:
        return False
    if any(rule.startswith(prefix) or rule == prefix.rstrip("-") for prefix in DETERMINISTIC_PREFIXES):
        return True
    if source in {"rule", "spellcheck", "term"} and suggestion and _has_evidence(payload):
        if rule.startswith("ENG-CN-"):
            return True
    return False


def select_deterministic(rule_candidates: list) -> list[dict]:
    selected = []
    for issue in rule_candidates or []:
        if is_deterministic_candidate(issue):
            payload = _as_dict(issue)
            payload["candidate_class"] = "A"
            payload["source"] = payload.get("source") or "rule"
            if not payload.get("status"):
                payload["status"] = "confirmed"
            selected.append(payload)
    return selected


def select_ai_candidates(rule_candidates: list) -> list[dict]:
    selected = []
    for issue in rule_candidates or []:
        if is_deterministic_candidate(issue):
            continue
        payload = _as_dict(issue)
        payload["candidate_class"] = "B"
        payload["source"] = payload.get("source") or "rule"
        payload["status"] = payload.get("status") or "pending"
        selected.append(payload)
    return selected


def is_high_risk_text(text: str) -> bool:
    return bool(HIGH_RISK_RE.search(str(text or "")))


def select_high_risk_spans(segments: list[dict], rule_candidates: list, source_text: str = "") -> list[dict]:
    occupied = []
    for issue in rule_candidates or []:
        start, end = parse_span(issue, source_text)
        if end > start:
            occupied.append((start, end, int(_issue_get(issue, "paragraph_index", 0) or 0)))
    per_paragraph: dict[int, int] = {}
    spans = []
    for segment in segments or []:
        text = str(segment.get("text") or "")
        if not is_high_risk_text(text):
            continue
        start = int(segment.get("start") or 0)
        end = int(segment.get("end") or (start + len(text)))
        paragraph_index = int(segment.get("paragraph_index") or 0)
        if any(not (end <= occ[0] or start >= occ[1]) for occ in occupied):
            continue
        if per_paragraph.get(paragraph_index, 0) >= MAX_HIGH_RISK_PER_PARAGRAPH:
            continue
        per_paragraph[paragraph_index] = per_paragraph.get(paragraph_index, 0) + 1
        spans.append({
            "candidate_class": "C",
            "source": "risk",
            "rule": "HIGH-RISK-SPAN",
            "rule_family": "RISK",
            "original_text": text.strip(),
            "text": text,
            "start": start,
            "end": end,
            "paragraph_index": paragraph_index,
            "language": segment.get("language") or "unknown",
            "status": "pending",
        })
    return spans


def _segment_by_index(segments: list[dict], index: int) -> dict | None:
    if 0 <= index < len(segments):
        return segments[index]
    return None


def merge_context_windows(
    items: list[dict],
    segments: list[dict],
    source_text: str = "",
    max_windows: int = MAX_AI_WINDOWS,
    context_before: int = 1,
    context_after: int = 1,
) -> list[dict]:
    windows = []
    seen = set()
    for item in items or []:
        start, end = parse_span(item, source_text)
        if end <= start:
            start = int(item.get("start") or 0)
            end = int(item.get("end") or 0)
        if end <= start:
            continue
        seg_index = 0
        for index, segment in enumerate(segments or []):
            if int(segment.get("start") or 0) <= start < int(segment.get("end") or 0):
                seg_index = index
                break
        before = _segment_by_index(segments, seg_index - context_before)
        current = _segment_by_index(segments, seg_index) or {}
        after = _segment_by_index(segments, seg_index + context_after)
        window_start = int((before or current).get("start") or start)
        window_end = int((after or current).get("end") or end)
        if source_text:
            window_text = source_text[window_start:window_end]
        else:
            window_text = str(current.get("text") or item.get("text") or item.get("original_text") or "")
        key = (window_start, window_end, window_text)
        if key in seen:
            continue
        seen.add(key)
        windows.append({
            "language": current.get("language") or item.get("language") or "unknown",
            "document_type": "technical_manual",
            "text": window_text,
            "context_before": str((before or {}).get("text") or ""),
            "context_after": str((after or {}).get("text") or ""),
            "protected_literals": extract_protected_literals(window_text),
            "rule_candidates": [{
                "rule_family": rule_family(item),
                "reason": str(item.get("description") or item.get("audit_basis") or item.get("rule") or ""),
            }],
            "start": window_start,
            "end": window_end,
            "paragraph_index": int(current.get("paragraph_index") or item.get("paragraph_index") or 0),
            "candidate_class": item.get("candidate_class") or "B",
        })
        if len(windows) >= max_windows:
            break
    return windows


def _original_in_span(original: str, source_text: str, start: int, end: int) -> bool:
    if not original:
        return False
    if 0 <= start < end <= len(source_text):
        slice_text = source_text[start:end]
        if original in slice_text or slice_text in original:
            return True
    return original in source_text


def validate_ai_evidence(
    ai_results: list,
    source_text: str,
    segments: list[dict] | None = None,
    protected_literals: list[str] | None = None,
) -> list[dict]:
    protected = protected_literals if protected_literals is not None else extract_protected_literals(source_text)
    validated = []
    for raw in ai_results or []:
        payload = _as_dict(raw)
        original = str(payload.get("original_text") or "").strip()
        suggestion = str(payload.get("suggestion") or "").strip()
        evidence = payload.get("evidence") or payload.get("audit_basis") or payload.get("description") or ""
        if isinstance(evidence, dict):
            evidence = evidence.get("text") or evidence.get("reason") or ""
        start, end = parse_span(payload, source_text)
        if payload.get("source_start") is not None:
            try:
                start = int(payload.get("source_start"))
                end = int(payload.get("source_end") or end)
            except (TypeError, ValueError):
                pass
        span_ok = _original_in_span(original, source_text, start, end) if original else False
        if original and start < 0:
            found = source_text.find(original)
            if found >= 0:
                start, end = found, found + len(original)
                span_ok = True
        status = str(payload.get("status") or "confirmed").lower()
        if payload.get("is_error") is False:
            status = "ignored"
        if not str(evidence or "").strip():
            status = "pending"
        if original and not span_ok:
            status = "pending"
            payload["location_quality"] = "unavailable"
        else:
            payload["location_quality"] = payload.get("location_quality") or ("exact" if span_ok else "unverified")
        if suggestion and any(token in original and token not in suggestion for token in protected):
            status = "pending"
            payload["rejected_reason"] = "protected_literal"
        if STYLE_ONLY_RE.search(str(evidence)) or STYLE_ONLY_RE.search(suggestion):
            status = "pending"
        if status == "confirmed" and not str(evidence or "").strip():
            status = "pending"
        payload["source"] = "ai"
        payload["status"] = status
        payload["start"] = start
        payload["end"] = end
        payload["evidence"] = str(evidence or "")
        if start >= 0 and end > start:
            payload["position"] = f"{start}-{end}"
        validated.append(payload)
    return validated


def _unit_signature(text: str) -> str:
    match = UNIT_TOKEN_RE.search(str(text or ""))
    return re.sub(r"\s+", "", match.group(0).lower()) if match else ""


def _spans_overlap(left: tuple[int, int], right: tuple[int, int]) -> bool:
    if left[1] <= left[0] or right[1] <= right[0]:
        return False
    return not (left[1] <= right[0] or right[1] <= left[0])


def adjudicate_and_deduplicate(
    confirmed_rules: list,
    validated_ai_results: list,
    ambiguous_rules: list | None = None,
) -> list[dict]:
    finals: list[dict] = []

    def append_unique(payload: dict) -> None:
        start, end = parse_span(payload)
        family = rule_family(payload)
        original = str(payload.get("original_text") or "")
        unit_sig = _unit_signature(original)
        for existing in finals:
            e_start, e_end = parse_span(existing)
            e_family = rule_family(existing)
            e_original = str(existing.get("original_text") or "")
            if unit_sig and _unit_signature(e_original) and unit_sig != _unit_signature(e_original):
                continue
            same_span = _spans_overlap((start, end), (e_start, e_end)) or (
                original and original == e_original and start == e_start and end == e_end
            )
            if same_span and (family == e_family or original == e_original):
                sources = {str(existing.get("source") or ""), str(payload.get("source") or "")}
                if "rule" in sources and "ai" in sources:
                    existing["source"] = "rule+ai"
                    if payload.get("is_error") is False or str(payload.get("status") or "") == "ignored":
                        existing["status"] = "pending"
                return
        finals.append(payload)

    for issue in confirmed_rules or []:
        payload = _as_dict(issue)
        payload["source"] = payload.get("source") or "rule"
        payload["status"] = payload.get("status") or "confirmed"
        payload["rule_family"] = rule_family(payload)
        append_unique(payload)

    for issue in ambiguous_rules or []:
        payload = _as_dict(issue)
        payload["source"] = payload.get("source") or "rule"
        if str(payload.get("status") or "") == "confirmed" and not _has_evidence(payload):
            payload["status"] = "pending"
        payload["status"] = payload.get("status") or "pending"
        payload["rule_family"] = rule_family(payload)
        append_unique(payload)

    for issue in validated_ai_results or []:
        payload = _as_dict(issue)
        payload["source"] = payload.get("source") or "ai"
        payload["rule_family"] = rule_family(payload)
        append_unique(payload)

    return finals


def run_staged_snippet_pipeline(
    text: str,
    rule_candidates: list,
    ai_results: list | None = None,
    ai_unavailable: bool = False,
) -> tuple[list[dict], dict]:
    source_text = str(text or "")
    segments = segment_text_by_language(source_text)
    normalized_rules = []
    for issue in rule_candidates or []:
        payload = _as_dict(issue)
        start, end = parse_span(payload, source_text)
        if end > start:
            payload["start"] = start
            payload["end"] = end
            payload["position"] = payload.get("position") or f"{start}-{end}"
        normalized_rules.append(payload)
    confirmed_rules = select_deterministic(normalized_rules)
    ambiguous_rules = select_ai_candidates(normalized_rules)
    risk_spans = select_high_risk_spans(segments, normalized_rules, source_text)
    windows = merge_context_windows(
        ambiguous_rules + risk_spans,
        segments,
        source_text=source_text,
    )
    validated_ai = []
    if not ai_unavailable:
        validated_ai = validate_ai_evidence(
            ai_results or [],
            source_text,
            segments,
            extract_protected_literals(source_text),
        )
    final_issues = adjudicate_and_deduplicate(confirmed_rules, validated_ai, ambiguous_rules)
    counts = {"confirmed": 0, "pending": 0, "ignored": 0, "blocked": 0}
    for issue in final_issues:
        start, end = parse_span(issue, source_text)
        if end > start:
            issue["start"] = start
            issue["end"] = end
            issue["position"] = issue.get("position") or f"{start}-{end}"
        status = str(issue.get("status") or "pending")
        if status in counts:
            counts[status] += 1
        else:
            counts["pending"] += 1
    diagnostics = {
        "pipeline_mode": "staged",
        "raw_rule_candidates": len(rule_candidates or []),
        "confirmed_rule_count": len(confirmed_rules),
        "ambiguous_rule_count": len(ambiguous_rules),
        "high_risk_span_count": len(risk_spans),
        "ai_window_count": len(windows),
        "ai_windows": windows,
        "high_risk_spans": [
            {"start": item["start"], "end": item["end"], "paragraph_index": item["paragraph_index"]}
            for item in risk_spans
        ],
        "ai_unavailable": bool(ai_unavailable),
        "ai_result_count": len(validated_ai),
        "final_issue_count": len(final_issues),
        "confirmed_count": counts["confirmed"],
        "pending_count": counts["pending"],
        "ignored_count": counts["ignored"],
        "blocked_count": counts["blocked"],
        "deterministic_skipped_ai": len(confirmed_rules) > 0 and not any(
            window.get("candidate_class") == "A" for window in windows
        ),
    }
    return final_issues, diagnostics
