"""Rulebook v1 false-positive matchers for the default review pipeline.

These patterns encode confirmed human rulings from
`.monkeycode/docs/误报过滤规则库_v1_20260821.md`. They drop only
structurally identifiable noise; they do not blanket-drop rule IDs.
"""

from __future__ import annotations

import re
from typing import Any


def _value(issue: Any, key: str, default: str = "") -> str:
    if isinstance(issue, dict):
        return str(issue.get(key, default) or default)
    return str(getattr(issue, key, default) or default)


def _blob(issue: Any) -> str:
    return " ".join(
        _value(issue, key)
        for key in (
            "original_text",
            "context",
            "suggestion",
            "description",
            "category",
            "audit_basis",
            "rule",
        )
    )


def rulebook_false_positive_reason(issue: Any) -> str | None:
    original = _value(issue, "original_text").strip()
    context = _value(issue, "context").strip()
    suggestion = _value(issue, "suggestion").strip()
    description = _value(issue, "description").strip()
    category = _value(issue, "category").strip()
    blob = _blob(issue)
    lowered = blob.casefold()
    complaint = " ".join([suggestion, description, category, _value(issue, "rule")])

    if "following status" in lowered:
        return "accepted_pdf_phrase_following_status"
    if "turn on it" in lowered:
        return "accepted_pdf_phrase_turn_on_it"

    if re.search(
        r"(?<![\w-])(?:https?://)?(?:www\.)?global-mgitech\.com(?:/|$|\s|[?&#])",
        f"{original} {context}",
        re.IGNORECASE,
    ) and re.search(r"官网|网址|url|术语一致|address", complaint, re.IGNORECASE):
        return "official_global_site"

    if re.search(r"https?://www\.completegenomics\.com", f"{original} {context}", re.IGNORECASE):
        return "complete_genomics_url"

    if _is_nested_list_numbering_noise(original, context, complaint):
        return "nested_ordered_list_numbering"

    if _is_body_trademark_repeat_noise(original, complaint):
        return "body_trademark_repeat"

    if _is_product_output_filename_noise(original, complaint):
        return "product_output_filename"

    if _is_english_email_only_contact_noise(original, context, complaint, blob):
        return "english_manual_email_only_contact"

    if re.search(r'["”’][\.,;:](?:\s|$)', blob) and re.search(
        r"引号|quote|标点|punctuation|句号",
        lowered,
        re.IGNORECASE,
    ):
        return "british_quote_punctuation_style"

    if re.search(r'[“‘][^\n]{0,120}["\']', blob) or re.search(r'["\'][^\n]{0,120}[”’]', blob):
        if re.search(r"引号|quote|混用|inconsistent", lowered, re.IGNORECASE):
            return "quote_mapping_artifact"

    if original and len(original) >= 4:
        compact_original = re.sub(r"\s+", "", original)
        compact_context = re.sub(r"\s+", "", context)
        if compact_original and compact_original * 2 in compact_context:
            return "duplicated_text_layer_artifact"
    if re.search(r"重复文本层|双层文本层|text\s+layer\s+repeat|duplicate(?:d)?\s+text\s+layer", lowered):
        return "duplicated_text_layer_artifact"

    if "this page is intentionally left blank" in lowered and re.search(
        r"blank|hyphen|dash|format|punct|删除|移除|空白页|连字符|破折号|格式|标点",
        lowered,
    ):
        return "intentionally_blank_page"

    if re.search(r"缺页码|missing\s+page\s+number|页码.*不符", lowered) and re.search(
        r"隔页|留白|intentionally|chapter\s+separator|章号",
        lowered,
    ):
        return "chapter_separator_page"

    if re.search(r"表\s*17|表\s*18|table\s*17|table\s*18", lowered) and re.search(
        r"标题完全相同|identical\s+title|凸阵式探头|声输出",
        lowered,
    ):
        return "same_probe_frequency_table_title"

    return None


def is_rulebook_false_positive(issue: Any) -> bool:
    return rulebook_false_positive_reason(issue) is not None


def _is_nested_list_numbering_noise(original: str, context: str, complaint: str) -> bool:
    if not re.search(r"格式不统一|numbering|编号差异|列表编号|list\s+style|ol\s+嵌套", complaint, re.IGNORECASE):
        return False
    evidence = f"{original} {context}"
    has_outer = bool(re.search(r"(?:^|\n)\s*\d+\.\s+\S", evidence)) or bool(re.search(r"\b\d+\.\s+\S", original))
    has_inner = bool(re.search(r"(?:^|\n)\s*\d+\)\s+\S", evidence)) or bool(re.fullmatch(r"\d+\)", original.strip()))
    mixed = bool(re.search(r"\d+\.", evidence) and re.search(r"\d+\)", evidence))
    return bool(has_inner or mixed or (has_outer and has_inner))


def _is_body_trademark_repeat_noise(original: str, complaint: str) -> bool:
    if re.search(r"声明页|trademark\s+statement|首次出现", complaint, re.IGNORECASE):
        return False
    if not re.search(r"商标|trademark|®|\bTM\b", complaint, re.IGNORECASE):
        return False
    return bool(re.search(r"正文|running\s+text|repeat|重复标注|再加", complaint, re.IGNORECASE))


def _is_product_output_filename_noise(original: str, complaint: str) -> bool:
    if not re.search(r"连写|文件名|filename|concatenat", complaint, re.IGNORECASE):
        return False
    return bool(re.search(r"\b[A-Z]{3,}[A-Za-z0-9]+\.(?:csv|tsv|xlsx|txt|json)\b", original))


def _is_english_email_only_contact_noise(original: str, context: str, complaint: str, _blob: str) -> bool:
    evidence = f"{original} {context}"
    if re.search(r"[\u4e00-\u9fff]", evidence):
        return False
    if not re.search(
        r"missing\s+(?:a\s+)?(?:phone|telephone)|lack(?:s|ing)?\s+(?:a\s+)?(?:phone|telephone)|contact\s+phone|telephone\s+number|缺(?:少|失)?(?:联系)?电话|联系电话",
        complaint,
        re.IGNORECASE,
    ):
        return False
    return bool(re.search(r"[\w.+-]+@[\w.-]+\.\w+", evidence))
