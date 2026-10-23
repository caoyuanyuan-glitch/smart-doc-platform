"""人工审核意见知识库化回流（v2 第 11 节）。

三步闭环：
  1. 去重合并  dedupe_annotations
  2. 归类填写  to_rule_drafts   （复用 annotation_baseline.classify_human_annotation）
  3. 回流落库  persist_rule_drafts（复用 crud.rule.bulk_create_rules）

设计原则：
  - 回流规则默认 regex=r"(?!)"（永不匹配），需人工确认后才启用，避免自动回流引入误报。
  - rule_no 基于「语言 + 内容」hash，既保证幂等（重复回流不产生重复规则），
    又保证中英文同名意见不会互相顶掉。
  - 不新增表、不新增迁移，完全复用现有 rules 表。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Iterable
import re

from app.review_engine.annotation_baseline import (
    HumanAnnotation,
    classify_human_annotation,
    parse_human_annotation_markdown,
)

DISABLED = r"(?!)"


@dataclass
class RuleDraft:
    rule_no: str
    category: str
    description: str
    suggestion: str
    example: str = ""
    severity: str = "suggestion"
    language: str = "cn"
    regex: str = DISABLED
    audit_basis: str = "人工审核意见知识库（v2 第 11 节）"
    source_annotations: list = field(default_factory=list)


def _norm(text) -> str:
    return "".join(str(text or "").split()).lower()


def _stable_hash(*parts) -> str:
    raw = "||".join(_norm(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]


_CN_CATEGORY_MAP = {
    "术语一致性": "中文_字词", "术语拼写": "中文_字词", "商标声明": "中文_字词",
    "货号写法": "中文_字词", "符号规范": "中文_字词", "中文残留": "中文_字词",
    "公司主体表述": "中文_字词", "物料编码": "中文_字词",
    "表达与句式": "中文_句子", "操作步骤语气": "中文_句子",
    "标点符号": "中文_标点", "单位/空格": "中文_标点", "字体/版式细节": "中文_标点",
    "范围/数值格式": "中文_标点", "标题大小写": "中文_标点", "页码异常": "中文_标点",
    "官网地址": "中文_标点",
    "重复内容": "中文_段落", "分页与标题边界": "中文_段落", "表格/版式": "中文_段落",
    "图片/对象缺失": "中文_段落", "信息完整性": "中文_段落",
    "步骤结构": "中文_逻辑", "结构完整性": "中文_逻辑", "主题结构": "中文_逻辑",
    "版本记录": "中文_逻辑", "地址字段确认": "中文_逻辑", "适用范围/硬件配置": "中文_逻辑",
    "表图编号": "中文_逻辑", "法规/注册确认": "中文_逻辑", "人工确认项": "中文_逻辑",
    "人工审核其他项": "中文_逻辑",
}

_EN_CATEGORY_MAP = {
    "术语一致性": "英文_拼写", "术语拼写": "英文_拼写", "商标声明": "英文_拼写",
    "货号写法": "英文_拼写",
    "表达与句式": "英文_句式", "操作步骤语气": "英文_句式",
    "标点符号": "英文_标点", "单位/空格": "英文_标点", "范围/数值格式": "英文_标点",
    "标题大小写": "英文_标点",
    "字体/版式细节": "英文_语法", "信息完整性": "英文_语法",
}

# 分类名未命中显式映射时，用人工意见原文做关键词兜底归类。
_BUCKET_PATTERNS = [
    ("字词", r"错别字|错字|拼写|写法|术语|用词|表述|不规范|应为|改为|名称|大小写|货号|商标"),
    ("标点", r"标点|符号|空格|单位|括号|引号|标号|乘号|顿号|句号|逗号|数值格式"),
    ("句子", r"语序|句式|语法|不通顺|读不|语句|措辞|语气|祈使"),
    ("段落", r"重复|冗余|啰嗦|多余|精简|拆分|合并|段落|分页|跨页|排版|版式|表格|图片|截图"),
    ("逻辑", r"步骤|顺序|编号|页码|结构|逻辑|一致|统一|前后|矛盾|缺失|遗漏|完整|引用|参见"),
]

_CN_BUCKET_SUFFIX = {"字词": "字词", "标点": "标点", "句子": "句子", "段落": "段落", "逻辑": "逻辑"}
_EN_BUCKET_SUFFIX = {"字词": "拼写", "标点": "标点", "句子": "句式", "段落": "逻辑", "逻辑": "逻辑"}

# 归类器的兜底类别本身不含维度信息，遇到时应改走原文关键词推断。
_CATCH_ALL_CATEGORIES = {"人工审核其他项", "人工确认项"}


def _bucket_from_text(text: str) -> str:
    for bucket, pattern in _BUCKET_PATTERNS:
        if re.search(pattern, text or "", re.IGNORECASE):
            return bucket
    return ""


def _to_v2_category(category: str, language: str = "cn", text: str = "") -> str:
    """把归类结果映射到 v2 10 大分类。

    优先用 classify_human_annotation 的分类名精确映射（兜底类别除外）；
    未覆盖时依次用「人工意见原文关键词 → 分类名关键词」推断维度，
    全部落空才归到该语言的逻辑维。
    """
    name = str(category or "")
    mapping = _EN_CATEGORY_MAP if language == "en" else _CN_CATEGORY_MAP
    if name in mapping and name not in _CATCH_ALL_CATEGORIES:
        return mapping[name]

    prefix = "英文" if language == "en" else "中文"
    suffix_map = _EN_BUCKET_SUFFIX if language == "en" else _CN_BUCKET_SUFFIX

    bucket = _bucket_from_text(text)
    if not bucket:
        bucket = _bucket_from_text(name)
    if bucket:
        return f"{prefix}_{suffix_map[bucket]}"
    return f"{prefix}_逻辑"


def dedupe_annotations(annotations: Iterable[HumanAnnotation]):
    """第 1 步：按 (comment 规范化, selected_text) 去重合并，保留首次出现。"""
    seen, merged = set(), []
    for item in annotations:
        key = (_norm(item.comment), _norm(item.selected_text))
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def to_rule_drafts(annotations: Iterable[HumanAnnotation], language: str = "cn"):
    """第 2 步：归类填写——复用 classify_human_annotation 的四层归类结果。"""
    language = "en" if language == "en" else "cn"
    drafts = []
    for item in annotations:
        category = getattr(item, "category", "") or ""
        expected_rule = getattr(item, "expected_rule", "") or ""
        context = getattr(item, "context", "") or ""
        if not category:
            category, _layer, expected_rule = classify_human_annotation(
                item.comment, item.selected_text, context
            )
        hint = " ".join([item.comment or "", item.selected_text or "", context])
        example = (item.selected_text or "").strip() or (context or "").strip()
        drafts.append(RuleDraft(
            rule_no=f"KB-{language.upper()}-{_stable_hash(language, item.comment, item.selected_text)}",
            category=_to_v2_category(category, language, hint),
            description=item.comment,
            suggestion=item.selected_text or expected_rule or "",
            example=example,
            language=language,
            source_annotations=[item.comment],
        ))
    return drafts


def persist_rule_drafts(db, drafts):
    """第 3 步：回流落库——复用 crud.rule.bulk_create_rules（按 rule_no 幂等）。"""
    from app.crud.rule import bulk_create_rules
    from app.schemas.rule import RuleCreate
    payload = [
        RuleCreate(
            rule_no=d.rule_no, category=d.category, description=d.description,
            regex=d.regex, example=d.example, suggestion=d.suggestion,
            audit_basis=d.audit_basis, severity=d.severity, language=d.language,
        )
        for d in drafts
    ]
    return bulk_create_rules(db, payload)


def import_annotations_markdown_to_rule_library(db, markdown_text: str, language: str = "cn") -> dict:
    """从 markdown 文本回流：写入临时文件后解析 → 去重 → 归类 → 落库。"""
    import tempfile
    from pathlib import Path

    with tempfile.NamedTemporaryFile("w", suffix=".md", encoding="utf-8", delete=False) as handle:
        handle.write(markdown_text or "")
        temp_path = handle.name
    try:
        return import_annotations_to_rule_library(db, temp_path, language=language)
    finally:
        Path(temp_path).unlink(missing_ok=True)


def import_annotations_to_rule_library(db, markdown_path: str, language: str = "cn") -> dict:
    """一站式入口：解析 → 去重 → 归类 → 落库，返回统计。"""
    annotations = parse_human_annotation_markdown(markdown_path)
    merged = dedupe_annotations(annotations)
    drafts = to_rule_drafts(merged, language=language)
    persisted = persist_rule_drafts(db, drafts)
    return {
        "parsed": len(annotations), "deduped": len(merged),
        "drafts": len(drafts), "persisted": persisted,
    }
