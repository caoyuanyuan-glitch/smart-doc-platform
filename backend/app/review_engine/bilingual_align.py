"""Deterministic zh-CN / English alignment for compare-audit."""

from __future__ import annotations

import json
import re


CN_FLOW_KEYWORDS = ("操作流程", "实验步骤", "操作步骤", "注意事项", "工作流程")
EN_FLOW_HEADINGS = (
    "operating procedure",
    "experimental procedure",
    "operating instructions",
    "workflow",
    "precautions",
    "notes and precautions",
)

_CHAPTER_CN_RE = re.compile(r"^第\s*([0-9一二三四五六七八九十]+)\s*章\s*(.*)$")
_CHAPTER_EN_RE = re.compile(r"^chapter\s+(\d+)\s*[:.\-–]?\s*(.*)$", re.I)
_APPENDIX_CN_RE = re.compile(r"^附录\s*([A-Z0-9])\s*(.*)$")
_APPENDIX_EN_RE = re.compile(r"^appendix\s+([A-Z0-9])\s*(.*)$", re.I)
_NUMBERED_HEADING_RE = re.compile(r"^(\d+(?:\.\d+){1,3})\s+([\u4e00-\u9fffA-Z].{1,80})$")
_MEASUREMENT_HEADING_RE = re.compile(
    r"^(?:"
    r"[×xX]\s*\d"
    r"|mL|ml|L|μL|µL|uL|kg|g|mg|mm|cm|inches|inch|in|ft|°C|℃|°F|℉|%"
    r"|\d+(?:\.\d+)?\s*(?:mL|ml|L|μL|µL|uL|kg|g|mg|mm|cm|m|inches|inch|in|ft|°C|℃|°F|℉|%|V|W|Hz|rpm)"
    r")"
)
_STEP_RE = re.compile(
    r"^(?:step\s*\d+\s*[:：.\-]?\s*|\d+[\.)、]\s+|[一二三四五六七八九十]+[、.]\s*|[-*•]\s+)",
    re.I,
)
_TOC_RE = re.compile(r"\.{3,}\s*\d{0,3}$")
_CN_NUM = {
    "一": "1", "二": "2", "三": "3", "四": "4", "五": "5",
    "六": "6", "七": "7", "八": "8", "九": "9", "十": "10",
}
_CATALOG_RE = re.compile(
    r"(?:"
    r"(?<![A-Za-z])[A-Za-z]{2,8}-\d{2,}[A-Za-z0-9+\-]*"
    r"|\d{3,}-\d{2,}(?:-\d{2,})+"
    r"|DNBSEQ[A-Za-z0-9+\-]*"
    r")",
    re.I,
)
_UNIT_VALUE_RE = re.compile(
    r"(?<![A-Za-z0-9.])\d+(?:\.\d+)?\s*"
    r"(?:℃|°C|°F|℉|%|％|mm|cm|kg|g|mg|μL|µL|uL|mL|L|kW|kV|Hz|rpm|min)"
    r"(?![A-Za-z])"
)
_VERSION_RE = re.compile(r"\b[VR]\d+(?:\.\d+)+\b", re.I)
_YEAR_RE = re.compile(r"^(?:19|20)\d{2}$")
_DOC_NO_RE = re.compile(r"^\d{3}-\d{6}(?:-\d{2})?$")
_DURATION_TOKEN_RE = re.compile(r"^\d+(?:\.\d+)?min$")
_POSTAL_TOKEN_RE = re.compile(r"^[a-z]{2}-\d{3,4}$")
_PHONE_TOKEN_RE = re.compile(r"^\d{3,}-\d{2,}(?:-\d{2,})+$")
_CONTACT_RE = re.compile(r"@|\+?\d[\d\- ()]{6,}")


def detect_doc_language(text: str) -> str:
    content = str(text or "")
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", content)
    english_chars = re.findall(r"[A-Za-z]", content)
    if len(chinese_chars) > len(english_chars) * 2:
        return "cn"
    if len(english_chars) > len(chinese_chars) * 2:
        return "en"
    return "both"


def is_bilingual_compare(main_text: str, reference_texts: list[str]) -> bool:
    sides = [detect_doc_language(main_text)] + [detect_doc_language(text) for text in reference_texts]
    return "cn" in sides and "en" in sides


def language_label(lang: str) -> str:
    return {"cn": "中文", "en": "英文", "both": "中英混合"}.get(lang, lang or "-")


