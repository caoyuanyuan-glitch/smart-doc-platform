"""Smart document chunker for the review module."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Iterable


_HEADING_RE = re.compile(
    r"^(?:"
    r"#{1,6}\s+\S"
    r"|第[一二三四五六七八九十百千0-9]+[章节篇部]"
    r"|\d+(?:\.\d+){0,4}\s+\S"
    r"|[A-Z][A-Z0-9 /_-]{7,}$"
    r"|附录[A-Z0-9]?"
    r"|Appendix\s+[A-Z0-9]+"
    r")",
    re.IGNORECASE,
)


@dataclass
class DocumentChunk:
    index: int
    start: int
    end: int
    content: str
    chunk_id: str
    chapter: str = ""
    parent_chapter: str = ""
    page_range: str = ""
    batch_index: int = 0


def _stable_chunk_id(index: int, start: int, end: int, content: str) -> str:
    payload = f"{index}:{start}:{end}:{content[:80]}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def _is_heading(line: str) -> bool:
    text = str(line or "").strip()
    if not text or len(text) > 80:
        return False
    return bool(_HEADING_RE.match(text))


class DocumentChunker:
    def __init__(self, max_chars: int = 2800, overlap: int = 200, max_chunks: int = 32, sampling_mode: str = "off"):
        self.max_chars = max(400, int(max_chars or 2800))
        self.overlap = max(0, min(int(overlap or 0), self.max_chars // 2))
        self.max_chunks = max(1, int(max_chunks or 32))
        self.sampling_mode = str(sampling_mode or "off").strip().lower() or "off"
        self.last_diagnostics: dict = {}

    def sampling_enabled(self) -> bool:
        return self.sampling_mode not in {"", "off", "none", "false", "0"}

    def chunk_document(self, content: str) -> list[DocumentChunk]:
        text = str(content or "")
        if not text.strip():
            self.last_diagnostics = _empty_coverage(len(text))
            return []
        segments = self._split_by_chapter(text)
        raw_chunks: list[DocumentChunk] = []
        parent_chapter = ""
        for chapter, start, _end, body in segments:
            parent = parent_chapter if parent_chapter and parent_chapter != chapter else ""
            raw_chunks.extend(self._window_split(body, start, chapter, parent_chapter=parent))
            if chapter:
                parent_chapter = chapter
        skipped_chapters: list[str] = []
        chunker_mode = "chapter"
        fallback_reason = ""
        if self.sampling_enabled() and len(raw_chunks) > self.max_chunks:
            kept_indexes = _even_indexes(len(raw_chunks), self.max_chunks)
            skipped_chapters = [
                raw_chunks[i].chapter for i in range(len(raw_chunks)) if i not in kept_indexes and raw_chunks[i].chapter
            ]
            raw_chunks = self._downsample(raw_chunks)
            chunker_mode = f"sampled:{self.sampling_mode}"
            fallback_reason = "explicit_sampling_mode"
        chunks = []
        for index, chunk in enumerate(raw_chunks):
            chunks.append(DocumentChunk(
                index=index,
                start=chunk.start,
                end=chunk.end,
                content=chunk.content,
                chapter=chunk.chapter,
                parent_chapter=chunk.parent_chapter,
                page_range=_page_range_for_offsets(text, chunk.start, chunk.end),
                chunk_id=_stable_chunk_id(index, chunk.start, chunk.end, chunk.content),
            ))
        self.last_diagnostics = compute_chunk_coverage(
            len(text),
            [(item.start, item.end) for item in chunks],
            all_chapters=[chapter for chapter, *_rest in segments],
            processed_chapters=[item.chapter for item in chunks],
            skipped_chapters=skipped_chapters,
            chunker_mode=chunker_mode,
            fallback_reason=fallback_reason,
            total_chunk_count=len(chunks),
            processed_chunk_count=len(chunks),
        )
        return chunks

    def _split_by_chapter(self, text: str) -> list[tuple[str, int, int, str]]:
        lines = text.splitlines(keepends=True)
        segments = []
        cursor = 0
        current_start = 0
        current_chapter = "正文"
        buffer: list[str] = []
        for line in lines:
            if buffer and _is_heading(line):
                body = "".join(buffer)
                segments.append((current_chapter, current_start, cursor, body))
                buffer = [line]
                current_start = cursor
                current_chapter = line.strip()[:80]
            else:
                if not buffer and _is_heading(line):
                    current_chapter = line.strip()[:80]
                buffer.append(line)
            cursor += len(line)
        if buffer:
            body = "".join(buffer)
            segments.append((current_chapter, current_start, cursor, body))
        if not segments:
            segments.append(("正文", 0, len(text), text))
        return segments

    def _window_split(self, body: str, base_start: int, chapter: str, parent_chapter: str = "") -> list[DocumentChunk]:
        if not body:
            return []
        parts = re.split(r"(\n\s*\n)", body)
        chunks: list[DocumentChunk] = []
        buf = ""
        buf_start = base_start
        cursor = 0
        for part in parts:
            if not part:
                cursor += len(part)
                continue
            if not buf:
                buf_start = base_start + cursor
            candidate = part if not buf else buf + part
            if buf and len(candidate) > self.max_chars:
                chunks.append(self._make_temp_chunk(buf, buf_start, chapter, parent_chapter=parent_chapter))
                overlap_text = _overlap_window(buf, self.overlap)
                buf = overlap_text + part
                buf_start = base_start + cursor - len(overlap_text)
            else:
                buf = candidate
            cursor += len(part)
        if buf.strip():
            chunks.append(self._make_temp_chunk(buf, buf_start, chapter, parent_chapter=parent_chapter))
        overflow = []
        for chunk in chunks:
            if len(chunk.content) <= self.max_chars:
                overflow.append(chunk)
                continue
            overflow.extend(self._hard_split(chunk.content, chunk.start, chapter, parent_chapter=parent_chapter))
        return overflow

    def _hard_split(self, text: str, start: int, chapter: str, parent_chapter: str = "") -> list[DocumentChunk]:
        chunks = []
        cursor = 0
        step = max(1, self.max_chars - self.overlap)
        while cursor < len(text):
            end = min(len(text), cursor + self.max_chars)
            piece = text[cursor:end]
            chunks.append(self._make_temp_chunk(piece, start + cursor, chapter, parent_chapter=parent_chapter))
            if end >= len(text):
                break
            cursor += step
        return chunks

    def _make_temp_chunk(self, content: str, start: int, chapter: str, parent_chapter: str = "") -> DocumentChunk:
        end = start + len(content)
        return DocumentChunk(
            index=0,
            start=max(0, start),
            end=end,
            content=content,
            chapter=chapter,
            parent_chapter=parent_chapter,
            chunk_id="",
        )

    def _downsample(self, chunks: list[DocumentChunk]) -> list[DocumentChunk]:
        if len(chunks) <= self.max_chunks:
            return chunks
        if self.max_chunks == 1:
            return [chunks[0]]
        indexes = sorted(_even_indexes(len(chunks), self.max_chunks))
        return [chunks[i] for i in indexes]


def create_smart_chunker(
    max_chunks: int = 32,
    max_chars: int = 2800,
    overlap: int = 200,
    sampling_mode: str = "off",
) -> DocumentChunker:
    return DocumentChunker(
        max_chars=max_chars,
        overlap=overlap,
        max_chunks=max_chunks,
        sampling_mode=sampling_mode,
    )


def _even_indexes(count: int, keep: int) -> set[int]:
    if count <= keep:
        return set(range(count))
    if keep <= 1:
        return {0}
    return {round(i * (count - 1) / (keep - 1)) for i in range(keep)}


def _overlap_window(text: str, overlap: int) -> str:
    if overlap <= 0 or not text:
        return ""
    window = text[-overlap:]
    break_at = window.find("\n")
    if 0 <= break_at < len(window) - 1:
        return window[break_at + 1:]
    return window


def _page_range_for_offsets(text: str, start: int, end: int) -> str:
    start_page = text[: max(0, start)].count("\f") + 1
    end_page = text[: max(0, end)].count("\f") + 1
    if start_page == end_page:
        return str(start_page)
    return f"{start_page}-{end_page}"


def _empty_coverage(source_len: int) -> dict:
    return compute_chunk_coverage(
        source_len,
        [],
        all_chapters=[],
        processed_chapters=[],
        skipped_chapters=[],
        chunker_mode="empty",
        fallback_reason="empty_content",
        total_chunk_count=0,
        processed_chunk_count=0,
    )


def compute_chunk_coverage(
    source_len: int,
    processed_ranges: list[tuple[int, int]],
    *,
    all_chapters: list[str] | None = None,
    processed_chapters: list[str] | None = None,
    skipped_chapters: list[str] | None = None,
    chunker_mode: str = "chapter",
    fallback_reason: str = "",
    total_chunk_count: int = 0,
    processed_chunk_count: int = 0,
) -> dict:
    merged: list[list[int]] = []
    for start, end in sorted((max(0, int(s)), max(0, int(e))) for s, e in processed_ranges or []):
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    covered = sum(end - start for start, end in merged)
    ratio = (covered / source_len) if source_len else 1.0
    skipped = list(skipped_chapters or [])
    if not skipped and all_chapters and processed_chapters is not None:
        processed_set = {item for item in processed_chapters if item}
        skipped = [item for item in all_chapters if item and item not in processed_set]
    return {
        "total_source_chars": int(source_len or 0),
        "total_chunk_count": int(total_chunk_count or len(processed_ranges or [])),
        "processed_chunk_count": int(processed_chunk_count or len(processed_ranges or [])),
        "covered_char_count": covered,
        "coverage_ratio": round(min(1.0, ratio), 4) if source_len else 1.0,
        "skipped_chunk_count": max(0, int(total_chunk_count or 0) - int(processed_chunk_count or 0)),
        "skipped_chapters": skipped,
        "chunker_mode": chunker_mode,
        "fallback_reason": fallback_reason,
    }


class CrossChapterConsistencyChecker:
    """Detect simple term spelling drift across chapter chunks."""

    def check(self, chunks: Iterable[DocumentChunk]) -> list[dict]:
        seen: dict[str, str] = {}
        issues = []
        for chunk in chunks or []:
            for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", chunk.content or ""):
                key = token.lower()
                previous = seen.get(key)
                if previous and previous != token:
                    issues.append({
                        "rule": "CHUNK-CONSISTENCY-001",
                        "category": "术语一致性",
                        "severity": "general",
                        "original_text": token,
                        "chapter": chunk.chapter,
                        "description": f"术语大小写/拼写在跨章节中不一致: {previous} vs {token}",
                        "suggestion": f"建议统一为 {previous}",
                        "source": "rule",
                        "chunk_id": chunk.chunk_id,
                    })
                else:
                    seen[key] = token
        return issues


class AuditResultMerger:
    def merge(self, issue_groups: Iterable[Iterable[dict]]) -> list[dict]:
        merged = []
        seen = set()
        for group in issue_groups or []:
            for issue in group or []:
                key = (
                    str(issue.get("rule") or ""),
                    str(issue.get("original_text") or "").strip(),
                    str(issue.get("chapter") or ""),
                )
                if key in seen:
                    continue
                seen.add(key)
                merged.append(issue)
        return merged
