import json
import re
from collections import Counter
from typing import Any


SEVERITY_RANK = {"fatal": 4, "serious": 3, "general": 2, "suggestion": 1}
SOURCE_RANK = {"rule": 4, "term": 3, "grammar": 2, "ai": 1, "spellcheck": 0}

LOW_VALUE_RULES = {
    "R002",
    "R003",
    "R006",
    "R014",
    "R028",
    "R029",
    "R035",
    "R036",
    "HR009",
    "PUNCT-002",
    "TENSE-001",
}

TOPIC_DETERMINISTIC_SHADOW = {"revision", "trademark", "credential", "network", "rohs", "appendix_table"}
TOPIC_AI_SINGLETON = {"rohs"}

HIGH_VALUE_PATTERN = re.compile(
    r"default\s+(?:account|password|username)|credential|password|ip\s+address|"
    r"\b(?:\d{1,3}\.){3}\d{1,3}:\d{2,5}\b|revision\s+history|empty\s+table|"
    r"missing\s+(?:object|icon|button|step|entry|field)|incomplete\s+sentence|"
    r"trademark|copyright|compliance|ROHS|DNBSEQ|CYY|人工审核|发布前自检|Checklist|"
    r"默认账号|默认密码|密码|内网|端口|版本记录|空表|缺失|不完整|合规|法规|商标|版权|"
    r"重复|物料编码|术语一致|图文引用|图号|表格内容|操作步骤|信息完整",
    re.IGNORECASE,
)

LOW_VALUE_PATTERN = re.compile(
    r"^an?\s+[a-z](?:\s|$)|^\d+(?:arc|cram|fastq|fq|bam|bcl|nvme|ssd|raid)$|"
    r"^click$|^please\s+contact$|^performing\s+the\s+following\s+steps$|"
    r"\b(?:nt responds|emplate|analysi|the same pr)\b|\[table content\]|check\s+if|"
    r"Browse|Edit|括号后请添加空格|建议拆分为多个短句|普通语法|冠词|标点|格式微调|"
    r"formatting\s+artifact|\btab\b|\ban\s+fq\b|\bto\s+to\b|after\s+login|"
    r"no\s+(?:issue|violation|change)\b|no\s+change\s+needed|appears\s+valid|is\s+correct\b|"
    r"verify\s+if\s+this\s+is\s+the\s+correct|preposition\s+'.*?'\s+is\s+ambiguous|is\s+clearer\s+for\s+describing",
    re.IGNORECASE,
)

VISUAL_LAYOUT_PATTERN = re.compile(
    r"列宽|拉大列宽|调整列宽|溢出单元格|版式|字体/版式|字体|字号|图标大小|icon大小|"
    r"图片尺寸|图片大小|矢量图|挪到右边|竖线|折线|太密集|太杂乱|样式没有设置|"
    r"table/layout|layout|column\s+width|cell\s+overflow|font\s+size|icon\s+size|image\s+size|visual",
    re.IGNORECASE,
)


def issue_value(issue: Any, key: str, default: Any = "") -> Any:
    if isinstance(issue, dict):
        return issue.get(key, default)
    return getattr(issue, key, default)


def set_issue_value(issue: Any, key: str, value: Any) -> None:
    if isinstance(issue, dict):
        issue[key] = value
    else:
        setattr(issue, key, value)


def issue_to_mapping(issue: Any) -> dict[str, Any]:
    return {
        "id": issue_value(issue, "id", 0),
        "source": issue_value(issue, "source", "") or "rule",
        "rule": issue_value(issue, "rule", "") or "",
        "category": issue_value(issue, "category", "") or "",
        "severity": issue_value(issue, "severity", "") or "general",
        "original_text": issue_value(issue, "original_text", "") or "",
        "context": issue_value(issue, "context", "") or "",
        "suggestion": issue_value(issue, "suggestion", "") or "",
        "description": issue_value(issue, "description", "") or "",
        "audit_basis": issue_value(issue, "audit_basis", "") or "",
        "confidence": issue_value(issue, "confidence", 0) or 0,
        "position": issue_value(issue, "position", "") or "",
        "chapter": issue_value(issue, "chapter", "") or "",
        "status": issue_value(issue, "status", "") or "",
    }


