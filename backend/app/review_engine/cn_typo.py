"""中文错别字表检查（DET-TYPO-CN-001 / A5）。

pyspellchecker 判不了中文。人工意见里的高频错字对（登陆→登录、临近→邻近、
涡漩→涡旋）必须走词表。只报词典命中，不猜。
"""

from __future__ import annotations

import json
import re

from app.utils.typo_dictionary import get_default_typo_dict

_MAX_REPORTS = 8
_MAX_PER_WRONG = 4


def _encode_position(start: int, end: int, **meta) -> str:
    payload = {"start": start, "end": end, "area": meta.pop("area", "正文")}
    payload.update({key: value for key, value in meta.items() if value not in (None, "", [], {})})
    return json.dumps(payload, ensure_ascii=False)


def _page_at(text: str, offset: int) -> int:
    return text[: max(0, offset)].count("\f") + 1


def _context(text: str, start: int, end: int, radius: int = 60) -> str:
    return re.sub(r"\s+", " ", text[max(0, start - radius):min(len(text), end + radius)]).strip()


def check_cn_typos(text: str, *, parsed: bool = True) -> list[dict]:
    source = str(text or "")
    if not parsed or not source.strip():
        return []

    mapping = get_default_typo_dict()
    if not mapping:
        return []

    occupied: list[tuple[int, int]] = []
    issues: list[dict] = []
    for wrong, right in sorted(mapping.items(), key=lambda item: (-len(item[0]), item[0])):
        if not wrong or wrong == right:
            continue
        start = 0
        hits = 0
        while hits < _MAX_PER_WRONG and len(issues) < _MAX_REPORTS:
            idx = source.find(wrong, start)
            if idx < 0:
                break
            end = idx + len(wrong)
            if any(idx < used_end and end > used_start for used_start, used_end in occupied):
                start = idx + 1
                continue
            occupied.append((idx, end))
            issues.append({
                "severity": "general",
                "category": "中文错别字",
                "rule": "DET-TYPO-CN-001",
                "chapter": "",
                "original_text": wrong,
                "context": _context(source, idx, end),
                "suggestion": f"建议改为「{right}」。",
                "description": f"中文用字错误：原文「{wrong}」应为「{right}」。",
                "audit_basis": "中文错别字表",
                "confidence": 88,
                "source": "rule",
                "status": "pending",
                "expected": right,
                "position": _encode_position(idx, end, page=_page_at(source, idx), area="正文"),
            })
            hits += 1
            start = end
    return issues
