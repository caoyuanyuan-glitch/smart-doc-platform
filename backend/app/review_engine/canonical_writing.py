"""外部规范写法库（DET-TERM-CANON-001）。

## 要解决的问题

上一轮的人工批注里，有一类问题**不是**文档内部的不一致，而是与
**外部约定写法**不符：

- 人工批注 #6：「小写」——`PE means Pair-end sequencing`，首字母应小写；
- 人工批注 #7：「小写」——`SE means Single-end sequencing`，首字母应小写。

`DET-TERM-BASELINE-001` 解决不了这类问题：文档里 `Pair-end` 与
`pair-end` 只出现前者，**文档内部是自洽的**，基线比对无从发现。
判定依据必须来自外部规范。

## 判定依据

维护一份**外部规范写法表**（`app/data/canonical_writing.json`），
表项形如：

    {
      "id": "c1",
      "canonical": "pair-end",
      "category": "测序类型",
      "note": "Illumina 体系通用写法，首字母小写",
      "variants": ["Pair-end", "Pair-End", "pair-End"]
    }

命中判据（全部满足才上报）：

1. 文档中出现 `variants` 里的某个写法；
2. 该写法**不是** `canonical` 本身（大小写敏感比较）；
3. 文档中**没有**出现过 `canonical` 写法——若文档本身两种写法混用，
   那属于文档内不一致，交给 `DET-TERM-BASELINE-001` 处理，
   本模块不越界。

第 3 条是关键的防误报约束：如果一份文档通篇写 `Pair-end`（作者
风格如此），只报一次全篇风格提示是合理的；**但如果文档里 `pair-end`
已经出现过**，那说明是**局部不一致**，此时应当按"逐处偏离多数写法"
上报，仍然只报偏离处，不报其他正确的 `pair-end` 位置。

## 明确不做的事

- 不做"哪个更规范"的推断——规范写法由外部表给定，表里没有的不管。
- 不改写文档内容，只报告位置与建议。
- 同一写法在全文的上报上限为 `_MAX_REPORTS_PER_PATTERN`，避免刷屏。
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path


_DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "canonical_writing.json"

# 同一种偏离写法的上报上限。
_MAX_REPORTS_PER_PATTERN = 6

# 只在英文文档语境下启用（本库全是英文规范写法）。
_ASCII_WORD = re.compile(r"[A-Za-z][A-Za-z0-9]*")


@lru_cache(maxsize=1)
def load_canonical_writing() -> tuple[dict, ...]:
    """加载外部规范写法表。文件缺失或损坏时返回空表（规则自动降级为不启用）。"""
    try:
        payload = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
    except Exception:
        return ()
    items = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return ()
    result: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        canonical = str(item.get("canonical") or "").strip()
        variants = item.get("variants") or []
        if not canonical or not isinstance(variants, list):
            continue
        cleaned = [
            str(v).strip()
            for v in variants
            if isinstance(v, (str, int, float)) and str(v).strip() and str(v).strip() != canonical
        ]
        if not cleaned:
            continue
        result.append({
            "id": str(item.get("id") or ""),
            "canonical": canonical,
            "category": str(item.get("category") or "术语写法"),
            "note": str(item.get("note") or ""),
            "variants": tuple(dict.fromkeys(cleaned)),
        })
    return tuple(result)


def _issue(rule, text, start, end, original, description, suggestion,
           *, category="术语写法", severity="general", confidence=88,
           audit_basis="外部规范写法库"):
    radius = 70
    context = re.sub(r"\s+", " ", text[max(0, start - radius):min(len(text), end + radius)]).strip()
    return {
        "severity": severity,
        "category": category,
        "rule": rule,
        "chapter": "",
        "original_text": original,
        "context": context,
        "suggestion": suggestion,
        "description": description,
        "audit_basis": audit_basis,
        "confidence": confidence,
        "source": "rule",
        "status": "pending",
        "position": json.dumps(
            {
                "start": start,
                "end": end,
                "area": "正文",
                "page": text[: max(0, start)].count("\f") + 1,
            },
            ensure_ascii=False,
        ),
    }


def _find_variant_occurrences(text: str, variant: str) -> list[tuple[int, int]]:
    """找出 `variant` 在文本中的所有出现位置（大小写敏感，词边界匹配）。"""
    pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(variant)}(?![A-Za-z0-9])")
    return [(m.start(), m.end()) for m in pattern.finditer(text)]


def find_canonical_writing_issues(text: str) -> list[dict]:
    """扫描文本，报告与外部规范写法不一致的位置。"""
    if not text:
        return []

    issues: list[dict] = []
    for item in load_canonical_writing():
        canonical = item["canonical"]
        canonical_occurrences = _find_variant_occurrences(text, canonical)
        for variant in item["variants"]:
            occurrences = _find_variant_occurrences(text, variant)
            if not occurrences:
                continue
            # 规范写法在文档中已经出现过：属于局部不一致，只报偏离处。
            # 规范写法从未出现：属于全篇风格偏离，同样只报偏离处，
            # 但描述里说明"全文未出现规范写法"。
            document_has_canonical = bool(canonical_occurrences)
            if document_has_canonical:
                detail = (
                    f"本文档中规范写法 `{canonical}` 已出现 {len(canonical_occurrences)} 次，"
                    f"但此处写作 `{variant}`，同一概念存在两种写法。"
                )
            else:
                detail = (
                    f"本文档全文未出现规范写法 `{canonical}`，"
                    f"此处写作 `{variant}`，与该术语的通行写法不一致。"
                )
            if item["note"]:
                detail += f"（{item['note']}）"
            for start, end in occurrences[:_MAX_REPORTS_PER_PATTERN]:
                issues.append(_issue(
                    "DET-TERM-CANON-001",
                    text, start, end, variant,
                    detail,
                    f"建议改为 `{canonical}`。",
                    category=item["category"],
                ))
            if len(occurrences) > _MAX_REPORTS_PER_PATTERN:
                pass  # 超出上限的部分不重复上报，避免刷屏
    return issues


def check_canonical_writing(text: str) -> list[dict]:
    """外部规范写法库入口。"""
    try:
        return find_canonical_writing_issues(text)
    except Exception:
        return []
