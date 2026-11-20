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


from app.review_engine.issue_position_utils import (
    encode_position as _encode_position,
    page_at as _page_at,
    build_context as _build_context,
)


def _context(text: str, start: int, end: int, radius: int = 60) -> str:
    return _build_context(text, start, end, radius)


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
