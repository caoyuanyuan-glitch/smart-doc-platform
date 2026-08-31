"""Single authority for figure/table/section cross-reference checks."""

from __future__ import annotations

import json
import re
from collections import defaultdict


TARGET_FOUND = "target_found"
TARGET_NOT_FOUND = "target_not_found"
TARGET_NOT_PARSED = "target_not_parsed"
TARGET_VISUAL_ONLY = "target_visual_only"
TARGET_AMBIGUOUS = "target_ambiguous"

_FIGURE_CAPTION_RE = re.compile(r"(?im)^\s*(?:Figure|Fig\.?|图)\s*(\d+)\b[^\n]{0,120}")
_TABLE_CAPTION_RE = re.compile(r"(?im)^\s*(?:Table|表)\s*(\d+)\b[^\n]{0,120}")
_SECTION_CAPTION_RE = re.compile(r"(?m)^\s*(\d+(?:\.\d+)*)[\.)]?\s+[A-Z\u4e00-\u9fff][^\n]{2,}")
_FIGURE_REF_RE = re.compile(r"(?i)(?:Figure|Fig\.?|图)\s*(\d+)")
_TABLE_REF_RE = re.compile(r"(?i)(?:Table|表)\s*(\d+)")
_HEADING_PREFIX = re.compile(r"(?i)^(Figure|Fig\.?|图|Table|表)\s*")


def _encode_position(start: int, end: int, **meta) -> str:
    payload = {"start": start, "end": end, "area": meta.pop("area", "正文")}
    payload.update({key: value for key, value in meta.items() if value not in (None, "", [], {})})
    return json.dumps(payload, ensure_ascii=False)


def _is_caption_line(text: str, match: re.Match) -> bool:
    line_start = text.rfind("\n", 0, match.start()) + 1
    line_end = text.find("\n", match.start())
    if line_end < 0:
        line_end = len(text)
    line = text[line_start:line_end].strip()
    return bool(_HEADING_PREFIX.match(line))


def _chapter_at(text: str, offset: int) -> str:
    prefix = text[: max(0, offset)]
    headings = re.findall(r"(?m)^(第[一二三四五六七八九十百千0-9]+[章节篇部][^\n]{0,40}|\d+(?:\.\d+){0,3}\s+[^\n]{2,40})", prefix)
    return str(headings[-1]).strip()[:80] if headings else ""


def _page_at(text: str, offset: int) -> int:
    return text[: max(0, offset)].count("\f") + 1


def _label_variants(ref_type: str, ref_id: str) -> list[str]:
    if ref_type == "figure":
        return [f"Figure {ref_id}", f"Fig. {ref_id}", f"Fig {ref_id}", f"图{ref_id}", f"图 {ref_id}"]
    if ref_type == "table":
        return [f"Table {ref_id}", f"表{ref_id}", f"表 {ref_id}"]
    return [f"Section {ref_id}", f"章节 {ref_id}"]


def build_reference_index(text: str, *, visual_targets: dict | None = None, parsed: bool = True) -> dict:
    source = str(text or "")
    visual_targets = visual_targets or {}
    index = {"figure": {}, "table": {}, "section": {}}

    def add_target(ref_type: str, ref_id: str, match: re.Match, layer: str):
        entry = index[ref_type].setdefault(ref_id, {
            "reference_type": ref_type,
            "reference_id": ref_id,
            "label_variants": _label_variants(ref_type, ref_id),
            "caption_text": match.group(0).strip()[:180],
            "page": _page_at(source, match.start()),
            "chapter": _chapter_at(source, match.start()),
            "source_layer": layer,
            "confidence": 90,
            "status": TARGET_FOUND,
        })
        if layer == "pdf_visual_layer" and entry.get("source_layer") == "docx":
            entry["source_layer"] = "both"
        elif layer == "docx" and entry.get("source_layer") == "pdf_visual_layer":
            entry["source_layer"] = "both"

    if parsed:
        for match in _FIGURE_CAPTION_RE.finditer(source):
            add_target("figure", match.group(1), match, "docx")
        for match in _TABLE_CAPTION_RE.finditer(source):
            add_target("table", match.group(1), match, "docx")
        for match in _SECTION_CAPTION_RE.finditer(source):
            add_target("section", match.group(1), match, "docx")

    for ref_type in ("figure", "table"):
        for ref_id in visual_targets.get(ref_type) or []:
            if ref_id in index[ref_type]:
                index[ref_type][ref_id]["source_layer"] = "both"
                continue
            index[ref_type][ref_id] = {
                "reference_type": ref_type,
                "reference_id": ref_id,
                "label_variants": _label_variants(ref_type, ref_id),
                "caption_text": "",
                "page": None,
                "chapter": "",
                "source_layer": "pdf_visual_layer",
                "confidence": 60,
                "status": TARGET_VISUAL_ONLY,
            }
    return index


