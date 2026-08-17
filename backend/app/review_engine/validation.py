import html
import re
from difflib import SequenceMatcher
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
    if "scientific research" in original and "clinical diagnosis" in original and re.search(r"\b(?:ruo|research\s+use\s+only)\b", suggestion, re.IGNORECASE):
        return True
    if re.search(r"\bdnb\b", original, re.IGNORECASE) and re.search(r"\bdna\s+nanoball", suggestion, re.IGNORECASE):
        return True
    if re.search(r"\bdnb\b", original, re.IGNORECASE) and re.search(r"\bdnbs\b|\bdnb\s+solution\b", suggestion, re.IGNORECASE):
        return True
    if "instructions for use" in original:
        if "instructions for use" not in suggestion:
            return True
        if re.search(r"\bifu\b|\bmanual\b|\binstruction\s+manual\b", suggestion, re.IGNORECASE):
            return True
    if re.search(r"\bplate\b", original, re.IGNORECASE) and re.search(r"\badapter\s+plate\b", suggestion, re.IGNORECASE) and "adapter plate" not in original:
        return True
    if "contact the technical support" in original and re.search(r"\bdefault\s+credentials\b|\bauthorized\s+login\b", suggestion, re.IGNORECASE):
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


def ai_suggestion_is_low_value_english_rewrite(original: Any, suggestion: Any) -> bool:
    original_text = normalize_report_text(original)
    suggestion_text = normalize_report_text(suggestion)
    if not original_text or not suggestion_text:
        return False

    def _strip_articles(text: str) -> list[str]:
        return [token for token in re.findall(r"[a-z0-9]+", text.lower()) if token not in {"a", "an", "the"}]

    original_tokens = _strip_articles(original_text)
    suggestion_tokens = _strip_articles(suggestion_text)
    if original_tokens and original_tokens == suggestion_tokens:
        return True

    original_token_set = {token for token in original_tokens if len(token) > 1}
    suggestion_token_set = {token for token in suggestion_tokens if len(token) > 1}
    filler_tokens = {
        "across",
        "and",
        "appears",
        "as",
        "at",
        "by",
        "column",
        "during",
        "from",
        "in",
        "into",
        "of",
        "on",
        "per",
        "remains",
        "securely",
        "surface",
        "to",
        "unit",
        "upon",
        "with",
        "without",
    }
    if original_token_set and suggestion_token_set:
        overlap = original_token_set & suggestion_token_set
        union = original_token_set | suggestion_token_set
        added = {token for token in (suggestion_token_set - original_token_set) if token not in filler_tokens}
        removed = {token for token in (original_token_set - suggestion_token_set) if token not in filler_tokens}
        if len(overlap) / max(len(union), 1) >= 0.6 and len(added | removed) <= 3:
            return True

    compact_original = " ".join(original_tokens)
    compact_suggestion = " ".join(suggestion_tokens)
    if compact_original and compact_suggestion:
        ratio = SequenceMatcher(None, compact_original, compact_suggestion).ratio()
        if ratio >= 0.72 and len((original_token_set ^ suggestion_token_set) - filler_tokens) <= 4:
            return True

    if original_text.startswith("ensure that ") and suggestion_text.startswith("ensure that "):
        shared = set(original_tokens) & set(suggestion_tokens)
        total = max(len(set(original_tokens)), len(set(suggestion_tokens)), 1)
        if len(shared) / total >= 0.85:
            return True

    return False


def ai_suggestion_is_speculative_completion(original: Any, suggestion: Any) -> bool:
    original_text = normalize_report_text(original)
    suggestion_text = normalize_report_text(suggestion)
    if not original_text or not suggestion_text:
        return False
    if suggestion_text == original_text:
        return False
    if not suggestion_text.startswith(original_text):
        return False

    trailing_fragment = re.search(r"\b(?:of|to|with|for|by|into|from|been|is|are|was|were)$", original_text)
    if trailing_fragment and len(suggestion_text) >= len(original_text) + 8:
        return True

    if len(original_text) <= 40 and len(suggestion_text) >= len(original_text) * 2:
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
    no_issue_pattern = re.compile(
        r"此处原文已正确|无需修改|no\s+(?:issue|violation|change)\b|no\s+change\s+needed|"
        r"appears\s+valid|is\s+correct\b|email\s+is\s+correct|verify\s+if\s+this\s+is\s+the\s+correct",
        re.IGNORECASE,
    )
    if no_issue_pattern.search(combined):
        return ValidationResult(False, "explicit_no_change")
    if any(marker in combined for marker in _BASIS_MARKERS):
        return ValidationResult(False, "audit_basis_leak")
    if original not in content_norm:
        return ValidationResult(False, "original_text_not_found")
    start = content_norm.find(original)
    end = start + len(original)
    if original[:1].isalpha() and start > 0 and content_norm[start - 1:start].isalpha():
        return ValidationResult(False, "truncated_word_fragment")
    if original[-1:].isalpha() and end < len(content_norm) and content_norm[end:end + 1].isalpha():
        return ValidationResult(False, "truncated_word_fragment")
    if suggestion and not has_substantive_suggestion(original, suggestion):
        return ValidationResult(False, "noop_suggestion")
    if suggestion and ai_suggestion_violates_number_unit_spacing(original, suggestion):
        return ValidationResult(False, "number_unit_spacing_regression")
    if suggestion and ai_suggestion_changes_protected_meaning(original, suggestion):
        return ValidationResult(False, "protected_meaning_changed")
    if suggestion and ai_suggestion_is_speculative_completion(original, suggestion):
        return ValidationResult(False, "speculative_completion")
    if suggestion and ai_suggestion_is_low_value_english_rewrite(original, suggestion):
        return ValidationResult(False, "low_value_english_rewrite")
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
