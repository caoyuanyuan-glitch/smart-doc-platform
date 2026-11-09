# -*- coding: utf-8 -*-
"""术语库动态解析器（不落库、按 mtime+size 缓存）。"""
from __future__ import annotations

import os
import re
import threading
from typing import Any, Optional

_CACHE = {"key": None, "value": None}
_LOCK = threading.Lock()

ZH_MARKS = ("zh-cn", "zh_cn", "中文", "简体中文")
EN_MARKS = ("en-us", "en_us", "英文", "英语", "english")
FORBIDDEN_NOTE_MARKS = ("禁止", "勿用", "不要写成", "错误写法")


def _norm(header: Any) -> str:
    return str(header or "").strip().lower().replace(" ", "")


def _blocks(headers) -> dict[str, list[int]]:
    """按表头字面量切出 zh / en 两个列区块。"""
    blocks, cur = {}, None
    for i, header in enumerate(headers):
        n = _norm(header)
        if any(mark in n for mark in ZH_MARKS):
            cur = "zh"
            blocks.setdefault("zh", [])
        elif any(mark in n for mark in EN_MARKS):
            cur = "en"
            blocks.setdefault("en", [])
        if cur:
            blocks[cur].append(i)
    return blocks


def _col(headers, block_idx, names):
    for i in block_idx:
        if _norm(headers[i]) in names:
            return i
    return None


def load_terminology(path: Optional[str]):
    """返回 TerminologyPack；文件不存在/格式不符返回 None，不抛异常。"""
    try:
        import openpyxl
    except ImportError:
        return None
    if not path or not os.path.exists(path):
        return None
    if not str(path).lower().endswith(".xlsx"):
        return None

    try:
        st = os.stat(path)
        stamp = (st.st_mtime, st.st_size)
    except OSError:
        return None

    with _LOCK:
        if _CACHE["key"] == (path, stamp) and _CACHE["value"] is not None:
            return _CACHE["value"]

    try:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception:
        return None

    try:
        ws = wb.active
        it = ws.iter_rows(values_only=True)
        try:
            headers = list(next(it))
        except StopIteration:
            return None
        blocks = _blocks(headers)
        if "zh" not in blocks or "en" not in blocks:
            return None

        zi = _col(headers, blocks["zh"], {"zh-cn", "中文"})
        ei = _col(headers, blocks["en"], {"en-us", "英文"})
        if zi is None or ei is None:
            return None

        z_src = _col(headers, blocks["zh"], {"source"})
        z_note = _col(headers, blocks["zh"], {"note"})
        z_desc = _col(headers, blocks["zh"], {"description"})
        e_src = _col(headers, blocks["en"], {"source"})

        pairs, zh_index, en_index = [], {}, {}
        zh_set, en_set = set(), set()

        def cell(row, idx):
            if idx is None or idx >= len(row):
                return ""
            value = row[idx]
            return str(value).strip() if value is not None else ""

        for row in it:
            zh, en = cell(row, zi), cell(row, ei)
            if not zh and not en:
                continue
            src = cell(row, z_src) or cell(row, e_src)
            note = cell(row, z_note) or cell(row, z_desc) or ""
            if zh:
                zh_set.add(zh)
            if en:
                en_set.add(en)
            if zh and en:
                pairs.append((zh, en, src, note))
                zh_index.setdefault(zh, [])
                if en not in zh_index[zh]:
                    zh_index[zh].append(en)
                en_index.setdefault(en, [])
                if zh not in en_index[en]:
                    en_index[en].append(zh)

        val = {
            "pairs": pairs,
            "zh_index": zh_index,
            "en_index": en_index,
            "zh_set": zh_set,
            "en_set": en_set,
            "stamp": stamp,
        }
        with _LOCK:
            _CACHE["key"] = (path, stamp)
            _CACHE["value"] = val
        return val
    except Exception:
        return None
    finally:
        try:
            wb.close()
        except Exception:
            pass


def reset_terminology_cache():
    with _LOCK:
        _CACHE["key"] = None
        _CACHE["value"] = None


def pack_to_term_dict(pack) -> dict:
    """润色侧兼容映射：中文标准写法 -> 英文标准写法。"""
    if not pack:
        return {}
    mapping = {}
    for zh, en, _src, _note in pack.get("pairs") or []:
        if zh and en and zh not in mapping:
            mapping[zh] = en
    return mapping


def trim_terms_for_ai_v2(pack, text: str, max_items: int = 120) -> list[dict]:
    """只保留与当前文本相关的术语对，压到 max_items 以内。"""
    if not pack:
        return []
    text = text or ""
    text_lower = text.lower()
    hit, rest = [], []
    for zh, en, src, note in pack.get("pairs") or []:
        item = {"zh": zh, "en": en, "note": note, "source": src}
        if zh in text or (en and en.lower() in text_lower):
            hit.append(item)
        else:
            rest.append(item)
    return (hit + rest)[:max_items]