def _collect_refs(text: str, pattern: re.Pattern, ref_type: str) -> list[dict]:
    items = []
    for match in pattern.finditer(text or ""):
        if _is_caption_line(text, match):
            continue
        items.append({
            "reference_type": ref_type,
            "reference_id": match.group(1),
            "original_text": match.group(0).strip(),
            "start": match.start(),
            "end": match.end(),
            "chapter": _chapter_at(text, match.start()),
            "page": _page_at(text, match.start()),
        })
    return items


def _issue_for_ref(ref: dict, status: str, *, rule_id: str, description: str, suggestion: str) -> dict:
    blocked = status in {TARGET_NOT_PARSED, TARGET_VISUAL_ONLY, TARGET_AMBIGUOUS}
    return {
        "severity": "general" if blocked else "serious",
        "category": "引用完整性",
        "rule": rule_id,
        "chapter": ref.get("chapter") or "",
        "original_text": ref.get("original_text") or "",
        "suggestion": suggestion,
        "description": description,
        "audit_basis": "引用完整性检查",
        "confidence": 70 if blocked else 90,
        "source": "rule",
        "status": "blocked" if blocked else "pending",
        "target_status": status,
        "reference_type": ref.get("reference_type"),
        "reference_id": ref.get("reference_id"),
        "position": _encode_position(
            int(ref.get("start") or 0),
            int(ref.get("end") or 0),
            reference_type=ref.get("reference_type"),
            target=ref.get("original_text"),
            check_result=status,
            page=ref.get("page"),
        ),
    }


def _dedupe_key(issue: dict) -> tuple:
    return (
        str(issue.get("reference_type") or ""),
        str(issue.get("reference_id") or ""),
        str(issue.get("rule") or ""),
        str(issue.get("chapter") or ""),
        str(issue.get("page") or ""),
    )


def check_references(
    text: str,
    *,
    visual_targets: dict | None = None,
    parsed: bool = True,
    include_types: tuple[str, ...] = ("figure", "table"),
) -> list[dict]:
    source = str(text or "")
    index = build_reference_index(source, visual_targets=visual_targets, parsed=parsed)
    refs = []
    if "figure" in include_types:
        refs.extend(_collect_refs(source, _FIGURE_REF_RE, "figure"))
    if "table" in include_types:
        refs.extend(_collect_refs(source, _TABLE_REF_RE, "table"))
    if "section" in include_types:
        refs.extend(_collect_refs(source, re.compile(r"(?i)(?:Section|Chapter|章节)\s+(\d+(?:\.\d+)*)"), "section"))

    issues = []
    seen = set()
    pending_by_type = defaultdict(list)
    for ref in refs:
        ref_type = ref["reference_type"]
        ref_id = ref["reference_id"]
        entry = (index.get(ref_type) or {}).get(ref_id)
        if not parsed:
            status = TARGET_NOT_PARSED
        elif entry and entry.get("status") == TARGET_VISUAL_ONLY:
            status = TARGET_VISUAL_ONLY
        elif entry:
            status = TARGET_FOUND
        else:
            status = TARGET_NOT_FOUND
        if status == TARGET_FOUND:
            continue
        rule_id = "REF-002" if ref_type == "figure" else "REF-001"
        if ref_type == "section":
            rule_id = "REF-SECTION"
        if status == TARGET_NOT_FOUND:
            description = f"引用 {ref['original_text']}，但文档中未找到对应标题。"
            suggestion = f"建议补充 {ref['original_text']}，或删除该引用"
        elif status == TARGET_VISUAL_ONLY:
            description = f"引用 {ref['original_text']} 仅在视觉层可见，文本层未解析到标题。"
            suggestion = "请人工复核图题/表题是否存在后再确认缺失。"
        else:
            description = f"引用 {ref['original_text']} 的目标未能可靠解析。"
            suggestion = "请人工复核该交叉引用。"
        issue = _issue_for_ref(ref, status, rule_id=rule_id, description=description, suggestion=suggestion)
        key = _dedupe_key(issue)
        if key in seen:
            continue
        seen.add(key)
        pending_by_type[ref_type].append(issue)

    for ref_type, group in pending_by_type.items():
        missing = [item for item in group if item.get("target_status") == TARGET_NOT_FOUND]
        if len(missing) > 10:
            issues.append({
                "severity": "serious",
                "category": "引用完整性",
                "rule": "REF-INDEX-001",
                "chapter": "",
                "original_text": f"{ref_type} references",
                "suggestion": "引用索引异常，请复核解析结果后再逐条确认。",
                "description": f"同类 {ref_type} 引用异常超过 10 条，已聚合为待复核。",
                "audit_basis": "引用完整性检查",
                "confidence": 80,
                "source": "rule",
                "status": "blocked",
                "target_status": TARGET_AMBIGUOUS,
                "reference_details": missing,
            })
            issues.extend(item for item in group if item.get("target_status") != TARGET_NOT_FOUND)
        else:
            issues.extend(group)
    return issues
