import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class HumanAnnotation:
    file: str
    page: str
    annotation_type: str
    author: str
    comment: str
    selected_text: str
    context: str
    category: str
    layer: str
    expected_rule: str


def _clean(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _parse_bullet(block: str, label: str) -> str:
    match = re.search(rf"^- {re.escape(label)}: (.*)$", block, flags=re.MULTILINE)
    return _clean(match.group(1)) if match else ""


def classify_human_annotation(comment: str, selected_text: str = "", context: str = "") -> tuple[str, str, str]:
    comment_text = str(comment or "").lower()
    text = " ".join([comment, selected_text, context]).lower()

    priority_patterns = [
        (r"出现了中文|中文", "中文残留", "deterministic", "DET-CN-001"),
        (r"缺少.*ne384|ne384.*硬件配置|不是还有ne384", "适用范围/硬件配置", "structural_consistency", "STRUCT-SCOPE-001"),
        (r"图片编号|图.*编号|table.*编号|编号.*连续", "表图编号", "structural_consistency", "STRUCT-FIGTAB-001"),
        (r"操作步骤.*祈使句|祈使句", "操作步骤语气", "ai_assisted", "AI-PROC-001"),
        (r"最新版本记录|版本记录.*最上面|日期留空", "版本记录", "deterministic", "DET-REVISION-001"),
        (r"统一大小写|大小写统一", "标题大小写", "deterministic", "DET-TITLE-CASE-001"),
        (r"物料编码|申请物料编码|0-00x", "物料编码", "deterministic", "DET-MATERIAL-001"),
        (r"母公司|同名|本公司|长光", "公司主体表述", "ai_assisted", "AI-COMPANY-001"),
        (r"nmpa|纸质说明书|电子版说明书", "法规/注册确认", "ai_assisted", "AI-REG-001"),
    ]
    for pattern, category, layer, rule in priority_patterns:
        if re.search(pattern, comment_text, re.IGNORECASE):
            return category, layer, rule

    structural_patterns = [
        (r"图片丢失|重新链接图片|重新截屏|重新截图|截图|图丑|矢量图|图标|icon|image|figure missing", "图片/对象缺失", "STRUCT-IMAGE-001"),
        (r"搞到下一页|跨页|下一页|分页|page break", "分页与标题边界", "STRUCT-PAGE-001"),
        (r"topic|主题|页眉跨行|appendix|附录", "主题结构", "STRUCT-TOPIC-001"),
        (r"表格|表头|竖线|多了竖线|边框|列宽|行高|均匀分布列|合并单元格|出框|拉大宽度|拉大列宽|调整列宽|溢出单元格|折线|太密集|挪到右边|样式没有设置对", "表格/版式", "STRUCT-LAYOUT-001"),
        (r"前文都是|统一|一致|同上|同下|同步修改|这个不是试剂名称|平行结构|冒号前面", "术语一致性", "STRUCT-TERM-001"),
        (r"重复出现|重复了|内容重合|意思重复", "重复内容", "STRUCT-DUP-001"),
        (r"主机.*其他部件|其他部件没有介绍|组成.*部件", "结构完整性", "STRUCT-COMPONENT-001"),
        (r"有序列表|不是一个步骤|操作步骤如下|合并到上一步", "步骤结构", "STRUCT-STEP-001"),
    ]
    for pattern, category, rule in structural_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return category, "structural_consistency", rule

    deterministic_patterns = [
        (r"缺空格|隔开|空格|℃|μl|ml|ng/μl|fmol|单位前面加空格", "单位/空格", "DET-SPACE-001"),
        (r"字号|上角标|下角标|公式|蓝色字|字小|粗了|横线|间隙|距离", "字体/版式细节", "DET-TYPO-001"),
        (r"确认.*版本|是不是\d|version|rev\b|版本", "版本记录", "DET-REVISION-001"),
        (r"标点|句号|逗号|括号|缺句号|多余句号|双引号|反向", "标点符号", "DET-PUNCT-001"),
        (r"地址|网址|global-mgitech|官网|封底", "官网地址", "DET-URL-001"),
        (r"货号|cat\.?\s*no", "货号写法", "DET-CATNO-001"),
        (r"trademark|商标声明", "商标声明", "DET-TRADEMARK-001"),
        (r"乘号", "符号规范", "DET-SYMBOL-001"),
        (r"otc.*oct|oct", "术语拼写", "DET-TERM-SPELL-001"),
        (r"为什么是/|不是一个范围", "范围/数值格式", "DET-RANGE-001"),
    ]
    for pattern, category, rule in deterministic_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return category, "deterministic", rule

    ai_patterns = [
        (r"sentence style|语句|表达|措辞|语法|口语化|改为|建议改为|删了|typo|the\b|with\b|that\b|device\b|logging\b|for selecting", "表达与句式", "AI-STYLE-001"),
        (r"确认|检查|是否|当$|真是这样写吗|项目组提供|资质|产品经理|项目经理|源头文件也要改|密码", "人工确认项", "AI-CHECK-001"),
    ]
    for pattern, category, rule in ai_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return category, "ai_assisted", rule

    return "人工审核其他项", "ai_assisted", "AI-HUMAN-OTHER"


def parse_human_annotation_markdown(path: str | Path) -> list[HumanAnnotation]:
    text = Path(path).read_text(encoding="utf-8-sig")
    annotations: list[HumanAnnotation] = []
    blocks = re.split(r"(?=^## \d+\. )", text, flags=re.MULTILINE)
    for block in blocks:
        header = re.search(r"^## \d+\. (.*?) · 第 (.*?) 页", block, flags=re.MULTILINE)
        if not header:
            continue
        comment = _parse_bullet(block, "人工意见")
        if not comment or comment == "-":
            continue
        selected_text = _parse_bullet(block, "选中文本")
        context = _parse_bullet(block, "附近正文")
        category, layer, expected_rule = classify_human_annotation(comment, selected_text, context)
        annotations.append(HumanAnnotation(
            file=_clean(header.group(1)),
            page=_clean(header.group(2)),
            annotation_type=_parse_bullet(block, "批注类型"),
            author=_parse_bullet(block, "批注人"),
            comment=comment,
            selected_text=selected_text,
            context=context,
            category=category,
            layer=layer,
            expected_rule=expected_rule,
        ))
    return annotations


def summarize_annotations(annotations: list[HumanAnnotation]) -> dict[str, Any]:
    by_layer: dict[str, int] = {}
    by_category: dict[str, int] = {}
    by_file: dict[str, int] = {}
    by_rule: dict[str, int] = {}
    for item in annotations:
        by_layer[item.layer] = by_layer.get(item.layer, 0) + 1
        by_category[item.category] = by_category.get(item.category, 0) + 1
        by_file[item.file] = by_file.get(item.file, 0) + 1
        by_rule[item.expected_rule] = by_rule.get(item.expected_rule, 0) + 1
    return {
        "total": len(annotations),
        "by_layer": dict(sorted(by_layer.items(), key=lambda pair: (-pair[1], pair[0]))),
        "by_category": dict(sorted(by_category.items(), key=lambda pair: (-pair[1], pair[0]))),
        "by_rule": dict(sorted(by_rule.items(), key=lambda pair: (-pair[1], pair[0]))),
        "by_file": dict(sorted(by_file.items(), key=lambda pair: (-pair[1], pair[0]))),
    }


def annotations_to_json(annotations: list[HumanAnnotation]) -> str:
    payload = {
        "summary": summarize_annotations(annotations),
        "annotations": [asdict(item) for item in annotations],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _norm_for_match(text: Any) -> str:
    text = _clean(text).lower()
    return re.sub(r"[\s\.,;:!?，。；：！？、()（）\[\]【】{}<>\-–—_/|]+", "", text)


def _issue_blob(issue: dict[str, Any]) -> str:
    return _norm_for_match(" ".join(str(issue.get(key, "")) for key in [
        "category", "rule", "original_text", "suggestion", "description", "context", "audit_basis",
    ]))


def _matches_expected_rule(item: HumanAnnotation, issue: dict[str, Any], blob: str) -> bool:
    rule = str(issue.get("rule", "") or "").upper()
    category = str(issue.get("category", "") or "")
    text = " ".join([item.comment, item.selected_text, item.context]).lower()

    if item.expected_rule == "DET-REVISION-001":
        return rule.startswith("DOC-REV") or "版本记录" in category
    if item.expected_rule == "DET-CN-001":
        return rule == "ENG-CN-001" or "中文混入" in category
    if item.expected_rule == "STRUCT-SCOPE-001":
        return rule in {"DOC-SCOPE-001", "DOC-MODEL-002"} or ("ne384" in blob and "硬件配置" in blob)
    if item.expected_rule == "STRUCT-FIGTAB-001":
        return rule.startswith("DOC-FIGTAB") or "表图编号" in category
    if item.expected_rule == "AI-PROC-001":
        return rule == "DOC-PROC-001" or "操作步骤语气" in category
    if item.expected_rule == "DET-TITLE-CASE-001":
        return rule == "DOC-TITLE-001" or "标题大小写" in category
    if item.expected_rule == "AI-CHECK-001" and "pos" in text:
        return rule == "DOC-POS-001" or "台面位置" in category
    if item.expected_rule == "DET-SPACE-001":
        selected = _norm_for_match(item.selected_text)
        if selected and len(selected) >= 2 and selected in blob:
            return True
        return rule in {"R010", "HR004", "UNIT-002", "UNIT-003", "UNIT-004", "HR006"}
    if item.expected_rule == "AI-STYLE-001":
        return rule in {"DOC-MICRO-001", "DOC-PROC-001", "GRAMMAR-003", "GRAMMAR-004", "GRAMMAR-005"}
    return False


def evaluate_against_annotations(issues: list[dict[str, Any]], annotations: list[HumanAnnotation]) -> dict[str, Any]:
    issue_pairs = [(issue, _issue_blob(issue)) for issue in issues]

    hits = []
    misses = []
    for item in annotations:
        selected = _norm_for_match(item.selected_text)
        comment = _norm_for_match(item.comment)
        context = _norm_for_match(item.context[:160])
        matched = False
        for issue, blob in issue_pairs:
            if _matches_expected_rule(item, issue, blob):
                matched = True
                break
            if selected and len(selected) >= 2 and selected in blob:
                matched = True
                break
            if selected and len(selected) >= 2 and any(part and len(part) >= 2 and part in blob for part in re.split(r"[-,，;；\s]+", selected)):
                matched = True
                break
            original = _norm_for_match(issue.get("original_text", ""))
            if original and len(original) >= 1 and selected and original in selected:
                matched = True
                break
            if comment and len(comment) >= 4 and comment in blob:
                matched = True
                break
            if context and len(context) >= 12 and context[:40] in blob:
                matched = True
                break
        record = asdict(item)
        if matched:
            hits.append(record)
        else:
            misses.append(record)

    return {
        "human_total": len(annotations),
        "matched": len(hits),
        "missed": len(misses),
        "match_rate": round(len(hits) / len(annotations), 4) if annotations else 0,
        "misses_by_category": summarize_annotations([HumanAnnotation(**item) for item in misses])["by_category"] if misses else {},
        "misses": misses[:50],
    }
