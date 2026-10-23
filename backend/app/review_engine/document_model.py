"""Structured document model for DOCX-primary content review."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
import re


_HEADING_RE = re.compile(
    r"^(?:#{1,6}\s+\S|第[一二三四五六七八九十百千0-9]+[章节篇部].*|\d+(?:\.\d+){0,4}\s+\S)",
)
_FIGURE_RE = re.compile(r"(?im)^\s*(?:Figure|Fig\.?|图)\s*(\d+)\b(.{0,120})")
_TABLE_RE = re.compile(r"(?im)^\s*(?:Table|表)\s*(\d+)\b(.{0,120})")


@dataclass
class TextSpan:
    text: str
    paragraph_index: int
    char_start: int
    char_end: int
    chapter: str = ""
    source_style: str = ""


@dataclass
class DocumentModel:
    source_format: str = "docx"
    document_language: str = "unknown"
    document_type: str = "unknown"
    fallback_reason: str = ""
    headings: list[TextSpan] = field(default_factory=list)
    paragraphs: list[TextSpan] = field(default_factory=list)
    tables: list[dict] = field(default_factory=list)
    figures: list[dict] = field(default_factory=list)
    cross_references: list[dict] = field(default_factory=list)
    page_breaks: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        payload = asdict(self)
        return payload


def _guess_document_type(text: str) -> str:
    blob = text[:4000]
    if re.search(r"SOP|标准操作程序", blob, re.IGNORECASE):
        return "SOP"
    if re.search(r"Release Notes|发行说明|更新说明", blob, re.IGNORECASE):
        return "release_note"
    if re.search(r"Instructions for Use|使用说明书|用户手册", blob, re.IGNORECASE):
        return "manual"
    return "unknown"


def build_document_model(
    content: str,
    *,
    source_format: str = "docx",
    document_language: str = "unknown",
    fallback_reason: str = "",
) -> DocumentModel:
    text = str(content or "")
    model = DocumentModel(
        source_format=source_format,
        document_language=document_language or "unknown",
        document_type=_guess_document_type(text),
        fallback_reason=fallback_reason,
        page_breaks=[index for index, char in enumerate(text) if char == "\f"],
    )
    paragraphs = text.splitlines(keepends=True)
    cursor = 0
    chapter = ""
    para_index = 0
    for line in paragraphs:
        stripped = line.strip()
        start = cursor
        end = cursor + len(line)
        if stripped:
            span = TextSpan(
                text=stripped,
                paragraph_index=para_index,
                char_start=start,
                char_end=end,
                chapter=chapter,
                source_style="heading" if _HEADING_RE.match(stripped) else "body",
            )
            if span.source_style == "heading":
                chapter = stripped[:80]
                span.chapter = chapter
                model.headings.append(span)
            model.paragraphs.append(span)
            para_index += 1
        cursor = end
    for match in _FIGURE_RE.finditer(text):
        model.figures.append({
            "reference_id": match.group(1),
            "caption_text": match.group(0).strip(),
            "char_start": match.start(),
            "char_end": match.end(),
        })
    for match in _TABLE_RE.finditer(text):
        model.tables.append({
            "reference_id": match.group(1),
            "caption_text": match.group(0).strip(),
            "char_start": match.start(),
            "char_end": match.end(),
        })
    return model


def locate_text(model: DocumentModel, snippet: str) -> dict | None:
    needle = str(snippet or "").strip()
    if not needle:
        return None
    for para in model.paragraphs:
        offset = para.text.find(needle)
        if offset < 0:
            continue
        return {
            "chapter": para.chapter,
            "paragraph_index": para.paragraph_index,
            "char_start": para.char_start + offset,
            "char_end": para.char_start + offset + len(needle),
            "source": model.source_format,
        }
    return None
