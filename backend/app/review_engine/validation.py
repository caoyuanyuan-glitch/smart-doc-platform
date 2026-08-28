import html
import re
from difflib import SequenceMatcher
from typing import Any

from app.review_engine.models import ValidationResult
from app.review_engine.pipeline import _log_pipeline_drop


_BASIS_MARKERS = (
    "release checklist and review basis",
    "技术文档常见错误清单",
    "说明书发布前自检 checklist",
    "中国rohs表格名称更新",
    "欧代标识更新",
    "海外官网地址变化",
)

_AGGRESSIVE_TEMPLATE_WORDS = frozenset({
    "ruo", "patient", "management", "diagnostic", "purposes", "intended",
    "verified", "verify", "corresponding", "appropriate", "properly",
    "seated", "underside", "center", "printed", "label", "remains",
    "remain", "quality", "first", "repeat", "disconnection", "gentle",
    "heard", "cracking", "carefully", "ensure", "clinical", "any",
})

_MEANINGFUL_LOCAL_REWRITE_PAIRS = {
    frozenset({"this", "these"}),
    frozenset({"that", "those"}),
    frozenset({"is", "are"}),
    frozenset({"was", "were"}),
    frozenset({"has", "have"}),
    frozenset({"does", "do"}),
    frozenset({"describe", "describes"}),
    frozenset({"click", "tap"}),
}


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


def _strip_leading_bullet_marker(text: Any) -> str:
    normalized = normalize_report_text(text)
    return re.sub(r"^(?:[y•·*\-]|\(?[a-z0-9]\)|[a-z0-9][\)\.])\s+", "", normalized, count=1)


