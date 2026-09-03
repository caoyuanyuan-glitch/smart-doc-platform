"""Paragraph/sentence language segmentation for review rules."""

from __future__ import annotations

import re


PROTECTED_LITERAL_RE = re.compile(
    r"(?:"
    r"\b(?:DNBSEQ|CoreTM|StandardMPS|DNBelab)[A-Za-z0-9\-]*\b"
    r"|\b[A-Z]{1,8}\d{1,4}[A-Za-z0-9\-]{0,12}\b"
    r"|\d+(?:\.\d+)?\s*(?:μL|µL|[uU][lL]|mL|ml|μl|rpm|min|sec|s|mm|nm|cm|°C|℃)\b"
    r"|\b[\w.-]+\.(?:docx|pdf|idml|xlsx|dita|xml|txt)\b"
    r")",
    re.IGNORECASE,
)
_PARAGRAPH_RE = re.compile(r"\n+")
_SENTENCE_RE = re.compile(r"(?<=[。！？.!?])\s+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_LATIN_RE = re.compile(r"[A-Za-z]")


def mask_protected_literals(text: str) -> str:
    return PROTECTED_LITERAL_RE.sub(" ", str(text or ""))


def classify_text_language(text: str) -> str:
    masked = mask_protected_literals(text)
    chinese = len(_CJK_RE.findall(masked))
    latin = len(_LATIN_RE.findall(masked))
    if chinese == 0 and latin == 0:
        return "unknown"
    if chinese and latin:
        return "mixed"
    return "zh-CN" if chinese else "en-US"


def _segment_payload(text: str, start: int, paragraph_index: int, sentence_index: int, language: str) -> dict:
    return {
        "text": text,
        "language": language,
        "start": start,
        "end": start + len(text),
        "paragraph_index": paragraph_index,
        "sentence_index": sentence_index,
    }


def _split_script_runs(text: str, abs_start: int, paragraph_index: int, sentence_index: int) -> list[dict]:
    parts = []
    for match in re.finditer(r"[\u4e00-\u9fff]+|[^\u4e00-\u9fff]+", text):
        chunk = match.group(0)
        if not chunk.strip():
            continue
        language = "zh-CN" if _CJK_RE.search(chunk) else classify_text_language(chunk)
        if language == "mixed":
            language = "en-US" if _LATIN_RE.search(chunk) else "unknown"
        parts.append(
            _segment_payload(chunk, abs_start + match.start(), paragraph_index, sentence_index, language)
        )
    return parts or [_segment_payload(text, abs_start, paragraph_index, 0, classify_text_language(text))]


def segment_text_by_language(text: str) -> list[dict]:
    """Return paragraph or sentence segments with language and offsets."""
    source = str(text or "")
    if not source:
        return []

    segments = []
    cursor = 0
    paragraph_index = 0
    for block in _PARAGRAPH_RE.split(source):
        start = source.find(block, cursor)
        if start < 0:
            start = cursor
        cursor = start + len(block)
        if not block.strip():
            continue
        paragraph_index += 1
        language = classify_text_language(block)
        if language != "mixed":
            segments.append(_segment_payload(block, start, paragraph_index, 0, language))
            continue
        sentence_index = 0
        sent_cursor = 0
        sentences = _SENTENCE_RE.split(block) if _SENTENCE_RE.search(block) else [block]
        if len(sentences) == 1:
            segments.extend(_split_script_runs(block, start, paragraph_index, 1))
            continue
        for sentence in sentences:
            sent_start = block.find(sentence, sent_cursor)
            if sent_start < 0:
                sent_start = sent_cursor
            sent_cursor = sent_start + len(sentence)
            if not sentence.strip():
                continue
            sentence_index += 1
            sent_lang = classify_text_language(sentence)
            abs_start = start + sent_start
            if sent_lang == "mixed":
                segments.extend(_split_script_runs(sentence, abs_start, paragraph_index, sentence_index))
            else:
                segments.append(_segment_payload(sentence, abs_start, paragraph_index, sentence_index, sent_lang))
    return segments


def language_at_offset(segments: list[dict], offset: int) -> str:
    for item in segments or []:
        if int(item.get("start") or 0) <= offset < int(item.get("end") or 0):
            return str(item.get("language") or "unknown")
    return "unknown"
