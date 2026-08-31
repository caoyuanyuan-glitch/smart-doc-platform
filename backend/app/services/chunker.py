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


def _stable_chunk_id(index: int, start: int, end: int, content: str) -> str:
    payload = f"{index}:{start}:{end}:{content[:80]}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def _is_heading(line: str) -> bool:
    text = str(line or "").strip()
    if not text or len(text) > 80:
        return False
    return bool(_HEADING_RE.match(text))


class DocumentChunker:
    def __init__(self, max_chars: int = 2800, overlap: int = 200, max_chunks: int = 32):
        self.max_chars = max(400, int(max_chars or 2800))
        self.overlap = max(0, min(int(overlap or 0), self.max_chars // 2))
        self.max_chunks = max(1, int(max_chunks or 32))

    def chunk_document(self, content: str) -> list[DocumentChunk]:
        text = str(content or "")
        if not text.strip():
            return []
        segments = self._split_by_chapter(text)
        raw_chunks: list[DocumentChunk] = []
        for chapter, start, _end, body in segments:
            raw_chunks.extend(self._window_split(body, start, chapter))
        if len(raw_chunks) > self.max_chunks:
            raw_chunks = self._downsample(raw_chunks)
        chunks = []
        for index, chunk in enumerate(raw_chunks):
            chunks.append(DocumentChunk(
                index=index,
                start=chunk.start,
                end=chunk.end,
                content=chunk.content,
                chapter=chunk.chapter,
                chunk_id=_stable_chunk_id(index, chunk.start, chunk.end, chunk.content),
            ))
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

    def _window_split(self, body: str, base_start: int, chapter: str) -> list[DocumentChunk]:
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
                chunks.append(self._make_temp_chunk(buf, buf_start, chapter))
                overlap_text = buf[-self.overlap:] if self.overlap else ""
                buf = overlap_text + part
                buf_start = base_start + cursor - len(overlap_text)
            else:
                buf = candidate
            cursor += len(part)
        if buf.strip():
            chunks.append(self._make_temp_chunk(buf, buf_start, chapter))
        overflow = []
        for chunk in chunks:
            if len(chunk.content) <= self.max_chars:
                overflow.append(chunk)
                continue
            overflow.extend(self._hard_split(chunk.content, chunk.start, chapter))
        return overflow

    def _hard_split(self, text: str, start: int, chapter: str) -> list[DocumentChunk]:
        chunks = []
        cursor = 0
        step = max(1, self.max_chars - self.overlap)
        while cursor < len(text):
            end = min(len(text), cursor + self.max_chars)
            piece = text[cursor:end]
            chunks.append(self._make_temp_chunk(piece, start + cursor, chapter))
            if end >= len(text):
                break
            cursor += step
        return chunks

    def _make_temp_chunk(self, content: str, start: int, chapter: str) -> DocumentChunk:
        end = start + len(content)
        return DocumentChunk(
            index=0,
            start=max(0, start),
            end=end,
            content=content,
            chapter=chapter,
            chunk_id="",
        )

    def _downsample(self, chunks: list[DocumentChunk]) -> list[DocumentChunk]:
        if len(chunks) <= self.max_chunks:
            return chunks
        if self.max_chunks == 1:
            return [chunks[0]]
        indexes = sorted({round(i * (len(chunks) - 1) / (self.max_chunks - 1)) for i in range(self.max_chunks)})
        return [chunks[i] for i in indexes]


def create_smart_chunker(max_chunks: int = 32, max_chars: int = 2800, overlap: int = 200) -> DocumentChunker:
    return DocumentChunker(max_chars=max_chars, overlap=overlap, max_chunks=max_chunks)


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