def normalize_noop_compare_text(text: Any) -> str:
    text = html.unescape(str(text or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = normalize_action_text(text)
    text = text.replace("×", "x").replace("℃", "°c")
    text = re.sub(r"[\"“”‘’`]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"[\s\.,;:!?，。；：！？、()（）\[\]【】{}<>\-–—_/]+", "", text)


def is_whitespace_only_correction(original: Any, suggestion: Any) -> bool:
    """仅空格差异（补缺失空格/删多余空格）属于实质性修复。

    例："temperature.For these" -> "temperature. For these"（句号后缺空格）、
    "High-throu ghput" -> "High-throughput"（词中多余空格）。
    这类建议与原文去掉空白后完全一致，但空格本身就是问题所在，不能按 no-op 丢弃。
    """
    a = str(original or "")
    b = str(suggestion or "")
    if not a or not b or a == b:
        return False
    return re.sub(r"\s+", "", a) == re.sub(r"\s+", "", b)


def has_substantive_suggestion(original: Any, suggestion: Any) -> bool:
    if is_number_unit_space_correction(original, suggestion):
        return True
    if is_whitespace_only_correction(original, suggestion):
        return True
    if is_duplicate_punctuation_reduction(original, suggestion):
        return True
    return bool(normalize_noop_compare_text(original) != normalize_noop_compare_text(suggestion))


def is_duplicate_punctuation_reduction(original: Any, suggestion: Any) -> bool:
    """删除连续重复标点属于实质性修复（如 ',,' -> ','、'..' -> '.'）。

    noop 比较会剥掉所有标点，导致 ',,' 与 ',' 归一化后均为空串而被误判为
    no-op；此处显式判定"建议 == 原文去掉重复标点"来放行此类修复。
    """
    a = str(original or "")
    b = str(suggestion or "")
    if not a or not b or a == b:
        return False
    if re.sub(r"\s+", "", a) == re.sub(r"\s+", "", b):
        return False
    reduced = re.sub(r"([,;:!?，。；：！？])\s*\1+", r"\1", a)
    reduced = re.sub(r"(?<!\.)\.\.(?!\.)", ".", reduced)
    return reduced == b.strip() or re.sub(r"\s+", "", reduced) == re.sub(r"\s+", "", b)


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
    if "系统内部已有" in original and re.search(r"外部系统|本平台内", suggestion):
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
    if "split barcode" in original and re.search(r"\byes\b.+\bselected\s+by\s+default\b|\bselected\s+by\s+default\b", suggestion, re.IGNORECASE):
        return True
    if "automatically filled in" in original and re.search(r"\bprevents?\s+proceeding\b|\bdisplays?\s+an\s+error\b|\bfails?\s+validation\b|\binvalid\s+or\s+expired\b", suggestion, re.IGNORECASE):
        return True
    if "local regulations and safety standards" in original and re.search(r"\bbiosafety\b|\bhazardous\s+waste\b|\binstitutional\b|\bnational\b|\bliquid/solid\s+waste\b|\bgenerated\s+during\s+sequencing\b|\blaboratory\s+safety\s+standards\b", suggestion, re.IGNORECASE):
        return True
    if "app library" in original and "app libraries" in suggestion:
        return True
    if "mixedly use" in original and re.search(r"\bmix(?:ed|ing)?\b", suggestion, re.IGNORECASE):
        return True
    if "do not centrifuge, vortex, or shake the tube" in original and re.search(r"\bshear\b|\baggregate\s+dnbs\b", suggestion, re.IGNORECASE):
        return True
    if "choose scheme interface" in original:
        if "choose scheme interface" not in suggestion:
            return True
        if "selected type" in original and "selected type" not in suggestion:
            return True
        if re.search(r"\bassay\s+type\b", suggestion, re.IGNORECASE):
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
        if changed_terms and added_terms and len(changed_terms) == len(added_terms):
            remaining_changed = set(changed_terms)
            paired = 0
            for added_term in added_terms:
                matched = None
                for changed_term in remaining_changed:
                    if _tokens_look_like_meaningful_fix_pair(changed_term, added_term):
                        matched = changed_term
                        break
                if matched is None:
                    break
                remaining_changed.remove(matched)
                paired += 1
            if paired == len(added_terms):
                return False
        if changed_terms and added_terms and len(changed_terms | added_terms) >= 2:
            return True
    return False


def ai_suggestion_is_low_value_english_rewrite(original: Any, suggestion: Any) -> bool:
    original_text = normalize_report_text(original)
    suggestion_text = normalize_report_text(suggestion)
    if not original_text or not suggestion_text:
        return False
    if is_whitespace_only_correction(original_text, suggestion_text):
        # 仅空格差异（补缺失空格/删多余空格）本身就是要修的问题，
        # 不能因 token 去空格后相同而判为低价值改写。
        return False
    if _is_localized_meaningful_english_fix(original_text, suggestion_text):
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


def ai_suggestion_is_low_value_cn_term_swap(original: Any, suggestion: Any) -> bool:
    original_text = normalize_report_text(original)
    suggestion_text = normalize_report_text(suggestion)
    if not original_text or not suggestion_text:
        return False

    low_value_pairs = [
        ("窗口", "对话框"),
    ]
    for left, right in low_value_pairs:
        if left in original_text and right in suggestion_text:
            collapsed_original = original_text.replace(left, "")
            collapsed_suggestion = suggestion_text.replace(right, "")
            if collapsed_original == collapsed_suggestion:
                return True
    return False


def ai_issue_is_low_value_ui_bracket_labeling(issue: dict[str, Any], original: str, suggestion: str, description: str) -> bool:
    issue_blob = " ".join([
        normalize_report_text(issue_value(issue, "rule", "")),
        normalize_report_text(issue_value(issue, "category", "")),
        description,
        suggestion,
    ])
    if not re.search(r"ui元素未按规范标注|缺少.?按钮.?二字|未说明其为按钮|button label|button word", issue_blob, re.IGNORECASE):
        return False
    if not re.search(r"(?:点击|单击|双击)【[^】]{1,24}】(?:[，,。；;\s]|$)", original):
        return False
    if re.search(r"【[^】]+】行的|【[^】]+】列的|【[^】]+】栏的|后方的\s*【|右侧的\s*【", original):
        return False
    return True


def _is_localized_meaningful_english_fix(original: Any, suggestion: Any) -> bool:
    original_tokens = re.findall(r"[a-z0-9']+", normalize_report_text(original))
    suggestion_tokens = re.findall(r"[a-z0-9']+", normalize_report_text(suggestion))
    original_set = {token for token in original_tokens if token not in {"a", "an", "the"}}
    suggestion_set = {token for token in suggestion_tokens if token not in {"a", "an", "the"}}
    added = suggestion_set - original_set
    removed = original_set - suggestion_set
    if not added or not removed or len(added) != len(removed) or len(added) > 2:
        return False

    remaining_removed = set(removed)
    for added_token in added:
        matched = None
        for removed_token in remaining_removed:
            if _tokens_look_like_meaningful_fix_pair(removed_token, added_token):
                matched = removed_token
                break
        if matched is None:
            return False
        remaining_removed.remove(matched)
    return True


def _tokens_look_like_meaningful_fix_pair(left: str, right: str) -> bool:
    if not left or not right or left == right:
        return False
    if frozenset({left, right}) in _MEANINGFUL_LOCAL_REWRITE_PAIRS:
        return True
    if left.rstrip("s") == right.rstrip("s") and abs(len(left) - len(right)) <= 2:
        return True
    if len(left) > 3 and len(right) > 3 and SequenceMatcher(None, left, right).ratio() >= 0.72:
        return True
    return False


def ai_suggestion_is_aggressive_rewrite(original: Any, suggestion: Any) -> bool:
    original_text = normalize_report_text(original)
    suggestion_text = normalize_report_text(suggestion)
    if not original_text or not suggestion_text or original_text == suggestion_text:
        return False
    if _is_localized_meaningful_english_fix(original_text, suggestion_text):
        return False

    def _tokens(text: str) -> set[str]:
        return {token for token in re.findall(r"[a-z][a-z0-9']*", text.lower()) if len(token) > 1}

    original_tokens = _tokens(original_text)
    suggestion_tokens = _tokens(suggestion_text)
    union = original_tokens | suggestion_tokens
    if not union:
        return False

    intersection = original_tokens & suggestion_tokens
    jaccard = len(intersection) / len(union)
    len_ratio = len(suggestion_text) / max(len(original_text), 1)
    diff_tokens = original_tokens ^ suggestion_tokens
    added = suggestion_tokens - original_tokens
    removed = original_tokens - suggestion_tokens

    if jaccard < 0.5 and 0.55 <= len_ratio <= 1.9:
        return True
    if jaccard < 0.55 and len_ratio < 0.72:
        return True

    template_hits = sum(1 for token in added if token in _AGGRESSIVE_TEMPLATE_WORDS)
    if len(diff_tokens) >= 5 and template_hits >= 1 and jaccard < 0.9:
        paired = 0
        for added_token in added:
            for removed_token in removed:
                if _tokens_look_like_meaningful_fix_pair(removed_token, added_token):
                    paired += 1
                    break
        if paired >= len(added):
            return False
        return True

    return False


def ai_suggestion_is_speculative_completion(original: Any, suggestion: Any) -> bool:
    original_text = normalize_report_text(original)
    suggestion_text = normalize_report_text(suggestion)
    if not original_text or not suggestion_text:
        return False
    if suggestion_text == original_text:
        return False
    stripped_original = _strip_leading_bullet_marker(original_text)
    stripped_suggestion = _strip_leading_bullet_marker(suggestion_text)
    if not suggestion_text.startswith(original_text) and not stripped_suggestion.startswith(stripped_original):
        return False

    baseline_original = stripped_original if stripped_suggestion.startswith(stripped_original) else original_text
    baseline_suggestion = stripped_suggestion if stripped_suggestion.startswith(stripped_original) else suggestion_text

    trailing_fragment = re.search(r"\b(?:of|to|with|for|by|into|from|been|is|are|was|were)$", baseline_original)
    if trailing_fragment and len(baseline_suggestion) >= len(baseline_original) + 8:
        return True

    if len(baseline_original) <= 40 and len(baseline_suggestion) >= len(baseline_original) * 2:
        return True

    return False


def ai_issue_is_visual_control_ambiguity(issue: dict[str, Any], original: str, suggestion: str, description: str) -> bool:
    if re.search(r"点击\s*[，,。]", original) and re.search(r"点击【[^】]+】", suggestion):
        return True

    issue_blob = " ".join([
        normalize_report_text(issue_value(issue, "rule", "")),
        normalize_report_text(issue_value(issue, "category", "")),
        description,
        suggestion,
    ])
    if not re.search(
        r"missing\s+(?:specific\s+)?(?:object|icon|button)|缺少.*?(?:按钮|图标|对象)|"
        r"(?:ui|交互元素).{0,12}缺失|图标丢失|ocr|控件名称|click|空白按钮|无语义|未指明具体按钮",
        issue_blob,
        re.IGNORECASE,
    ):
        return False

    evidence_text = " ".join([
        original,
        normalize_report_text(issue_value(issue, "context", "")),
    ])
    if not re.search(r"\b(?:icon|button|toolbar|menu)\b|图标|按钮|工具栏|菜单", evidence_text, re.IGNORECASE):
        if not re.search(r"点击\s*[，,。]|栏目?的文\s|右侧的文\s|【操作】[栏列]的\s", evidence_text):
            return False

    if re.search(r"【[^】]+】行的", evidence_text):
        return False

    if re.search(r"点击\s*[，,。]", original):
        return True

    if re.search(r"栏目?的文\s|右侧的文\s", evidence_text):
        return True

    if re.search(r"【操作】[栏列]的\s", evidence_text):
        return True

    return True


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
    if original == "reagent" and suggestion == "reagents" and "equipment, reagent, and consumbles" in content_norm:
        return ValidationResult(False, "protected_meaning_changed")
    if suggestion and ai_suggestion_is_aggressive_rewrite(original, suggestion):
        return ValidationResult(False, "aggressive_rewrite")
    if suggestion and ai_suggestion_is_speculative_completion(original, suggestion):
        return ValidationResult(False, "speculative_completion")
    if ai_issue_is_low_value_ui_bracket_labeling(issue, original, suggestion, description):
        return ValidationResult(False, "low_value_ui_bracket_labeling")
    if ai_issue_is_visual_control_ambiguity(issue, original, suggestion, description):
        return ValidationResult(False, "visual_control_ambiguity")
    if suggestion and ai_suggestion_is_low_value_cn_term_swap(original, suggestion):
        return ValidationResult(False, "low_value_cn_term_swap")
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
        _log_pipeline_drop(f"ai_evidence:{result.reason}", issue)
    return filtered, dropped_by_reason
