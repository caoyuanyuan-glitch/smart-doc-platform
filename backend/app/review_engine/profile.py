"""Document profile and rule applicability gating."""

from __future__ import annotations

import re

from app.review_engine.document_model import DocumentModel


ENGLISH_ONLY_RULES = {"ENG-CN-001"}
CHINESE_MIXED_RULES = {
    "CYY-CN-MIXED-001",
    "CYY-CN-MIXED-002",
    "CYY-CN-MIXED-003",
    "CYY-CN-MIXED-004",
    "CYY-CN-MIXED-005",
    "CYY-CN-MIXED-006",
    "CYY-CN-MIXED-007",
    "CYY-CN-MIXED-008",
}


def build_document_profile(content: str, *, file_type: str = "", language: str = "unknown", model: DocumentModel | None = None) -> dict:
    text = str(content or "")
    chinese = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if language in {"cn", "zh", "zh-CN"}:
        document_language = "zh-CN"
    elif language in {"en", "en-US"}:
        document_language = "en-US"
    elif chinese and latin and chinese > 20 and latin > 40:
        document_language = "mixed"
    elif chinese > latin:
        document_language = "zh-CN"
    elif latin > 0:
        document_language = "en-US"
    else:
        document_language = "unknown"
    page_count = text.count("\f") + 1 if text else 0
    chapter_count = len(model.headings) if model is not None else len(re.findall(r"(?m)^(?:第[一二三四五六七八九十0-9]+[章节]|[0-9]+(?:\.[0-9]+)*\s+\S)", text))
    source_format = "pdf" if str(file_type or "").lower() == "pdf" else "docx"
    return {
        "document_language": document_language,
        "document_type": model.document_type if model is not None else "unknown",
        "page_count": page_count,
        "chapter_count": chapter_count,
        "text_layer_quality": "ok" if len(text.strip()) > 40 else "poor",
        "visual_layer_available": source_format == "pdf",
        "source_format": source_format,
    }


def rule_not_applicable_reason(rule_id: str, profile: dict) -> str:
    language = str(profile.get("document_language") or "unknown")
    rule = str(rule_id or "").upper()
    if language == "unknown":
        return "rule_not_applicable_to_document_profile"
    if rule in ENGLISH_ONLY_RULES and language != "en-US":
        return "rule_not_applicable_to_document_profile"
    if rule in CHINESE_MIXED_RULES and language == "en-US":
        return "rule_not_applicable_to_document_profile"
    return ""


def enabled_rule_engines(*, snippet_review: bool = False, use_new_rules: bool = False, pipeline_mode: str = "") -> list[str]:
    engines = ["spelling_v1", "cn_xref_v2", "unit_format_v1"]
    if snippet_review:
        engines.append("snippet_content_v1")
        if (pipeline_mode or "staged") == "staged":
            engines.append("staged_pipeline_v1")
    if use_new_rules:
        engines.append("deterministic_v2")
    return engines


def apply_rule_gating(issues: list, profile: dict) -> tuple[list, dict]:
    kept = []
    skipped = 0
    blocked = 0
    for issue in issues or []:
        segment_language = str((issue or {}).get("segment_language") or "")
        reason = rule_not_applicable_reason(str(issue.get("rule") or ""), profile)
        if segment_language:
            if str(issue.get("rule") or "").upper() in ENGLISH_ONLY_RULES and segment_language != "en-US":
                reason = "rule_not_applicable_to_document_profile"
            elif str(issue.get("rule") or "").upper() in CHINESE_MIXED_RULES and segment_language == "en-US":
                reason = "rule_not_applicable_to_document_profile"
            else:
                reason = ""
        if not reason:
            kept.append(issue)
            continue
        language = segment_language or str(profile.get("document_language") or "unknown")
        if language == "unknown":
            issue = dict(issue)
            issue["status"] = "blocked"
            issue["rejected_reason"] = reason
            kept.append(issue)
            blocked += 1
            continue
        skipped += 1
    diagnostics = {
        "enabled_rule_issues": len(kept) - blocked,
        "skipped_rule_issues": skipped,
        "blocked_rule_issues": blocked,
    }
    return kept, diagnostics
