"""AI 审核规范基线的本地兜底读取。

背景：知识库 DB 登记的写作规范文件可能缺失（文件夹未建）或物理文件不可读
（Windows ACL 反常状态：可写、无读权限），导致 AI prompt 规范基线为空
（cn=0/en=0）。此时回退到本地「审核依据」目录的可读副本。

来源目录可用环境变量 REVIEW_WRITING_STANDARDS_DIR 覆盖；
默认指向 C:/MyFileAudit/审核工作区/审核依据（人工审核语料与规范原文）。

知识库优先级：DB 登记文件（review.py::_load_review_spec_texts）>
本地兜底副本。仅在 DB 文本为空时启用兜底，不覆盖知识库原文。

《2026历史人工审核意见知识库》的三段硬约束（免报清单 / 判定流程 / 证据要求）
通过 extract_human_review_kb_constraints 抽取后作为 AI 输出约束注入 prompt。
"""

from __future__ import annotations

import os
import re
from pathlib import Path

# 键名与 review.py spec_texts 的键保持一致；human_review_kb 为本模块新增。
FALLBACK_FILENAMES = {
    "cn_style": "中文技术文档写作风格指南.md",
    "en_style": "MGI英文技术文档写作风格指南.md",
    "common_errors": "技术文档常见错误清单与规范.md",
    "human_review_kb": "2026历史人工审核意见知识库.md",
}

DEFAULT_FALLBACK_DIR = r"C:\MyFileAudit\审核工作区\审核依据"

_CACHE: tuple[Path, dict[str, str]] | None = None

# 《2026历史人工审核意见知识库》中的小节边界（标题行正则）。
_KB_SECTIONS = [
    # (起始标题, 结束标题, 段落用途说明)
    (r"^##\s*十一、免报清单.*$", r"^##\s*十二、", "免报清单（人工明示不需改，命中即排除）"),
    (r"^###\s*13\.1 判定流程.*$", r"^###\s*13\.3", "判定流程（扫描命中后的七步排除链）"),
    (r"^###\s*13\.2 证据要求.*$", r"^###\s*13\.3", "证据要求（各类问题必备证据，缺证据不得出报告）"),
]


def fallback_dir() -> Path | None:
    """返回兜底目录；不存在返回 None。"""
    raw = os.getenv("REVIEW_WRITING_STANDARDS_DIR") or DEFAULT_FALLBACK_DIR
    path = Path(raw)
    return path if path.is_dir() else None


def reset_cache() -> None:
    """测试或目录内容变更后重置读取缓存。"""
    global _CACHE
    _CACHE = None


def load_fallback_spec_texts(directory: Path | None = None) -> dict[str, str]:
    """读取本地兜底规范文本，返回 {spec_key: text}。目录不存在或文件缺失时对应键缺省。"""
    global _CACHE
    dir_path = Path(directory) if directory else fallback_dir()
    if dir_path is None or not dir_path.is_dir():
        return {}
    if _CACHE is not None and _CACHE[0] == dir_path:
        return _CACHE[1]

    texts: dict[str, str] = {}
    for key, name in FALLBACK_FILENAMES.items():
        path = dir_path / name
        if not path.is_file():
            continue
        try:
            texts[key] = path.read_text(encoding="utf-8-sig", errors="ignore")
        except Exception as exc:
            print(f"[审核] 读取本地规范兜底文件失败 {key}({name}): {exc}")
    _CACHE = (dir_path, texts)
    return texts


def extract_human_review_kb_constraints(text: str, max_chars: int = 4000) -> str:
    """抽取《2026历史人工审核意见知识库》的三段硬约束，拼成 prompt 可用的约束块。

    缺任一段落时只返回能抽到的部分；整体为空则返回空串。
    """
    if not text:
        return ""
    chunks: list[str] = []
    for start_pat, end_pat, purpose in _KB_SECTIONS:
        start = re.search(start_pat, text, flags=re.MULTILINE)
        if not start:
            continue
        rest = text[start.end():]
        end = re.search(end_pat, rest, flags=re.MULTILINE)
        body = rest[: end.start()] if end else rest
        body = body.strip()
        if body:
            chunks.append(f"【{purpose}】\n{body}")

    if not chunks:
        return ""
    joined = "\n\n".join(chunks)
    if len(joined) > max_chars:
        joined = joined[:max_chars].rstrip() + "\n…（已截断，以本地原文为准）"
    return joined