def _normalize_line(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _normalize_chapter_number(raw: str) -> str:
    value = str(raw or "").strip()
    return _CN_NUM.get(value, value)


def _is_probable_heading(title: str) -> bool:
    text = _normalize_line(title)
    if not text or len(text) > 80:
        return False
    if re.search(r"[。；;]", text):
        return False
    if _MEASUREMENT_HEADING_RE.match(text):
        return False
    if _STEP_RE.match(text):
        return False
    return True


def _parse_heading(line: str):
    text = _normalize_line(line)
    if not text or len(text) > 90:
        return None
    if _TOC_RE.search(text) and len(text) <= 60:
        return None

    match = _CHAPTER_CN_RE.match(text)
    if match and _is_probable_heading(match.group(2) or text):
        return _normalize_chapter_number(match.group(1)), _normalize_line(match.group(2) or text)
    match = _CHAPTER_EN_RE.match(text)
    if match and _is_probable_heading(match.group(2) or text):
        return match.group(1), _normalize_line(match.group(2) or text)
    match = _APPENDIX_CN_RE.match(text) or _APPENDIX_EN_RE.match(text)
    if match:
        return f"A{match.group(1).upper()}", _normalize_line(match.group(2) or text)
    match = _NUMBERED_HEADING_RE.match(text)
    if match and _is_probable_heading(match.group(2)):
        return match.group(1), _normalize_line(match.group(2))
    return None


def extract_headings(text: str) -> list[dict]:
    lines = [_normalize_line(line) for line in re.split(r"\r?\n+", str(text or ""))]
    headings = []
    current = None
    for line in lines:
        if not line:
            continue
        parsed = _parse_heading(line)
        if parsed:
            number, title = parsed
            current = {"number": number, "title": title, "body": []}
            headings.append(current)
            continue
        if current is not None:
            current["body"].append(line)
    for item in headings:
        item["body_text"] = " ".join(item["body"])[:1200]
    return headings


def _title_key(text: str) -> str:
    value = _normalize_line(text).casefold()
    value = re.sub(r"\s+\d{1,3}$", "", value)
    value = re.sub(r"[（()）]", "", value)
    value = value.replace("&", " and ")
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", value)


_TOC_LINE_RE = re.compile(r"^(.{2,80}?)\s+(\d{1,3})$")
SECTION_TITLE_PAIRS = (
    ("约定", "Conventions used in this manual"),
    ("通用安全", "General safety"),
    ("电气安全", "Electrical safety"),
    ("机械安全", "Mechanical safety"),
    ("配件安全", "Components safety"),
    ("生物安全", "Biological safety"),
    ("符号", "Symbols"),
    ("外箱", "Packaging"),
    ("仪器", "Device"),
    ("标签", "Label"),
    ("适用范围", "Intended use"),
    ("工作原理", "Working principle"),
    ("结构组成", "Structural composition"),
    ("基本组件", "Basic components"),
    ("前视图", "Front view"),
    ("后视图", "Back view"),
    ("左视图", "Left view"),
    ("右视图", "Right view"),
    ("载片仓视图", "Flow cell compartment"),
    ("载片仓", "Flow cell compartment"),
    ("试剂仓视图", "Reagent compartment"),
    ("试剂仓", "Reagent compartment"),
    ("控制软件", "Control software"),
    ("概述", "Overview"),
    ("主界面", "Main interface"),
    ("日志界面", "Log interface"),
    ("设置界面", "Settings interface"),
    ("维护界面", "Maintenance interface"),
    ("关于界面", "About interface"),
    ("锁屏/重启/关机界面", "Lock screen/Restart computer/Shutdown interface"),
    ("拼接任务界面", "Stitch task interface"),
    ("场地要求", "Site requirements"),
    ("网络要求", "Network requirements"),
    ("仪器要求", "Device requirements"),
    ("电源要求", "Power supply requirements"),
    ("辅助设备要求", "Peripheral device requirements"),
    ("推荐耗材清单", "Recommended consumable list"),
    ("准备试剂槽和载片", "Preparing the reagent cartridge and flow cell"),
    ("用于染色的试剂槽和载片", "Reagent cartridge and flow cell for staining"),
    ("用于清洗的试剂槽和载片", "Reagent cartridge and flow cell for washing"),
    ("准备仪器", "Preparing the device"),
    ("开机", "Powering the device on"),
    ("登录控制软件", "Logging in to the control software"),
    ("染色前自检", "Pre-run checks for staining"),
    ("进行预清洗", "Performing a pre-run wash"),
    ("工作流程", "Workflow"),
    ("样本预处理", "Performing sample pretreatment"),
    ("准备&装载试剂槽", "Preparing and loading the reagent cartridge"),
    ("准备&装载载片", "Preparing and loading the flow cell"),
    ("进行载片自检", "Performing a flow cell self-check"),
    ("设置染色参数", "Setting staining parameters"),
    ("回顾参数", "Reviewing parameters"),
    ("进行染色", "Performing staining"),
    ("进行洗脱", "Performing elution"),
    ("清洗", "Performing a wash"),
    ("处理染色试剂槽和载片", "Disposing of the reagent cartridge and flow cell"),
    ("可选关机", "Powering the device off"),
    ("关机", "Powering the device off"),
    ("染色数据", "Staining data"),
    ("染色结果文件", "Staining result files"),
    ("导出数据", "Exporting Data"),
    ("服务计划", "Service plan"),
    ("日维护", "Daily maintenance"),
    ("清洗类型介绍", "Wash type introduction"),
    ("清洗前准备", "Preparing for a wash"),
    ("进行清洗", "Performing a wash"),
    ("重复使用清洗试剂槽", "Reusing cleaning cartridges"),
    ("周维护", "Weekly maintenance"),
    ("清理磁盘历史数据", "Clearing the historical data in the disk"),
    ("重启设备", "Restarting the device"),
    ("检查线缆", "Checking the power cord"),
    ("清洁载片平台", "Cleaning the flow cell stage"),
    ("废液桶维护", "Maintaining the waste container"),
    ("月维护", "Monthly maintenance"),
    ("清洁仪器", "Cleaning the device"),
    ("检查并清理散热风扇", "Checking and cleaning the cooling fan"),
    ("年保养", "Annual maintenance"),
    ("软件维护", "Maintaining the software"),
    ("故障处理", "Troubleshooting"),
    ("储存与运输", "Transportation and storage"),
    ("仪器处理", "Disposal of the device"),
    ("网络安全说明与指导", "Network safety instructions and guidance"),
    ("用户访问控制机制", "Access control"),
    ("数据接口", "Data port"),
    ("网络安全特征配置", "Network security feature configuration"),
    ("数据备份与灾难恢复", "Data backup and disaster recovery"),
    ("运行环境要求", "Operating environment requirements"),
    ("安全软件信息", "Security software information"),
    ("外部环境与安全软件更新要求", "External environment and security software update requirements"),
    ("符合标准清单", "Compliance information"),
    ("仅供科研使用", "Research use only"),
    ("制造商信息", "Manufacturer information"),
    ("欧洲代表信息", "European representative information"),
)
_CN_TO_EN_KEYS = {}
_EN_TO_CN_KEYS = {}
for _cn_title, _en_title in SECTION_TITLE_PAIRS:
    _cn_key = _title_key(_cn_title)
    _en_key = _title_key(_en_title)
    _CN_TO_EN_KEYS.setdefault(_cn_key, set()).add(_en_key)
    _EN_TO_CN_KEYS.setdefault(_en_key, set()).add(_cn_key)


def _is_junk_toc_title(title: str) -> bool:
    text = _normalize_line(title)
    if not text:
        return True
    folded = text.casefold()
    if folded in {"user manual", "i", "ii", "iii", "iv"}:
        return True
    if re.fullmatch(r"[\d\s]+", text):
        return True
    if re.search(r"\d+\s+\d+\s+\d+", text):
        return True
    if re.match(r"^(?:figure|table|fig\.?|图|表)\s*\d+", folded):
        return True
    if len(re.findall(r"[A-Za-z\u4e00-\u9fff]", text)) < 2:
        return True
    if "appapeil" in folded or "classe" in folded:
        return True
    if folded.startswith("cleaning cartridge"):
        return True
    return False


def extract_toc_titles(text: str) -> list[str]:
    lines = [_normalize_line(line) for line in re.split(r"\r?\n+", str(text or ""))]
    limit = max(80, int(len(lines) * 0.18))
    titles = []
    max_page = 0
    for line in lines[:limit]:
        match = _TOC_LINE_RE.match(line)
        if not match:
            continue
        title = match.group(1).strip()
        if _is_junk_toc_title(title):
            continue
        try:
            page = int(match.group(2))
        except ValueError:
            continue
        if max_page >= 20 and page <= 5 and page < max_page - 20:
            break
        max_page = max(max_page, page)
        if titles and titles[-1] == title:
            continue
        titles.append(title)
    return titles


def _sections_from_titles(text: str, titles: list[str]) -> list[dict]:
    lines = [_normalize_line(line) for line in re.split(r"\r?\n+", str(text or ""))]
    start_after = max(0, int(len(lines) * 0.1))
    positions = []
    for title in titles:
        hits = [index for index, line in enumerate(lines) if line == title]
        body_hits = [index for index in hits if index >= start_after]
        positions.append(body_hits[0] if body_hits else (hits[-1] if hits else None))
    sections = []
    for index, title in enumerate(titles):
        start = positions[index]
        if start is None:
            sections.append({"title": title, "number": title, "body_text": ""})
            continue
        end = len(lines)
        for later in positions[index + 1:]:
            if later is not None and later > start:
                end = later
                break
        body = " ".join(line for line in lines[start + 1:end] if line)[:1200]
        sections.append({"title": title, "number": title, "body_text": body})
    return sections


def extract_manual_sections(text: str) -> list[dict]:
    titles = extract_toc_titles(text)
    if len(titles) >= 5:
        return _sections_from_titles(text, titles)
    headings = extract_headings(text)
    return [
        {
            "title": heading["title"],
            "number": heading["number"],
            "body_text": heading.get("body_text") or "",
        }
        for heading in headings
    ]


def _titles_match(title_a: str, title_b: str) -> bool:
    key_a = _title_key(title_a)
    key_b = _title_key(title_b)
    if not key_a or not key_b:
        return False
    if key_a == key_b:
        return True
    en_keys = _CN_TO_EN_KEYS.get(key_a) or _EN_TO_CN_KEYS.get(key_a) or set()
    cn_keys = _EN_TO_CN_KEYS.get(key_b) or _CN_TO_EN_KEYS.get(key_b) or set()
    if key_b in en_keys or key_a in cn_keys:
        return True
    if any(item and len(item) >= 8 and (item in key_b or key_b in item) for item in en_keys):
        return True
    if any(item and len(item) >= 8 and (item in key_a or key_a in item) for item in cn_keys):
        return True
    return False


def align_section_titles(main_titles: list[str], peer_titles: list[str]) -> list[dict]:
    used = set()
    cursor = 0
    aligned = []
    for title in main_titles:
        found = None
        window_end = min(len(peer_titles), cursor + 10)
        for index in range(cursor, window_end):
            if index in used:
                continue
            if _titles_match(title, peer_titles[index]) or _titles_match(peer_titles[index], title):
                found = index
                break
        if found is None:
            aligned.append({"main": title, "peer": None})
            continue
        aligned.append({"main": title, "peer": peer_titles[found]})
        used.add(found)
        cursor = found + 1
    for index, title in enumerate(peer_titles):
        if index in used:
            continue
        aligned.append({"main": None, "peer": title})
    return aligned


def _normalize_token(token: str) -> str:
    value = re.sub(r"\s+", "", str(token or "")).casefold()
    value = value.replace("℃", "°c").replace("℉", "°f").replace("％", "%")
    value = value.replace("μl", "ul").replace("µl", "ul")
    return value


def extract_fact_tokens(text: str) -> set[str]:
    content = str(text or "")
    tokens = set()
    for regex in (_CATALOG_RE, _UNIT_VALUE_RE, _VERSION_RE):
        for match in regex.finditer(content):
            token = _normalize_token(match.group(0))
            if not token or _YEAR_RE.match(token) or _is_noise_token(token):
                continue
            tokens.add(token)
    return tokens


def _is_noise_token(token: str) -> bool:
    value = str(token or "")
    if _DOC_NO_RE.match(value):
        return True
    if _DURATION_TOKEN_RE.match(value):
        return True
    if _POSTAL_TOKEN_RE.match(value) or _PHONE_TOKEN_RE.match(value):
        return True
    if value.endswith("°f"):
        return True
    return False


def _token_priority(token: str) -> str:
    if re.search(r"[a-z]", token) and re.search(r"\d", token):
        return "P0"
    return "P1"


def bilingual_values_match(value_a: str, value_b: str) -> bool:
    left = _normalize_line(value_a)
    right = _normalize_line(value_b)
    if not left or not right:
        return False
    if left.casefold() == right.casefold():
        return True
    compact_left = _normalize_token(left)
    compact_right = _normalize_token(right)
    if compact_left and compact_left == compact_right:
        return True
    left_tokens = extract_fact_tokens(left)
    right_tokens = extract_fact_tokens(right)
    if left_tokens and left_tokens == right_tokens:
        return True
    shared = left_tokens & right_tokens
    if shared and any(_token_priority(token) == "P0" for token in shared):
        return True
    return False


def bilingual_value_status(value_a: str, value_b: str) -> str:
    left = _normalize_line(value_a)
    right = _normalize_line(value_b)
    if not left or not right:
        return "missing"
    if bilingual_values_match(left, right):
        return "match"
    if _CONTACT_RE.search(left) or _CONTACT_RE.search(right):
        return "mismatch"
    left_tokens = extract_fact_tokens(left)
    right_tokens = extract_fact_tokens(right)
    if left_tokens or right_tokens:
        return "mismatch" if left_tokens != right_tokens else "match"
    left_has_cjk = bool(re.search(r"[\u4e00-\u9fff]", left))
    right_has_cjk = bool(re.search(r"[\u4e00-\u9fff]", right))
    if left_has_cjk != right_has_cjk:
        return "translation"
    return "mismatch"


def _is_en_flow_heading(line: str) -> bool:
    text = _normalize_line(line).casefold()
    if len(text) > 48:
        return False
    if re.fullmatch(r"(?:operating procedure|experimental procedure|operating instructions|workflow|precautions|notes and precautions)\s+\d{1,3}", text):
        return False
    text = re.sub(r"\s+\d{1,3}$", "", text).strip(" :-")
    return any(text == keyword or text.startswith(keyword + " ") for keyword in EN_FLOW_HEADINGS)


def _is_cn_flow_heading(line: str) -> bool:
    text = _normalize_line(line)
    if len(text) > 24:
        return False
    if re.fullmatch(r"(?:操作流程|实验步骤|操作步骤|注意事项|工作流程)\s+\d{1,3}", text):
        return False
    text = re.sub(r"\s+\d{1,3}$", "", text).strip(" ：:、-")
    return any(text == keyword or text.startswith(keyword) for keyword in CN_FLOW_KEYWORDS)


def extract_flow_profile(text: str) -> dict:
    lines = [_normalize_line(line) for line in re.split(r"\r?\n+", str(text or "")) if line.strip()]
    sections = []
    active = None
    for line in lines:
        if _is_cn_flow_heading(line) or _is_en_flow_heading(line):
            active = {"heading": line, "lines": []}
            sections.append(active)
            continue
        if active is None:
            continue
        if _parse_heading(line) and not _STEP_RE.match(line):
            active = None
            continue
        active["lines"].append(line)

    steps = []
    for section in sections:
        for line in section["lines"]:
            if not _STEP_RE.match(line):
                continue
            step_text = _STEP_RE.sub("", line).strip(" ：:;；,.，。")
            if not step_text:
                continue
            steps.append({"text": step_text[:80], "section": section["heading"]})
    return {"sections": sections, "steps": steps}


def summarize_flow_profile(profile: dict) -> str:
    headings = [section.get("heading") for section in profile.get("sections") or [] if section.get("heading")]
    heading_text = "、".join(headings[:3]) if headings else "未识别到指定流程章节"
    return f"{heading_text}；识别到 {len(profile.get('steps') or [])} 个主干步骤"


def _row(dimension, name, main_value, reference_items, conclusion, level, kind="bilingual"):
    return {
        "dimension": dimension,
        "parameter_name": name,
        "main_value": main_value or "-",
        "reference_values": reference_items,
        "reference_summary": "；".join(item.get("value") or "-" for item in reference_items) or "-",
        "reference_detail": "；".join(
            f"{item.get('filename') or '参考文件'}：{item.get('value') or '-'}"
            for item in reference_items
        ) or "-",
        "reference_value": "；".join(item.get("value") or "-" for item in reference_items) or "-",
        "conclusion": conclusion,
        "level": level,
        "kind": kind,
    }


def _reference_items(docs: list[dict], values: list[str]) -> list[dict]:
    items = []
    for doc, value in zip(docs, values):
        items.append({
            "filename": str(doc.get("filename") or "参考文件").strip() or "参考文件",
            "value": value or "-",
        })
    return items


def _heading_sort_key(value: str):
    parts = []
    for part in re.split(r"(\d+)", str(value or "")):
        if not part:
            continue
        parts.append(int(part) if part.isdigit() else part)
    return parts


def _section_snippet(text: str, limit: int = 180) -> str:
    value = _normalize_line(text)
    if not value:
        return "-"
    return value[:limit] + ("..." if len(value) > limit else "")


def _summarize_titles(titles: list[str], limit: int = 6) -> str:
    names = [title for title in titles if title]
    if not names:
        return "-"
    extra = f" 等{len(names)}项" if len(names) > limit else ""
    return "、".join(names[:limit]) + extra


def _named_section_rows(main_doc: dict, peer_docs: list[dict]) -> list[dict] | None:
    main_sections = extract_manual_sections(main_doc.get("text") or "")
    peer_doc = peer_docs[0] if peer_docs else None
    if not peer_doc:
        return None
    peer_sections = extract_manual_sections(peer_doc.get("text") or "")
    if len(main_sections) < 5 or len(peer_sections) < 5:
        return None
    if not any(item.get("title") for item in main_sections) or not any(item.get("title") for item in peer_sections):
        return None

    main_map = {item["title"]: item for item in main_sections}
    peer_map = {item["title"]: item for item in peer_sections}
    pairs = align_section_titles(
        [item["title"] for item in main_sections],
        [item["title"] for item in peer_sections],
    )
    rows = []
    main_label = language_label(detect_doc_language(main_doc.get("text") or ""))
    peer_label = language_label(detect_doc_language(peer_doc.get("text") or ""))
    missing_peer = [item["main"] for item in pairs if item.get("main") and not item.get("peer")]
    missing_main = [item["peer"] for item in pairs if item.get("peer") and not item.get("main")]
    matched = [item for item in pairs if item.get("main") and item.get("peer")]
    matched_main = {item["main"] for item in matched}
    matched_peer = {item["peer"] for item in matched}
    missing_peer = [title for title in missing_peer if title not in matched_main]
    missing_main = [title for title in missing_main if title not in matched_peer]

    if missing_peer:
        rows.append(_row(
            "中英对照",
            f"目录章节缺失（{peer_label}）",
            _summarize_titles(missing_peer),
            _reference_items([peer_doc], ["缺失"]),
            f"{peer_label}目录未找到与这些{main_label}章节对应的标题，请核对是否漏译或目录层级不同。",
            "P1",
        ))
    if missing_main:
        rows.append(_row(
            "中英对照",
            f"目录章节缺失（{main_label}）",
            "缺失",
            _reference_items([peer_doc], [_summarize_titles(missing_main)]),
            f"{main_label}目录未找到与这些{peer_label}章节对应的标题，请核对是否漏译或目录层级不同。",
            "P1",
        ))

    token_rows = []
    main_global = extract_fact_tokens(main_doc.get("text") or "")
    peer_global = extract_fact_tokens(peer_doc.get("text") or "")
    for item in matched:
        main_section = main_map.get(item["main"]) or {}
        peer_section = peer_map.get(item["peer"]) or {}
        name = f"{item['main']} / {item['peer']}"
        main_tokens = extract_fact_tokens(f"{item['main']} {main_section.get('body_text') or ''}")
        peer_tokens = extract_fact_tokens(f"{item['peer']} {peer_section.get('body_text') or ''}")
        missing_in_peer = sorted(token for token in main_tokens if token not in peer_global)
        missing_in_main = sorted(token for token in peer_tokens if token not in main_global)
        if not missing_in_peer and not missing_in_main:
            continue
        p0_missing = [token for token in missing_in_peer + missing_in_main if _token_priority(token) == "P0"]
        parts = []
        if missing_in_peer:
            parts.append("参考文件全文缺少 " + "、".join(missing_in_peer[:5]))
        if missing_in_main:
            parts.append("主文档全文缺少 " + "、".join(missing_in_main[:5]))
        token_rows.append(_row(
            "中英对照",
            name,
            _section_snippet(main_section.get("body_text") or item["main"]),
            _reference_items([peer_doc], [_section_snippet(peer_section.get("body_text") or item["peer"])]),
            "；".join(parts) + "。请核对货号、规格或数值是否漏译或写错。",
            "P0" if p0_missing else "P1",
        ))
        if len(token_rows) >= 15:
            break
    rows.extend(token_rows)

    if matched and not token_rows:
        sample = matched[:8]
        rows.append(_row(
            "中英对照",
            "已对齐目录章节",
            _summarize_titles([item["main"] for item in sample], 8),
            _reference_items([peer_doc], [_summarize_titles([item["peer"] for item in sample], 8)]),
            f"已按目录对齐 {len(matched)} 个章节，关键数值未发现差异。",
            "一致",
        ))
    elif matched:
        rows.append(_row(
            "中英对照",
            "已对齐目录章节",
            f"识别到 {len(main_sections)} 个目录章节",
            _reference_items([peer_doc], [f"识别到 {len(peer_sections)} 个目录章节"]),
            f"已按目录对齐 {len(matched)} 个章节。",
            "一致",
        ))
    return rows


def _align_heading_rows(main_doc: dict, peer_docs: list[dict]) -> list[dict]:
    main_headings = extract_headings(main_doc.get("text") or "")
    peer_heading_sets = [extract_headings(doc.get("text") or "") for doc in peer_docs]
    if not main_headings and not any(peer_heading_sets):
        return []

    rows = []
    main_map = {item["number"]: item for item in main_headings}
    peer_maps = [{item["number"]: item for item in headings} for headings in peer_heading_sets]
    numbers = sorted(set(main_map) | set().union(*[set(item) for item in peer_maps]), key=_heading_sort_key)

    for number in numbers:
        main_item = main_map.get(number)
        peer_titles = []
        for peer_map in peer_maps:
            peer_item = peer_map.get(number)
            peer_titles.append(peer_item["title"] if peer_item else "缺失")
        if main_item and all(number in peer_map for peer_map in peer_maps):
            continue
        if not main_item:
            conclusion = f"主文档缺少章节 {number}，参考文件有对应标题。"
        else:
            conclusion = f"参考文件缺少章节 {number}，主文档标题为“{main_item['title']}”。"
        rows.append(_row(
            "中英对照",
            f"章节 {number}",
            main_item["title"] if main_item else "-",
            _reference_items(peer_docs, peer_titles),
            conclusion,
            "P1",
        ))

    if rows:
        return rows[:12]
    return [_row(
        "中英对照",
        "章节结构",
        f"识别到 {len(main_headings)} 个编号章节",
        _reference_items(peer_docs, [f"识别到 {len(headings)} 个编号章节" for headings in peer_heading_sets]),
        "中英文编号章节可以按序号对齐。",
        "一致",
    )]


def _compare_token_texts(name, main_text, peer_docs, peer_texts):
    main_tokens = extract_fact_tokens(main_text)
    peer_token_sets = [extract_fact_tokens(text) for text in peer_texts]
    if name == "全文关键数值":
        main_tokens = {token for token in main_tokens if _token_priority(token) == "P0"}
        peer_token_sets = [{token for token in tokens if _token_priority(token) == "P0"} for tokens in peer_token_sets]
    missing_in_peer = []
    missing_in_main = []
    for token in sorted(main_tokens):
        if any(token not in tokens for tokens in peer_token_sets):
            missing_in_peer.append(token)
    union_peer = set().union(*peer_token_sets) if peer_token_sets else set()
    for token in sorted(union_peer):
        if token not in main_tokens:
            missing_in_main.append(token)
    if not missing_in_peer and not missing_in_main:
        return None
    p0_missing = [token for token in missing_in_peer + missing_in_main if _token_priority(token) == "P0"]
    parts = []
    if missing_in_peer:
        parts.append("参考文件缺少 " + "、".join(missing_in_peer[:5]))
    if missing_in_main:
        parts.append("主文档缺少 " + "、".join(missing_in_main[:5]))
    return _row(
        "中英对照",
        name,
        "、".join(sorted(main_tokens)[:8]) or "-",
        _reference_items(peer_docs, ["、".join(sorted(tokens)[:8]) or "-" for tokens in peer_token_sets]),
        "；".join(parts) + "。请核对货号、规格或数值是否漏译或写错。",
        "P0" if p0_missing else "P1",
    )


def _fact_token_rows(main_doc: dict, peer_docs: list[dict]) -> list[dict]:
    main_headings = extract_headings(main_doc.get("text") or "")
    peer_heading_sets = [extract_headings(doc.get("text") or "") for doc in peer_docs]
    rows = []
    main_map = {item["number"]: item for item in main_headings}
    peer_maps = [{item["number"]: item for item in headings} for headings in peer_heading_sets]
    for number, main_item in main_map.items():
        if not all(number in peer_map for peer_map in peer_maps):
            continue
        peer_texts = []
        for peer_map in peer_maps:
            peer_item = peer_map[number]
            peer_texts.append(f"{peer_item['title']} {peer_item.get('body_text') or ''}")
        row = _compare_token_texts(
            f"章节 {number} 数值",
            f"{main_item['title']} {main_item.get('body_text') or ''}",
            peer_docs,
            peer_texts,
        )
        if row:
            rows.append(row)
        if len(rows) >= 10:
            break

    if rows:
        return rows
    row = _compare_token_texts(
        "全文关键数值",
        main_doc.get("text") or "",
        peer_docs,
        [doc.get("text") or "" for doc in peer_docs],
    )
    if row:
        return [row]
    return [_row(
        "中英对照",
        "全文关键数值",
        "、".join(sorted(extract_fact_tokens(main_doc.get("text") or ""))[:8]) or "-",
        _reference_items(
            peer_docs,
            ["、".join(sorted(extract_fact_tokens(doc.get("text") or ""))[:8]) or "-" for doc in peer_docs],
        ),
        "中英文关键货号、型号和带单位数值一致。",
        "一致",
    )]


def _flow_rows(main_doc: dict, peer_docs: list[dict]) -> list[dict]:
    main_profile = extract_flow_profile(main_doc.get("text") or "")
    peer_profiles = [extract_flow_profile(doc.get("text") or "") for doc in peer_docs]
    main_count = len(main_profile.get("steps") or [])
    peer_counts = [len(profile.get("steps") or []) for profile in peer_profiles]
    usable_counts = [count for count in peer_counts if count > 0]
    majority = usable_counts[0] if usable_counts else 0
    if usable_counts:
        majority = max(set(usable_counts), key=usable_counts.count)
    if main_count == 0 and not usable_counts:
        level, conclusion = "一致", "中英文均未识别到主干步骤，跳过步骤数对照。"
    elif main_count == 0 and majority > 0:
        level, conclusion = "P1", "主文档未识别到主干步骤，参考文件有可对照流程。"
    elif majority == 0 and main_count > 0:
        level, conclusion = "P1", "参考文件未识别到主干步骤，主文档有可对照流程。"
    elif majority > 0 and abs(main_count - majority) / majority > 0.3:
        level, conclusion = "P1", f"中英文主干步骤数不一致：主文档 {main_count}，参考文件 {majority}。"
    else:
        level, conclusion = "一致", "中英文主干步骤数整体一致。"
    return [_row(
        "中英对照",
        "主干步骤数",
        summarize_flow_profile(main_profile),
        _reference_items(peer_docs, [summarize_flow_profile(profile) for profile in peer_profiles]),
        conclusion,
        level,
        kind="flow",
    )]


def _parse_ai_issues(raw: str) -> list[dict]:
    text = str(raw or "").strip()
    if not text:
        return []
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", text, re.S)
        if not match:
            return []
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return []
    if isinstance(data, dict):
        data = data.get("issues") or data.get("items") or []
    if not isinstance(data, list):
        return []
    issues = []
    for item in data:
        if not isinstance(item, dict):
            continue
        conclusion = str(item.get("conclusion") or item.get("reason") or "").strip()
        if not conclusion:
            continue
        issues.append({
            "index": item.get("index"),
            "level": item.get("level") if item.get("level") in {"P0", "P1", "P2"} else "P1",
            "conclusion": conclusion[:200],
        })
    return issues


def semantic_alignment_rows(pairs: list[dict], chat_fn=None) -> list[dict]:
    if not pairs or chat_fn is None:
        return []
    capped = pairs[:6]
    sample = "\n".join(
        f"[{idx + 1}] 章节 {item.get('number')} | 中文: {(item.get('cn') or '')[:350]} | 英文: {(item.get('en') or '')[:350]}"
        for idx, item in enumerate(capped)
    )
    prompt = (
        "请作为中英技术文档对照审核员，只检查事实性不一致：货号/型号写错、数值不同、步骤缺失、含义相反。\n"
        "不要报告文体、语序、中英空格或可接受的译名差异。\n\n"
        f"对照片段:\n{sample}\n\n"
        '严格输出 JSON 数组，每项为 {"index": 编号, "level": "P0|P1|P2", "conclusion": "一句话"}。\n'
        "没有问题则输出 []。只输出 JSON。"
    )
    try:
        raw = chat_fn(
            [{"role": "user", "content": prompt}],
            max_tokens=1200,
            temperature=0.1,
            request_label="compare.bilingual.semantic",
        )
    except Exception:
        return []
    rows = []
    for issue in _parse_ai_issues(raw):
        try:
            index = int(issue.get("index") or 0) - 1
        except (TypeError, ValueError):
            continue
        if index < 0 or index >= len(capped):
            continue
        pair = capped[index]
        rows.append(_row(
            "中英对照",
            f"章节 {pair.get('number')} 语义",
            (pair.get("cn") or "-")[:180],
            [{"filename": pair.get("filename") or "参考文件", "value": (pair.get("en") or "-")[:180]}],
            issue["conclusion"],
            issue["level"],
        ))
    return rows


def _heading_semantic_pairs(main_doc: dict, peer_doc: dict) -> list[dict]:
    main_map = {item["number"]: item for item in extract_headings(main_doc.get("text") or "")}
    peer_map = {item["number"]: item for item in extract_headings(peer_doc.get("text") or "")}
    pairs = []
    for number, main_item in main_map.items():
        peer_item = peer_map.get(number)
        if not peer_item:
            continue
        cn_text = f"{main_item['title']} {main_item.get('body_text') or ''}".strip()
        en_text = f"{peer_item['title']} {peer_item.get('body_text') or ''}".strip()
        if len(cn_text) < 8 or len(en_text) < 8:
            continue
        pairs.append({
            "number": number,
            "cn": cn_text,
            "en": en_text,
            "filename": peer_doc.get("filename") or "参考文件",
        })
        if len(pairs) >= 6:
            break
    return pairs


def opposite_language_docs(main_doc: dict, reference_docs: list[dict]) -> list[dict]:
    main_lang = detect_doc_language(main_doc.get("text") or "")
    target = "en" if main_lang == "cn" else "cn" if main_lang == "en" else ""
    if not target:
        return [
            doc for doc in reference_docs
            if detect_doc_language(doc.get("text") or "") in {"cn", "en"}
        ]
    return [doc for doc in reference_docs if detect_doc_language(doc.get("text") or "") == target]


def build_bilingual_rows(main_doc: dict, reference_docs: list[dict], *, enable_ai: bool = False, chat_fn=None) -> list[dict]:
    peer_docs = opposite_language_docs(main_doc, reference_docs)
    if not peer_docs:
        return []
    rows = []
    named_rows = _named_section_rows(main_doc, peer_docs)
    if named_rows:
        rows.extend(named_rows)
    else:
        rows.extend(_align_heading_rows(main_doc, peer_docs))
        rows.extend(_fact_token_rows(main_doc, peer_docs))
    if enable_ai:
        resolver = chat_fn
        if resolver is None:
            try:
                from app.utils.ai_client import ai_client
                if ai_client.available_providers():
                    resolver = ai_client.chat
            except Exception:
                resolver = None
        if resolver is not None:
            rows.extend(semantic_alignment_rows(_heading_semantic_pairs(main_doc, peer_docs[0]), chat_fn=resolver))
    return rows