def normalize_text(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def compact_text(text: Any) -> str:
    return re.sub(r"\s+", "", str(text or "")).lower()


def issue_blob(issue: Any) -> str:
    return " ".join(str(issue_value(issue, key, "") or "") for key in [
        "source",
        "rule",
        "category",
        "severity",
        "original_text",
        "context",
        "suggestion",
        "description",
        "audit_basis",
    ])


def parse_position_start(position: Any) -> int:
    if isinstance(position, int):
        return position
    if not position:
        return 0
    try:
        parsed = json.loads(position) if isinstance(position, str) and position.strip().startswith("{") else None
    except Exception:
        parsed = None
    if isinstance(parsed, dict):
        return int(parsed.get("start") or 0)
    match = re.match(r"(\d+)-\d+", str(position))
    return int(match.group(1)) if match else 0


def issue_topic(issue: Any) -> str:
    text = issue_blob(issue)
    if re.search(r"revision\s+history|版本记录", text, re.IGNORECASE):
        return "revision"
    if re.search(r"trademark|DNBSEQ\s*TM|DNBSEQTM|商标", text, re.IGNORECASE):
        return "trademark"
    if re.search(r"default\s+(?:account|password|username)|credential|默认账号|默认密码|密码", text, re.IGNORECASE):
        return "credential"
    if re.search(r"(?:\d{1,3}\.){3}\d{1,3}:\d{2,5}|ip\s+address|端口", text, re.IGNORECASE):
        return "network"
    if re.search(r"ROHS|有害物质的名称及含[有量]信息表|有害物质的名称及含量", text, re.IGNORECASE):
        return "rohs"
    if re.search(r"DOC-NOTICE-003|Affected\s+Products|Change\s+Details|table\s+content|table\s+structure|附录信息完整性|受影响产品", text, re.IGNORECASE):
        return "appendix_table"
    return ""


def is_high_value(issue: Any) -> bool:
    rule = str(issue_value(issue, "rule", "") or "").upper()
    if is_visual_layout_issue(issue):
        return False
    if rule.startswith(("DOC-", "CHECKLIST-", "CYY-")):
        return True
    if rule.startswith("STRUCT-") and re.search(r"图文引用|图号|表格内容|步骤|术语|重复|完整", issue_blob(issue), re.IGNORECASE):
        return True
    return bool(HIGH_VALUE_PATTERN.search(issue_blob(issue)))


def is_visual_layout_issue(issue: Any) -> bool:
    data = issue_to_mapping(issue)
    rule = str(data["rule"] or "").upper()
    category = normalize_text(data["category"])
    blob = issue_blob(data)
    if category in {"表格/版式", "图片/对象缺失", "字体/版式细节"}:
        return True
    if rule in {"STRUCT-LAYOUT-001", "STRUCT-IMAGE-001", "DET-TYPO-001"}:
        return True
    return bool(VISUAL_LAYOUT_PATTERN.search(blob))


def value_score(issue: Any) -> int:
    data = issue_to_mapping(issue)
    rule = str(data["rule"] or "").upper()
    source = str(data["source"] or "").lower()
    category = str(data["category"] or "")
    severity = str(data["severity"] or "general").lower()
    confidence = int(data["confidence"] or 0)

    score = 50
    score += {"fatal": 25, "serious": 18, "general": 6, "suggestion": -8}.get(severity, 0)
    score += {"rule": 8, "term": 6, "ai": -2, "spellcheck": -20}.get(source, 0)
    if confidence >= 95:
        score += 10
    elif confidence >= 90:
        score += 6
    elif confidence and confidence < 80:
        score -= 12
    if is_high_value(data):
        score += 30
    if LOW_VALUE_PATTERN.search(normalize_text(data["original_text"])) or LOW_VALUE_PATTERN.search(issue_blob(data)):
        score -= 55
    if rule in LOW_VALUE_RULES:
        score -= 45
    if source == "spellcheck":
        score -= 40
    if source == "ai" and category.lower() in {"spelling", "grammar", "punctuation"} and not is_high_value(data):
        score -= 20
    if not data["original_text"] or not data["suggestion"]:
        score -= 20
    return max(0, min(100, score))


def is_noise(issue: Any, counters: Counter | None = None) -> bool:
    counters = counters if counters is not None else Counter()
    data = issue_to_mapping(issue)
    rule = str(data["rule"] or "").upper()
    source = str(data["source"] or "").lower()
    original = normalize_text(data["original_text"])
    suggestion = normalize_text(data["suggestion"])
    description = normalize_text(data["description"])
    context = normalize_text(data["context"])
    category = normalize_text(data["category"])

    if source == "spellcheck":
        return True
    if is_visual_layout_issue(data):
        return True
    if rule in LOW_VALUE_RULES:
        return True
    if rule == "TERM-001" and re.fullmatch(r"click", original, re.IGNORECASE) and re.fullmatch(r"tap", suggestion, re.IGNORECASE):
        return True
    if rule == "R013" and re.fullmatch(r"\d+(?:arc|cram|fastq|fq|bam|bcl|nvme|ssd|raid)", original, re.IGNORECASE):
        return True
    if rule in {"R023", "GRAMMAR"} and re.fullmatch(r"an?\s+[a-z](?:\s|$).*", original, re.IGNORECASE):
        return True
    if rule == "GRAMMAR-003" and re.search(r"\bsample\s+(?:information\s+)?have\s+been\b", original, re.IGNORECASE):
        counters["GRAMMAR_SAMPLE_HAVE_BEEN"] += 1
        return counters["GRAMMAR_SAMPLE_HAVE_BEEN"] > 2
    if rule == "R024" and re.search(r"\bto\s+to\b", original, re.IGNORECASE):
        if re.search(r"\bSwitch\s+to\s+to\s+generate\b", context or original, re.IGNORECASE):
            return True
        counters["R024_TO_TO"] += 1
        return counters["R024_TO_TO"] > 1
    if rule in {"HR008", "GRAMMAR-002"} and re.fullmatch(r"(?:please\s+contact|after\s+login)", original, re.IGNORECASE):
        return True
    if source == "ai" and value_score(data) < 45 and not is_high_value(data):
        return True
    if source == "ai" and LOW_VALUE_PATTERN.search(issue_blob(data)):
        return True
    if source == "ai" and re.search(r"\[[^\]]*(?:table content|company name|address|contact details)[^\]]*\]", suggestion, re.IGNORECASE):
        return True
    if source == "ai" and category.lower() in {"format", "punctuation"} and re.search(r"space\s+before\s+colon|remove\s+space\s+before\s+colon|punctuation", issue_blob(data), re.IGNORECASE):
        return True
    if source == "ai" and re.search(r"\bcheck\s+if\b|是否使用|是否正确", suggestion, re.IGNORECASE):
        return True
    if source == "ai" and re.search(r"\b(?:Browse|Edit)\b", suggestion) and not re.search(r"\b(?:Browse|Edit)\b", original):
        return True
    if source == "ai" and re.match(r"^Tips\b", original, re.IGNORECASE) and re.search(r"formatting\s+artifact|tab", f"{rule} {description} {suggestion}", re.IGNORECASE):
        return True
    if source == "ai" and re.search(r"missing\s+object|缺少(?:按钮|图标|对象)|click", f"{rule} {category} {description}", re.IGNORECASE):
        counters["AI_CLICK_OBJECT"] += 1
        return counters["AI_CLICK_OBJECT"] > 3
    if LOW_VALUE_PATTERN.search(original) and not is_high_value(data):
        return True
    return False


def normalize_issue(issue: Any) -> Any:
    data = issue_to_mapping(issue)
    severity = str(data["severity"] or "general").lower()
    if severity not in SEVERITY_RANK:
        severity = "general"
    set_issue_value(issue, "severity", severity)
    set_issue_value(issue, "source", data["source"] or "rule")
    set_issue_value(issue, "category", data["category"] or "其他")
    set_issue_value(issue, "rule", data["rule"] or "AI")
    set_issue_value(issue, "original_text", normalize_text(data["original_text"]))
    set_issue_value(issue, "context", data["context"] or "")
    set_issue_value(issue, "suggestion", normalize_text(data["suggestion"]))
    set_issue_value(issue, "description", data["description"] or "")
    set_issue_value(issue, "audit_basis", data["audit_basis"] or "审核流水线")
    set_issue_value(issue, "confidence", int(data["confidence"] or 0))
    set_issue_value(issue, "review_value_score", value_score(issue))
    return issue


def dedupe_key(issue: Any) -> str:
    data = issue_to_mapping(issue)
    topic = issue_topic(data)
    original = compact_text(data["original_text"])
    source = str(data["source"] or "").lower()
    rule = str(data["rule"] or "").upper()
    if topic:
        return f"topic|{topic}|{original[:80]}"
    if source == "spellcheck" or rule == "SPELL":
        return f"spell|{original}|{data['position']}"
    if rule in {"UNIT-003", "UNIT-004", "HR011", "STYLE-003", "HR008", "GRAMMAR-001", "GRAMMAR-002"}:
        return f"{rule}|{original}|{data['position']}"
    return f"{rule}|{original}|{compact_text(data['chapter'])}"


def issue_rank(issue: Any) -> tuple[int, int, int, int, int]:
    data = issue_to_mapping(issue)
    return (
        value_score(data),
        SEVERITY_RANK.get(str(data["severity"] or "general").lower(), 0),
        SOURCE_RANK.get(str(data["source"] or "").lower(), 0),
        int(data["confidence"] or 0),
        -parse_position_start(data["position"]),
    )


def sort_key(issue: Any) -> tuple[int, int, int, int, int]:
    data = issue_to_mapping(issue)
    severity = str(data["severity"] or "general").lower()
    severity_group = {"fatal": 0, "serious": 1}.get(severity, 2)
    return (
        severity_group,
        -value_score(data),
        -SEVERITY_RANK.get(severity, 0),
        parse_position_start(data["position"]),
        int(data["id"] or 0),
    )


def suppress_shadowed_ai(issues: list[Any]) -> list[Any]:
    deterministic_topics = set()
    deterministic_keys = set()
    for issue in issues:
        data = issue_to_mapping(issue)
        if str(data["source"] or "").lower() == "ai":
            continue
        topic = issue_topic(data)
        original = compact_text(data["original_text"])
        if topic:
            deterministic_topics.add(topic)
        if topic and original:
            deterministic_keys.add((topic, original))

    filtered = []
    seen_ai_topics = set()
    for issue in issues:
        data = issue_to_mapping(issue)
        if str(data["source"] or "").lower() == "ai":
            topic = issue_topic(data)
            original = compact_text(data["original_text"])
            if topic in TOPIC_DETERMINISTIC_SHADOW and topic in deterministic_topics:
                continue
            if topic and original and (topic, original) in deterministic_keys:
                continue
            if topic in TOPIC_AI_SINGLETON:
                if topic in seen_ai_topics:
                    continue
                seen_ai_topics.add(topic)
        filtered.append(issue)
    return filtered


def select_review_issues(issues: list[Any], min_score: int = 45, status_filter: bool = False) -> list[Any]:
    counters: Counter = Counter()
    selected_by_key: dict[str, Any] = {}
    for raw_issue in issues or []:
        issue = normalize_issue(raw_issue)
        data = issue_to_mapping(issue)
        status = str(data["status"] or "").lower()
        if status_filter and status not in {"", "pending", "confirmed", "converted_to_rule"}:
            continue
        if not data["original_text"]:
            continue
        if is_noise(issue, counters):
            continue
        threshold = 38 if str(data["severity"] or "").lower() in {"fatal", "serious"} else min_score
        if value_score(issue) < threshold:
            continue
        key = dedupe_key(issue)
        existing = selected_by_key.get(key)
        if existing is None or issue_rank(issue) > issue_rank(existing):
            selected_by_key[key] = issue

    selected = suppress_shadowed_ai(list(selected_by_key.values()))
    return sorted(selected, key=sort_key)
