"""人工意见 → 学习规则（安全版）

设计原则：
  - 人工意见转成规则草案时，regex 恒为 `(?!)`（永不匹配），不会产生误报；
  - 抽象检测要点放在 description/audit_basis，人工确认后才"启用"；
  - 启用方式：description 加 `[已启用]` 前缀——零迁移、可回退；
  - 启用的学习规则不参与正则匹配，而是作为"审核依据 section"注入 prompt，
    复用 human_review_patterns 的抽象模式机制，不照搬具体错误原文。

状态约定（rule_no 前缀 LR- 表示学习规则）：
  - 草案：description 无 `[已启用]`，regex=(?!)  → 不生效
  - 启用：description 有 `[已启用]`，regex=(?!) → 作为审核依据注入
  - 停用：去掉 `[已启用]` 前缀 → 回到草案

不做的事：不把意见原文写成正则去匹配（会照搬臆造，用户已裁定为误报类型）。
"""
from __future__ import annotations

import hashlib
from typing import Any

ENABLED_PREFIX = "[已启用]"
DISABLED_REGEX = r"(?!)"
LEARNED_PREFIX = "LR-"

# 与 human_review_patterns.CATEGORY_PATTERNS 相同的抽象模式，按 category 取
CATEGORY_HINT: dict[str, str] = {
    "单位/空格": "数字与单位、倍率符号之间是否保留半角空格；同类表述全文是否空格一致。",
    "表达与句式": "句子是否通顺、是否有成分残缺或叠用；是否有口语化、歧义或与上下文不一致。",
    "步骤结构": "步骤编号是否连续、是否有跳号或合并；步骤是否可执行。",
    "重复内容": "同一句或同一信息是否跨页重复；语义是否重复。",
    "术语一致性": "同一概念全文用词与大小写是否统一；术语首次出现是否有解释。",
    "表格/版式": "表格表头是否跨页重复、列宽是否足够、边框/竖线是否多余或缺失。",
    "标点符号": "中英文标点是否混用、括号是否配对、句号逗号冒号是否缺失或多余。",
    "货号写法": "货号是否符合既定三段式格式；全文格式是否统一。",
    "图片/对象缺失": "图片是否丢失或未正确链接；图题与图编号是否连续。",
    "版本记录": "版本记录日期是否填写、版本是否与正文/文件名一致。",
    "官网地址": "封底官网地址、邮箱、电话是否与手册语言对应。",
    "中文残留": "英文手册中是否混入未翻译的中文。",
}
FALLBACK_HINT = "检查该类问题是否有明确文本或版面证据；仅在证据充分时报告。"


def make_rule_no(language: str, comment: str, selected_text: str = "") -> str:
    raw = f"{language}||{comment}||{selected_text}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10].upper()
    return f"{LEARNED_PREFIX}{language.upper()}-{digest}"


def is_learned_rule(rule_no: Any) -> bool:
    return str(rule_no or "").upper().startswith(LEARNED_PREFIX)


def is_enabled(description: Any) -> bool:
    return str(description or "").strip().startswith(ENABLED_PREFIX)


def abstract_hint(category: Any) -> str:
    return CATEGORY_HINT.get(str(category or "").strip(), FALLBACK_HINT)


def strip_enabled_prefix(description: Any) -> str:
    value = str(description or "").strip()
    return value[len(ENABLED_PREFIX):].strip() if is_enabled(value) else value


def load_enabled_sections(db) -> list[dict]:
    """从数据库读已启用学习规则，转成审核依据 section。"""
    from app.models.rule import Rule

    rows = (
        db.query(Rule)
        .filter(Rule.rule_no.like(f"{LEARNED_PREFIX}%"))
        .all()
    )
    sections = []
    for row in rows:
        if not is_enabled(row.description):
            continue
        hint = strip_enabled_prefix(row.description)
        category = str(row.category or "人工学习规则")
        sections.append({
            "label": f"人工学习规则-{category}",
            "text": f"【人工学习规则 · {category}】\n{hint}\n"
                    f"注意：仅在本次文档有明确证据时报告，不照搬历史样例。",
            "priority": 4,
            "language": "both",
            "basis_type": "learned_rule",
            "tags": [" learned", "rule", category.strip()],
        })
    return sections