def resolve_terminology_path(db, document=None) -> Optional[str]:
    """按优先级返回术语库文件路径。"""
    from app.models.knowledge import KnowledgeFile, Folder

    tid = getattr(document, "terminology_id", None) if document is not None else None
    if tid:
        f = db.query(KnowledgeFile).filter(KnowledgeFile.id == tid).first()
        if f and f.file_path and os.path.exists(f.file_path):
            return f.file_path

    folder_ids = set()
    try:
        for folder in db.query(Folder).all():
            name = folder.name or ""
            if "术语" in name:
                folder_ids.add(folder.id)
    except Exception:
        folder_ids = set()
    if 19 not in folder_ids:
        # 兼容旧环境硬编码目录
        folder_ids.add(19)

    stack, all_ids = list(folder_ids), set(folder_ids)
    while stack:
        fid = stack.pop()
        try:
            children = db.query(Folder).filter(Folder.parent_id == fid).all()
        except Exception:
            children = []
        for sf in children:
            if sf.id not in all_ids:
                all_ids.add(sf.id)
                stack.append(sf.id)

    try:
        files = db.query(KnowledgeFile).filter(KnowledgeFile.folder_id.in_(all_ids)).all()
    except Exception:
        return None
    cands = [
        f for f in files
        if f.file_path and str(f.file_path).lower().endswith(".xlsx")
        and "术语" in (f.name or f.filename or "")
        and os.path.exists(f.file_path)
    ]
    if not cands:
        return None
    cands.sort(key=lambda f: os.path.getmtime(f.file_path), reverse=True)
    return cands[0].file_path


def _windows(content: str, term: str, radius: int = 80):
    start = 0
    while True:
        idx = content.find(term, start)
        if idx < 0:
            return
        yield content[max(0, idx - radius): idx + len(term) + radius]
        start = idx + max(len(term), 1)


def run_term_check_v2(content: str, pack, lang: str = "zh") -> list[dict]:
    """集合/配对校验：只报不统一、配对错误、明确禁止写法。"""
    issues = []
    if not pack or not content:
        return issues

    seen = set()

    def add(issue: dict):
        key = (issue["rule"], issue["original_text"])
        if key in seen:
            return
        seen.add(key)
        issues.append(issue)

    # ① 同一英文概念多种中文译法：仅当术语库对该英文只有唯一译法时才判。
    # 实际可检的是：唯一官方译法出现的同时，文档里还出现了带括号/全角变体。
    for en, zh_list in pack.get("en_index", {}).items():
        if len(zh_list) != 1:
            continue
        official = zh_list[0]
        if not official or official not in content:
            continue
        variants = []
        stripped_official = official.replace("【", "").replace("】", "").replace("[", "").replace("]", "")
        for zh in pack.get("zh_set", ()):
            if zh == official or zh not in content:
                continue
            stripped = zh.replace("【", "").replace("】", "").replace("[", "").replace("]", "")
            if stripped and stripped == stripped_official:
                variants.append(zh)
        if variants:
            present = [official, *variants]
            add({
                "severity": "suggestion",
                "category": "术语规范",
                "rule": "TERM-INCONSIST",
                "original_text": " / ".join(present),
                "suggestion": f"术语库对 {en} 的唯一译法为「{official}」，本篇并存 {len(present)} 种写法",
                "description": "同一英文概念在本篇出现多种中文译法",
                "audit_basis": "术语&固定表达 V3.0",
                "confidence": 80,
                "source": "term_v2",
            })

    # ② 中英配对错误：中文术语附近出现库内英文，但不在该中文允许译法中
    pair_on = (os.environ.get("WORKBUDDY_TERM_PAIR") or "off").lower() == "on"
    if pair_on:
        present_en = [en for en in pack.get("en_set", ()) if en and len(en) >= 4 and en in content]
        for zh, en_list in pack.get("zh_index", {}).items():
            if not zh or len(zh) < 2 or zh not in content:
                continue
            allowed = set(en_list or [])
            for window in _windows(content, zh, 80):
                wrong = [en for en in present_en if en in window and en not in allowed]
                if not wrong:
                    continue
                add({
                    "severity": "suggestion",
                    "category": "术语规范",
                    "rule": "TERM-PAIR",
                    "original_text": f"{zh} / {wrong[0]}",
                    "suggestion": f"「{zh}」对应英文应为 {' / '.join(en_list[:3])}",
                    "description": "中文术语附近配了库外的英文",
                    "audit_basis": "术语&固定表达 V3.0",
                    "confidence": 75,
                    "source": "term_v2",
                })
                break

    # ③ 术语表明确禁止的写法
    for zh, en, src, note in pack.get("pairs") or []:
        note = note or ""
        if not any(mark in note for mark in FORBIDDEN_NOTE_MARKS):
            continue
        target = zh if zh in content else (en if en and en in content else "")
        if not target:
            continue
        add({
            "severity": "general",
            "category": "术语规范",
            "rule": "TERM-FORBIDDEN",
            "original_text": target,
            "suggestion": note or f"请改用标准写法 {en or zh}",
            "description": "术语表明确禁止的写法",
            "audit_basis": f"术语&固定表达 V3.0（source={src}）",
            "confidence": 90,
            "source": "term_v2",
        })
    return issues
