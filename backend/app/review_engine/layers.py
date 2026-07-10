import re
from typing import Any


DETERMINISTIC_LAYER = "deterministic"
STRUCTURAL_LAYER = "structural_consistency"
AI_ASSISTED_LAYER = "ai_assisted"
UNKNOWN_LAYER = "unknown"


def _value(issue: dict[str, Any], key: str) -> str:
    return str(issue.get(key, "") if isinstance(issue, dict) else getattr(issue, key, "") or "")


def classify_issue_layer(issue: dict[str, Any]) -> str:
    source = _value(issue, "source").lower()
    rule = _value(issue, "rule").upper()
    category = _value(issue, "category")
    description = _value(issue, "description")
    basis = _value(issue, "audit_basis")
    text = " ".join([rule, category, description, basis]).lower()

    structural_pattern = (
        r"适用范围|硬件配置|表图编号|编号|货号一致|章节结构|pos\d|cross|reference|table|figure|"
        r"图片|对象缺失|分页|跨页|下一页|topic|主题结构|appendix|附录|页眉跨行|版式|竖线|表格"
    )

    if source == "ai":
        if re.search(structural_pattern, text, re.IGNORECASE):
            return STRUCTURAL_LAYER
        return AI_ASSISTED_LAYER

    deterministic_patterns = (
        r"unit|单位|空格|字号|公式|url|官网|型号|model|date|日期|cat\.?\s*no|货号写法|中文残留|标点|punct|版本记录|revision|history",
        r"^(R\d+|HR\d+|UNIT-|PUNCT-|SPELL|GRAMMAR-|DOC-MODEL|DOC-URL|CHECKLIST-|DET-)",
    )
    if re.search(deterministic_patterns[0], text, re.IGNORECASE) or re.search(deterministic_patterns[1], rule, re.IGNORECASE):
        return DETERMINISTIC_LAYER

    if re.search(structural_pattern, text, re.IGNORECASE) or re.search(r"^STRUCT-", rule, re.IGNORECASE):
        return STRUCTURAL_LAYER

    if source:
        return AI_ASSISTED_LAYER
    return UNKNOWN_LAYER


def count_issue_layers(issues: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for issue in issues:
        layer = classify_issue_layer(issue)
        counts[layer] = counts.get(layer, 0) + 1
    return counts
