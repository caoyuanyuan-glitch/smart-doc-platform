"""B9 学到的替换对：同一文档同时出现锚点与替换文本时上报 LEARN-PATCH-001。

只做文档内一致性，不把单点改写当成全局规则。泛化英文单词对
（device/product）和无关改写（Color/sentence style）在加载时丢弃。
"""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

_ASSETS = Path(__file__).resolve().parent / "assets" / "learned_patches.json"
_MAX_REPORTS = 8
_GENERIC_ONE = {
    "device", "product", "power", "color", "colour", "system", "module",
    "data", "file", "user", "type", "mode", "page", "table", "figure",
    "button", "icon", "window", "error", "value", "number", "sample",
    "reagent", "kit", "card", "port", "cable", "status", "content",
    "item", "list", "option", "setting", "parameter", "volume", "speed",
    "flow", "cell", "chip", "click", "select", "start", "stop", "name",
}


def _encode_position(start: int, end: int, **meta) -> str:
    payload = {"start": start, "end": end, "area": meta.pop("area", "正文")}
    payload.update({key: value for key, value in meta.items() if value not in (None, "", [], {})})
    return json.dumps(payload, ensure_ascii=False)


def _page_at(text: str, offset: int) -> int:
    return text[: max(0, offset)].count("\f") + 1


def _context(text: str, start: int, end: int, radius: int = 70) -> str:
    return re.sub(r"\s+", " ", text[max(0, start - radius):min(len(text), end + radius)]).strip()


def looks_like_variant(anchor: str, replacement: str) -> bool:
    a = str(anchor or "").strip()
    b = str(replacement or "").strip()
    if not a or not b or a.lower() == b.lower():
        return False
    al = a.lower().strip(".")
    bl = b.lower().strip(".")
    if al in _GENERIC_ONE and bl in _GENERIC_ONE:
        return False
    if "【" in a or "【" in b or "下同" in b or "或者：" in b:
        return False
    cjk_a = bool(re.search(r"[\u4e00-\u9fff]", a))
    cjk_b = bool(re.search(r"[\u4e00-\u9fff]", b))
    if cjk_a or cjk_b:
        shared_cjk = {ch for ch in set(a) & set(b) if "\u4e00" <= ch <= "\u9fff"}
        ratio = len(a) / max(len(b), 1)
        return bool(shared_cjk) and 0.4 <= ratio <= 2.5 and max(len(a), len(b)) <= 16
    a_toks = set(re.findall(r"[A-Za-z]{4,}", a.lower()))
    b_toks = set(re.findall(r"[A-Za-z]{4,}", b.lower()))
    if a_toks & b_toks:
        return True
    return SequenceMatcher(None, al, bl).ratio() >= 0.58


def _find_all(text: str, needle: str) -> list[int]:
    if not needle:
        return []
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9'-]*", needle):
        pattern = re.compile(r"\b" + re.escape(needle) + r"\b", re.IGNORECASE)
        return [match.start() for match in pattern.finditer(text)]
    starts = []
    idx = 0
    while True:
        pos = text.find(needle, idx)
        if pos < 0:
            break
        starts.append(pos)
        idx = pos + max(len(needle), 1)
    return starts


@lru_cache(maxsize=1)
def load_learned_patches() -> tuple[dict, ...]:
    if not _ASSETS.is_file():
        return ()
    payload = json.loads(_ASSETS.read_text(encoding="utf-8"))
    items = []
    seen = set()
    for row in payload.get("items") or []:
        anchor = str(row.get("anchor") or "").strip()
        replacement = str(row.get("replacement") or "").strip()
        if not looks_like_variant(anchor, replacement):
            continue
        key = (anchor.lower(), replacement.lower())
        if key in seen:
            continue
        seen.add(key)
        items.append({"anchor": anchor, "replacement": replacement})
    return tuple(items)


def check_learned_patches(text: str, *, parsed: bool = True) -> list[dict]:
    source = str(text or "")
    if not parsed or not source.strip():
        return []

    issues = []
    for item in load_learned_patches():
        if len(issues) >= _MAX_REPORTS:
            break
        anchor = item["anchor"]
        replacement = item["replacement"]
        left = _find_all(source, anchor)
        right = _find_all(source, replacement)
        if not left or not right:
            continue
        minority = left if len(left) <= len(right) else right
        majority_form = replacement if len(left) <= len(right) else anchor
        minority_form = anchor if minority is left else replacement
        start = minority[0]
        end = start + len(minority_form)
        issues.append({
            "severity": "general",
            "category": "术语一致性",
            "rule": "LEARN-PATCH-001",
            "chapter": "",
            # 以源码实际切片作为原文：_find_all() 对英文做忽略大小写匹配，
            # 但资产保留原拼写（close/Close），直接用 minority_form 会让报告里的
            # 原文在被检查文档中根本不存在（phantom）。
            "original_text": source[start:end],
            "context": _context(source, start, end),
            "suggestion": f"建议全文统一为「{majority_form}」。",
            "description": (
                f"同一文档同时出现「{anchor}」与「{replacement}」，"
                f"属于学到的替换对在篇内共存。"
            ),
            "audit_basis": "B9 学到的替换对 / 文档内一致性",
            "confidence": 84,
            "source": "rule",
            "status": "pending",
            "expected": majority_form,
            "position": _encode_position(start, end, page=_page_at(source, start), area="正文"),
        })
    return issues
