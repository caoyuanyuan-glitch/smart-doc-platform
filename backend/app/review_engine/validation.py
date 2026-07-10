import html
import re
from typing import Any

from app.review_engine.models import ValidationResult


_BASIS_MARKERS = (
    "release checklist and review basis",
    "技术文档常见错误清单",
    "说明书发布前自检 checklist",
    "中国rohs表格名称更新",
    "欧代标识更新",
    "海外官网地址变化",
)


def issue_value(issue: dict[str, Any], key: str, default: Any = "") -> Any:
    return issue.get(key, default) if isinstance(issue, dict) else getattr(issue, key, default)


def normalize_report_text(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().rstrip(".").lower()


def normalize_action_text(text: Any) -> str:
    text = str(text or "").strip()
    text = re.sub(r"^(?:建议(?:改为|替换为|统一为)?|修改建议|修改后)\s*[:：]?\s*", "", text)
    text = text.strip('`"“”‘’[]()（） ')
    text = re.sub(r"\s+", " ", text)
    return text.lower()


def normalize_noop_compare_text(text: Any) -> str:
    text = html.unescape(str(text or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = normalize_action_text(text)
    text = text.replace("×", "x").replace("℃", "°c")
    text = re.sub(r"[\"“”‘’`]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"[\s\.,;:!?，。；：！？、()（）\[\]【】{}<>\-–—_/]+", "", text)


def has_substantive_suggestion(original: Any, suggestion: Any) -> bool:
    if is_number_unit_space_correction(original, suggestion):
        return True
    return bool(normalize_noop_compare_text(original) != normalize_noop_compare_text(suggestion))


def is_number_unit_space_correction(original: Any, suggestion: Any) -> bool:
    original = str(original or "")
    suggestion = str(suggestion or "")
    compact = re.search(
        r"\b\d+(?:\.\d+)?(?:μl|ul|ml|ng|bp|kb|mb|gb|rpm|min|sec|s|h|°c)\b",
        original,
        re.IGNORECASE,
    )
    spaced = re.search(
        r"\b\d+(?:\.\d+)?\s+(?:μl|ul|ml|ng|bp|kb|mb|gb|rpm|min|sec|s|h|°c)\b",
        suggestion,
        re.IGNORECASE,
    )
    return bool(compact and spaced)


def ai_suggestion_violates_number_unit_spacing(original: Any, suggestion: Any) -> bool:
    original = str(original or "")
    suggestion = str(suggestion or "")
    compact_unit_pattern = re.compile(
        r"\b\d+(?:\.\d+)?(?:μl|ul|ml|ng|bp|kb|mb|gb|rpm|min|sec|s|h|°c)\b",
        re.IGNORECASE,
    )
    if compact_unit_pattern.search(suggestion):
        if compact_unit_pattern.search(original) and re.search(
            r"\b\d+(?:\.\d+)?\s+(?:μl|ul|ml|ng|bp|kb|mb|gb|rpm|min|sec|s|h|°c)\b",
            suggestion,
            re.IGNORECASE,
        ):
            return False
        return True
    if re.search(r"\b\d+(?:\.\d+)?\s*[×x]\s*(?:te|buffer)\b", suggestion, re.IGNORECASE):
        return not re.search(r"\b\d+(?:\.\d+)?\s+[×x]\s+(?:te|buffer)\b", suggestion, re.IGNORECASE)
    return False


def ai_suggestion_changes_numeric_values(original: Any, suggestion: Any) -> bool:
    original_numbers = re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?(?![A-Za-z])", str(original or ""))
    suggestion_numbers = re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?(?![A-Za-z])", str(suggestion or ""))
    if not original_numbers or not suggestion_numbers:
        return False
    return original_numbers != suggestion_numbers


def ai_suggestion_changes_protected_meaning(original: Any, suggestion: Any) -> bool:
    original = normalize_report_text(original)
    suggestion = normalize_report_text(suggestion)
    if ai_suggestion_changes_numeric_values(original, suggestion):
        return True
    if re.search(r"\bplate\b", original, re.IGNORECASE) and re.search(r"\badapter\s+plate\b", suggestion, re.IGNORECASE) and "adapter plate" not in original:
        return True
    protected_replacements = [
        ("user-supplied", "supplier provided"),
        ("place at rt", "store at rt"),
        ("thaw at rt", "thaw at room temperature"),
        ("not for use in diagnostic procedures", "for in vitro diagnostic use"),
        ("fragmentase", "enzyme"),
        ("and so on", "and so forth"),
        ("and so on", "etc"),
        ("use it with the corresponding kit", "use it along with the corresponding kit"),
        ("dna clean beads", "magnetic beads"),
        ("ad ligase", "avidin ligase"),
        ("en-te", "etoh"),
        ("udb pf adapter kit", "udb pf adapter kits"),
        ("for research use only", "for research use only. not for use in diagnostic procedures"),
    ]
    for left, right in protected_replacements:
        if left in original and right in suggestion and left not in suggestion:
            return True
    if re.search(r"\b(?:user-supplied|customer-supplied|supplier|provided|store|place|thaw|incubate|ligase|beads|buffer|adapter|kit)\b", original, re.IGNORECASE):
        original_terms = set(re.findall(r"[a-z][a-z0-9-]{2,}", original.lower()))
        suggestion_terms = set(re.findall(r"[a-z][a-z0-9-]{2,}", suggestion.lower()))
        changed_terms = original_terms - suggestion_terms
        added_terms = suggestion_terms - original_terms
        if changed_terms and added_terms and len(changed_terms | added_terms) >= 2:
            return True
    return False


def validate_ai_issue_candidate(issue: dict[str, Any], content: str) -> ValidationResult:
    original = normalize_report_text(issue_value(issue, "original_text", ""))
    suggestion = normalize_report_text(issue_value(issue, "suggestion", ""))
    description = normalize_report_text(issue_value(issue, "description", ""))
    rule = normalize_report_text(issue_value(issue, "rule", ""))
    chapter = normalize_report_text(issue_value(issue, "chapter", ""))
    audit_basis = normalize_report_text(issue_value(issue, "audit_basis", ""))
    combined = " ".join([original, suggestion, description, rule, chapter, audit_basis])
    content_norm = normalize_report_text(content)

    if not original:
        return ValidationResult(False, "missing_original_text")
    if not suggestion and not description:
        return ValidationResult(False, "missing_suggestion_and_description")
    if "此处原文已正确" in combined or "无需修改" in combined:
        return ValidationResult(False, "explicit_no_change")
    if any(marker in combined for marker in _BASIS_MARKERS):
        return ValidationResult(False, "audit_basis_leak")
    if original not in content_norm:
        return ValidationResult(False, "original_text_not_found")
    if suggestion and not has_substantive_suggestion(original, suggestion):
        return ValidationResult(False, "noop_suggestion")
    if suggestion and ai_suggestion_violates_number_unit_spacing(original, suggestion):
        return ValidationResult(False, "number_unit_spacing_regression")
    if suggestion and ai_suggestion_changes_protected_meaning(original, suggestion):
        return ValidationResult(False, "protected_meaning_changed")
    return ValidationResult(True, "accepted")


def filter_ai_issues_without_document_evidence(issues: list[dict[str, Any]], content: str) -> tuple[list[dict[str, Any]], dict[str, int]]:
    filtered: list[dict[str, Any]] = []
    dropped_by_reason: dict[str, int] = {}
    for issue in issues:
        if str(issue_value(issue, "source", "") or "").lower() != "ai":
            filtered.append(issue)
            continue
        result = validate_ai_issue_candidate(issue, content)
        if result.accepted:
            filtered.append(issue)
            continue
        dropped_by_reason[result.reason] = dropped_by_reason.get(result.reason, 0) + 1
    return filtered, dropped_by_reason
