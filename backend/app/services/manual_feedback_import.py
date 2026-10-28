"""人工审核意见导入解析器。

把三种已整理好的人工审核意见格式解析为统一结构：

1. Markdown 汇总（review_comment_extractor 产物 / 人工整理汇总）
   - 每条以 `## N. <文档名> · 第 <X> 页` 起头
   - 字段行：`- 批注类型: ...` / `- 批注人: ...` / `- 人工意见: ...` / `- 选中文本: ...` / `- 附近正文: ...`
   - 新版（extractor v2）为 `### 批注覆盖文本` / `### 原文` / `### 人工意见` 小节
2. JSON（gold_v0 评测集格式）
   - list of {file, page, annotation_type, author, comment, selected_text, context, category, layer, expected_rule}
3. CSV（标注集 v0 格式）
   - batch, doc, page, comment, selected, context, auto_category, rule_detectable, loc_quality, flag, note

输出统一 dict 列表，字段与 SupplementFeedback 模型对齐。
"""
from __future__ import annotations

import csv
import json
import re
from typing import Any, Iterable


def _clean(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text in {"-", "—", "[待补充]", "（空——批注覆盖在图上/线框区域，无文本层）", "（空）"}:
        return ""
    return text


def parse_json_content(raw: str | bytes) -> list[dict]:
    data = json.loads(raw if isinstance(raw, str) else raw.decode("utf-8", errors="replace"))
    if isinstance(data, dict):
        data = data.get("annotations") or data.get("items") or []
    if not isinstance(data, list):
        raise ValueError("JSON 顶层应为数组或包含 annotations 数组的对象")
    rows = []
    for item in data:
        if not isinstance(item, dict):
            continue
        rows.append({
            "doc_name": _clean_doc_name(item.get("file") or item.get("doc") or item.get("document")),
            "page": _clean(item.get("page")),
            "annotation_type": _clean(item.get("annotation_type") or item.get("type")),
            "author": _clean(item.get("author") or item.get("reviewer")),
            "comment": _clean(item.get("comment") or item.get("人工意见")),
            "original_text": _clean(item.get("selected_text") or item.get("selected") or item.get("批注覆盖文本")),
            "context": _clean(item.get("context") or item.get("附近正文") or item.get("原文")),
            "category": _clean(item.get("category") or item.get("类别") or item.get("auto_category")),
            "suggestion": _clean(item.get("suggestion") or item.get("修改建议")),
            "layer": _clean(item.get("layer") or item.get("channel")),
            "expected_rule": _clean(item.get("expected_rule") or item.get("rule")),
        })
    return [r for r in rows if r["comment"]]


def _clean_doc_name(name: str) -> str:
    """去掉 `1. ` / `N. ` 序号前缀，保留文档名。"""
    name = _clean(name)
    m = re.match(r"^\d+\.\s*(.+)$", name)
    return m.group(1).strip() if m else name


def parse_csv_content(raw: str | bytes) -> list[dict]:
    text = raw if isinstance(raw, str) else raw.decode("utf-8", errors="replace")
    reader = csv.DictReader(text.splitlines())
    rows = []
    for row in reader:
        r = {k.strip(): (v or "").strip() for k, v in row.items()}
        comment = r.get("comment") or r.get("人工意见") or ""
        if not comment:
            continue
        # rule_detectable 列映射 layer：deterministic / ai_assisted
        rd = (r.get("rule_detectable") or "").strip().lower()
        layer = "deterministic" if rd in {"是", "y", "yes", "1", "true", "deterministic"} else "ai_assisted"
        rows.append({
            "doc_name": _clean_doc_name(r.get("doc") or r.get("document") or r.get("file") or ""),
            "page": r.get("page") or "",
            "annotation_type": r.get("annotation_type") or r.get("type") or "",
            "author": r.get("author") or r.get("reviewer") or "",
            "comment": comment,
            "original_text": r.get("selected") or r.get("selected_text") or r.get("批注覆盖文本") or "",
            "context": r.get("context") or r.get("附近正文") or r.get("原文") or "",
            "category": r.get("auto_category") or r.get("category") or r.get("类别") or "",
            "suggestion": r.get("suggestion") or r.get("修改建议") or "",
            "layer": layer,
            "expected_rule": r.get("expected_rule") or r.get("rule") or "",
        })
    return rows


_SECTION_HEAD_RE = re.compile(r"^##\s*\d*\.?\s*(.*?)\s*·\s*第\s*([0-9]+)\s*页")
_ATTR_LINE_RE = re.compile(r"^-\s*(批注类型|批注人|人工意见|选中文本|附近正文|类别|修改建议|触发条件|例外条件|批注矩形|批注截图)\s*:\s*(.*)$")
_SUBSECTION_RE = re.compile(r"^###\s*(批注覆盖文本|原文|人工意见|人工意见\d*)\s*$")


def _parse_md_blocks(lines: list[str]) -> Iterable[tuple[dict, list[str]]]:
    """按 `##` 切块，返回 (header_info, block_lines)。"""
    current: dict | None = None
    block: list[str] = []
    for line in lines:
        if line.startswith("## "):
            if current is not None:
                yield current, block
            m = _SECTION_HEAD_RE.match(line)
            current = {"doc_name": m.group(1).strip() if m else "", "page": m.group(2).strip() if m else ""}
            block = []
        else:
            block.append(line)
    if current is not None:
        yield current, block


def _parse_md_block(header: dict, lines: list[str]) -> dict:
    row = {
        "doc_name": header.get("doc_name", ""),
        "page": header.get("page", ""),
        "annotation_type": "",
        "author": "",
        "comment": "",
        "original_text": "",
        "context": "",
        "category": "",
        "suggestion": "",
        "layer": "",
        "expected_rule": "",
    }
    # 新版 extractor 小节结构：### 批注覆盖文本 / ### 原文 / ### 人工意见
    sub_sections: dict[str, list[str]] = {}
    cur_sub: str | None = None
    attr_lines: list[tuple[str, str]] = []
    for raw in lines:
        line = raw.rstrip("\n").strip()
        if not line:
            continue
        m = _SUBSECTION_RE.match(line)
        if m:
            cur_sub = m.group(1)
            sub_sections.setdefault(cur_sub, [])
            continue
        if cur_sub:
            sub_sections[cur_sub].append(line)
            continue
        m = _ATTR_LINE_RE.match(line)
        if m:
            attr_lines.append((m.group(1), m.group(2).strip()))
            continue
        # 旧版：`- 知识库整理:` 下面的子字段以 `  - 类别: ...` 形式出现
        m2 = re.match(r"^\s*-\s*(类别|修改建议|触发条件|例外条件)\s*:\s*(.*)$", line)
        if m2:
            attr_lines.append((m2.group(1), m2.group(2).strip()))

    for key, value in attr_lines:
        if key in ("批注类型",):
            row["annotation_type"] = _clean(value)
        elif key == "批注人":
            row["author"] = _clean(value)
        elif key in ("人工意见",):
            row["comment"] = _clean(value)
        elif key == "选中文本":
            row["original_text"] = _clean(value)
        elif key == "附近正文":
            row["context"] = _clean(value)
        elif key == "类别":
            row["category"] = _clean(value)
        elif key == "修改建议":
            row["suggestion"] = _clean(value)

    if "批注覆盖文本" in sub_sections:
        row["original_text"] = row["original_text"] or _clean(" ".join(sub_sections["批注覆盖文本"]))
    if "原文" in sub_sections:
        row["context"] = row["context"] or _clean(" ".join(sub_sections["原文"]))
    if "人工意见" in sub_sections:
        row["comment"] = row["comment"] or _clean(" ".join(sub_sections["人工意见"]))
    return row


def parse_md_content(raw: str | bytes) -> list[dict]:
    text = raw if isinstance(raw, str) else raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    rows = []
    for header, block in _parse_md_blocks(lines):
        row = _parse_md_block(header, block)
        if row["comment"]:
            rows.append(row)
    return rows


def parse_upload(filename: str, raw: bytes) -> list[dict]:
    """按扩展名自动路由到对应解析器。"""
    lower = filename.lower()
    if lower.endswith(".json"):
        return parse_json_content(raw)
    if lower.endswith(".csv"):
        return parse_csv_content(raw)
    if lower.endswith(".md") or lower.endswith(".markdown") or lower.endswith(".txt"):
        return parse_md_content(raw)
    raise ValueError(f"不支持的文件类型: {filename}（支持 .md / .json / .csv）")
