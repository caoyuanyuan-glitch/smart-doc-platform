"""中英文配对审核：确定性抽取 + 双向对照。

设计口径（对齐知识库 R-E1/R-E2）：
- 只报「一侧检出、另一侧完全缺失」的客观事实，不做术语/型号「应该是什么」的推断。
- 每条差异必须双向举证（行号 + 原文片段）；缺一侧证据不出问题。
- 缺安全警示 → P0；缺步骤/参数/章节 → P1；编号/顺序/表述差异 → P2 待人工裁定。
- 产品配置差异无法由文本判定，一律降级 P2 并提示人工确认，不定性为错误。
"""

from __future__ import annotations

import re
from typing import Any

CJK_RE = re.compile(r"[\u4e00-\u9fff]")
LATIN_RE = re.compile(r"[A-Za-z]")

# 安全警示：要求行首或紧跟冒号，避免把「注意事项」章节标题误判为警示条目
# 中文警示常用破折号/逗号而非冒号（「警告—打开时…」「小心，烫伤…」）；
# 但「注意事项」这类章节标题不算警示条目，故要求标记后接分隔符或行尾。
CN_SAFETY_PATTERNS = {
    "WARNING": re.compile(r"^\s*(?:警告|危险|警示)(?=[\s,，:：—\-]|$)", re.MULTILINE),
    "CAUTION": re.compile(r"^\s*(?:注意|小心|当心)(?=[\s,，:：—\-]|$)", re.MULTILINE),
}
EN_SAFETY_PATTERNS = {
    "WARNING": re.compile(r"^\s*(?:WARNING|DANGER)\b", re.MULTILINE | re.IGNORECASE),
    "CAUTION": re.compile(r"^\s*(?:CAUTION|NOTICE|ATTENTION)\b", re.MULTILINE | re.IGNORECASE),
}
SAFETY_LABELS = {"WARNING": "警告/危险", "CAUTION": "注意/小心"}

# 数值+单位：只收带单位的 token，避免页码/版本号/章节号入列。
# lookbehind 用 ASCII 边界而非 \w：中文在 Unicode 下属于 \w，
# 用 \w 会把「准备0.05%」截成「05%」、「2.60 mL」截成「60mL」（真实文件实测误报）。
# 同时排除小数点，防止从 "0.05" 的第二位再起一个 token。
# 单位前后只允许同行空白 [ \t]，禁止 \s 跨行把「32 \n\n X」拼成「32×」（PDF 提取伪影）。
# 尾边界用 ASCII 而非 \w：中文「37 °C的 PBS」「20 分钟进行水化」中中文属 \w，用 \w 会漏抽。
_MEASURE_RE = re.compile(
    r"(?<![A-Za-z0-9.])(-?\d+(?:[.,]\d+)?)[ \t]*"
    r"(μL|µL|uL|微升|毫升|ml|mL|L|℃|°C|°F|min|minutes?|分钟|h|hrs?|小时|s|sec|秒|rpm|V|mA|A|W|kW|%|×|X)(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_UNIT_ALIASES = {
    "µl": "μl", "ul": "μl", "微升": "μl", "毫升": "ml", "ml": "ml", "l": "l",
    "℃": "℃", "°c": "℃", "°f": "°f",
    "min": "min", "minute": "min", "minutes": "min", "分钟": "min",
    "h": "h", "hr": "h", "hrs": "h", "小时": "h",
    "s": "s", "sec": "s", "秒": "s",
    "rpm": "rpm", "v": "v", "ma": "ma", "a": "a",
    "w": "w", "kw": "kw", "%": "%", "×": "×", "x": "×",
}

_CAPTION_RE = re.compile(
    r"(?:图|figure|fig\.?|表|table|tab\.?)\s*[-—]?\s*(\d+(?:\.\d+)*)",
    re.IGNORECASE,
)
_CAPTION_KIND_RE = re.compile(r"^(?:图|figure|fig\.?|表|table|tab\.?)", re.IGNORECASE)

# 章节标题必须「编号 + 标题文字占满整行」：
# 旧正则会把「15. 将载片浸泡于含0.5%…」和页码行当章节，真实文件实测产生垃圾编号。
_NUMBERED_HEADING_RE = re.compile(
    r"^\s*(\d+(?:\.\d+)+)\s+[\u4e00-\u9fffA-Za-z][^\n]{0,38}$|"
    r"^\s*(\d{1,2})\s*[、.．]?\s*[\u4e00-\u9fffA-Za-z]{2,20}\s*$",
    re.MULTILINE,
)
# 顶层章节优先用显式「第 N 章 / Chapter N」标记：中文手册常用该写法，
# 数字列表项（如「1 状态指示灯」）不是章节，抓进来会制造垃圾编号。
_EXPLICIT_CHAPTER_RE = re.compile(
    r"^\s*(?:第\s*(\d+)\s*章|Chapter\s+(\d+))\b",
    re.MULTILINE | re.IGNORECASE,
)
# 流程关键词按语义归类后再比对：中文「注意事项」与英文 Precautions 属同一类，
# 直接按字面集合比对会把「语言不同」误判成「章节缺失」。
FLOW_CATEGORY_TERMS = {
    "操作步骤/流程": ("操作步骤", "操作流程", "实验步骤", "procedure", "operation", "steps"),
    "注意事项": ("注意事项", "precautions", "caution"),
    "故障排除": ("故障排除", "故障处理", "故障排查", "troubleshoot"),
}


def detect_language(text: str) -> str:
    """按 CJK / 拉丁字符占比判定语言：zh / en / unknown。"""
    content = str(text or "")
    cjk = len(CJK_RE.findall(content))
    latin = len(LATIN_RE.findall(content))
    if cjk >= 4 and cjk / max(cjk + latin, 1) >= 0.20:
        return "zh"
    if latin >= 8 and cjk / max(cjk + latin, 1) < 0.10:
        return "en"
    return "unknown"


def _line_contexts(text: str, pattern: re.Pattern[str], limit: int = 5) -> list[dict[str, Any]]:
    """返回命中行号 + 原文片段，用于双向举证。"""
    lines = str(text or "").splitlines()
    hits: list[dict[str, Any]] = []
    for line_no, line in enumerate(lines, start=1):
        if pattern.search(line):
            hits.append({"line_no": line_no, "context": line.strip()[:200]})
            if len(hits) >= limit:
                break
    return hits


def extract_safety_items(text: str) -> dict[str, list[dict[str, Any]]]:
    """抽取中/英安全警示条目，按 WARNING / CAUTION 分类，带行号。"""
    content = str(text or "")
    result: dict[str, list[dict[str, Any]]] = {"WARNING": [], "CAUTION": []}
    for category, pattern in CN_SAFETY_PATTERNS.items():
        result[category].extend(_line_contexts(content, pattern))
    for category, pattern in EN_SAFETY_PATTERNS.items():
        result[category].extend(_line_contexts(content, pattern))
    return result


def _normalized_measure(number: str, unit: str) -> str:
    unit_key = _UNIT_ALIASES.get(unit.casefold(), unit.casefold())
    if unit_key == "×":
        return f"{number}×"
    return f"{number}{unit_key}"


def extract_measure_tokens(text: str) -> dict[str, list[dict[str, Any]]]:
    """抽取数值+单位 token，归一化码位/空格；返回 token -> 举证片段。"""
    content = str(text or "")
    tokens: dict[str, list[dict[str, Any]]] = {}
    for match in _MEASURE_RE.finditer(content):
        number = match.group(1).replace(",", "")
        token = _normalized_measure(number, match.group(2))
        line_no = content.count("\n", 0, match.start()) + 1
        start = content.rfind("\n", 0, match.start()) + 1
        end = content.find("\n", match.end())
        if end == -1:
            end = len(content)
        context = content[start:end].strip()[:200]
        evidence = {"line_no": line_no, "context": context}
        bucket = tokens.setdefault(token, [])
        if len(bucket) < 3 and evidence not in bucket:
            bucket.append(evidence)
    return tokens


def extract_caption_numbers(text: str) -> dict[str, set[str]]:
    """抽取图/表编号集合，中文「图 3」与英文「Figure 3」归一化到同一编号。"""
    content = str(text or "")
    result: dict[str, set[str]] = {"figure": set(), "table": set()}
    for match in _CAPTION_RE.finditer(content):
        head = match.group(0)[: match.group(0).find(match.group(1))]
        kind_match = _CAPTION_KIND_RE.match(head.strip())
        if not kind_match:
            continue
        kind = "figure" if kind_match.group(0).casefold().startswith(("图", "fig")) else "table"
        result[kind].add(match.group(1))
    return result


def extract_section_profile(text: str) -> dict[str, Any]:
    """抽取编号章节大纲与流程关键词覆盖，用于双语章节结构对照。"""
    content = str(text or "")
    headings = []
    for match in _NUMBERED_HEADING_RE.finditer(content):
        number = match.group(1) or match.group(2)
        if not number:
            continue
        line = match.group(0).strip()
        title = line[len(number):].strip(" 、.．\t")
        headings.append({"number": number, "title": title})
    explicit = {
        match.group(1) or match.group(2)
        for match in _EXPLICIT_CHAPTER_RE.finditer(content)
        if (match.group(1) or match.group(2))
    }
    # 仅在有显式「第 N 章 / Chapter N」标记时给出顶层编号。
    # 目录页「标题 + 页码」被 PDF 提取成孤立数字，各语言版抽取质量不一致，
    # 用它做章节比对会制造误报——宁可放弃该维度，也不报无法证明的差异。
    top_level = explicit
    lowered = content.casefold()
    categories = {
        category
        for category, terms in FLOW_CATEGORY_TERMS.items()
        if any(term.casefold() in lowered for term in terms)
    }
    return {"headings": headings, "top_level": top_level, "categories": categories}


def _format_hits(hits: list[dict[str, Any]]) -> str:
    return " | ".join(f"第{h['line_no']}行: {h['context']}" for h in hits if h.get("context")) or "-"


def _format_set(values: set[str] | list[str]) -> str:
    return "、".join(sorted(values)[:6]) or "-"


def _row(
    *,
    parameter_name: str,
    main_value: str,
    reference_values: list[dict[str, Any]],
    conclusion: str,
    level: str,
    kind: str,
    main_evidence: list[dict[str, Any]],
    reference_evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "dimension": "中英对照",
        "parameter_name": parameter_name,
        "main_value": main_value or "-",
        "reference_values": reference_values,
        "reference_summary": "；".join(item["value"] for item in reference_values) or "-",
        "reference_detail": _reference_detail(reference_values),
        "reference_value": "；".join(item["value"] for item in reference_values) or "-",
        "conclusion": conclusion,
        "level": level,
        "kind": kind,
        "main_evidence": main_evidence,
        "reference_evidence": reference_evidence,
        "evidence": f"主文档：{_format_hits(main_evidence)}\n参考文件：{_format_hits(reference_evidence)}",
    }


def _reference_detail(reference_values: list[dict[str, Any]]) -> str:
    parts = []
    for item in reference_values or []:
        filename = str(item.get("filename") or "参考文件").strip()
        value = str(item.get("value") or "-")
        parts.append(f"{filename}：{value}")
    return "；".join(parts) or "-"


def _first_evidence(evidence_map: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """取第一个有举证的值，保证双语条目双向可定位。"""
    for hits in evidence_map.values():
        if hits:
            return hits
    return []


def _safety_rows(main_doc: dict[str, Any], ref_doc: dict[str, Any]) -> list[dict[str, Any]]:
    main_items = extract_safety_items(main_doc.get("text") or "")
    ref_items = extract_safety_items(ref_doc.get("text") or "")
    ref_name = ref_doc.get("filename") or "参考文件"
    rows: list[dict[str, Any]] = []
    for category in ("WARNING", "CAUTION"):
        main_hits = main_items[category]
        ref_hits = ref_items[category]
        if bool(main_hits) == bool(ref_hits):
            continue
        if not main_hits:
            level = "P0" if category == "WARNING" else "P1"
            conclusion = f"主文档缺少{SAFETY_LABELS[category]}类警示，参考文档检出；请同步补充并核对中英两版。"
        else:
            level = "P0" if category == "WARNING" else "P1"
            conclusion = f"参考文档缺少{SAFETY_LABELS[category]}类警示，主文档检出；请同步补充并核对中英两版。"
        rows.append(_row(
            parameter_name=f"安全警示·{SAFETY_LABELS[category]}",
            main_value=f"检出 {len(main_hits)} 处" if main_hits else "未检出",
            reference_values=[{"filename": ref_name, "value": f"检出 {len(ref_hits)} 处" if ref_hits else "未检出"}],
            conclusion=conclusion,
            level=level,
            kind="bilingual_safety",
            main_evidence=main_hits,
            reference_evidence=ref_hits,
        ))
    return rows


def _measure_rows(main_doc: dict[str, Any], ref_doc: dict[str, Any]) -> list[dict[str, Any]]:
    main_tokens = extract_measure_tokens(main_doc.get("text") or "")
    ref_tokens = extract_measure_tokens(ref_doc.get("text") or "")
    ref_name = ref_doc.get("filename") or "参考文件"
    only_main = sorted(set(main_tokens) - set(ref_tokens))
    only_ref = sorted(set(ref_tokens) - set(main_tokens))
    if not only_main and not only_ref:
        return []
    main_value = f"独有：{_format_set(only_main)}" if only_main else "-"
    ref_value = f"独有：{_format_set(only_ref)}" if only_ref else "-"
    evidence_main = [hit for token in only_main for hit in main_tokens[token]][:5]
    evidence_ref = [hit for token in only_ref for hit in ref_tokens[token]][:5]
    main_part = f"主文档独有 {_format_set(only_main)}" if only_main else "主文档无独有 token"
    ref_part = f"参考文档独有 {_format_set(only_ref)}" if only_ref else "参考文档无独有 token"
    conclusion = (
        f"数值/单位 token 不对应：{main_part}；{ref_part}。"
        "请确认是否漏写或产品配置差异（需人工裁定）。"
    )
    return [_row(
        parameter_name="关键数值/单位",
        main_value=main_value,
        reference_values=[{"filename": ref_name, "value": ref_value}],
        conclusion=conclusion,
        level="P1",
        kind="bilingual_measure",
        main_evidence=evidence_main,
        reference_evidence=evidence_ref,
    )]


def _caption_rows(main_doc: dict[str, Any], ref_doc: dict[str, Any]) -> list[dict[str, Any]]:
    main_captions = extract_caption_numbers(main_doc.get("text") or "")
    ref_captions = extract_caption_numbers(ref_doc.get("text") or "")
    ref_name = ref_doc.get("filename") or "参考文件"
    rows: list[dict[str, Any]] = []
    for kind, label in (("figure", "图编号"), ("table", "表编号")):
        main_set, ref_set = main_captions[kind], ref_captions[kind]
        if not main_set and not ref_set:
            continue
        if main_set == ref_set:
            continue
        only_main = sorted(main_set - ref_set)
        only_ref = sorted(ref_set - main_set)
        if not only_main or not only_ref:
            continue  # 单侧多出：可能是版本页差，交人工，不自动定级
        rows.append(_row(
            parameter_name=label,
            main_value=f"主文档：{_format_set(main_set)}",
            reference_values=[{"filename": ref_name, "value": _format_set(ref_set)}],
            conclusion=f"{label}集合不一致（主文档独有 {_format_set(only_main)}；参考文档独有 {_format_set(only_ref)}），请人工核对是否章节增删。",
            level="P2",
            kind="bilingual_caption",
            main_evidence=[{"line_no": 0, "context": _format_set(main_set)}],
            reference_evidence=[{"line_no": 0, "context": _format_set(ref_set)}],
        ))
    return rows


def _section_rows(main_doc: dict[str, Any], ref_doc: dict[str, Any]) -> list[dict[str, Any]]:
    main_profile = extract_section_profile(main_doc.get("text") or "")
    ref_profile = extract_section_profile(ref_doc.get("text") or "")
    ref_name = ref_doc.get("filename") or "参考文件"
    main_top, ref_top = main_profile["top_level"], ref_profile["top_level"]
    rows: list[dict[str, Any]] = []
    # 章节编号体系在双语版本间本就可能不同；仅当两侧都抽出足够多的顶层编号且差异显著时提示，降级 P2 待裁定。
    if len(main_top) >= 3 and len(ref_top) >= 3:
        overlap = len(main_top & ref_top) / len(main_top | ref_top)
        if overlap < 0.5:
            rows.append(_row(
                parameter_name="章节结构",
                main_value=f"顶层编号：{_format_set(main_top)}",
                reference_values=[{"filename": ref_name, "value": _format_set(ref_top)}],
                conclusion="中英两版顶层章节编号重合度低于 50%，请确认是否漏章或版本差异。",
                level="P2",
                kind="bilingual_section",
                main_evidence=[{"line_no": 0, "context": _format_set(main_top)}],
                reference_evidence=[{"line_no": 0, "context": _format_set(ref_top)}],
            ))
    # 流程类别：中文「注意事项」与英文 Precautions 归一为同类后再比对
    main_categories = main_profile["categories"]
    ref_categories = ref_profile["categories"]
    missing_in_main = sorted(ref_categories - main_categories)
    missing_in_ref = sorted(main_categories - ref_categories)
    if missing_in_main or missing_in_ref:
        rows.append(_row(
            parameter_name="流程章节覆盖",
            main_value=f"类别：{_format_set(main_categories)}",
            reference_values=[{"filename": ref_name, "value": _format_set(ref_categories)}],
            conclusion=(
                f"流程章节覆盖不一致：主文档缺少 {_format_set(missing_in_main)}；参考文档缺少 {_format_set(missing_in_ref)}。"
            ),
            level="P1",
            kind="bilingual_section",
            main_evidence=[{"line_no": 0, "context": _format_set(main_categories)}],
            reference_evidence=[{"line_no": 0, "context": _format_set(ref_categories)}],
        ))
    return rows


def build_bilingual_rows(
    main_doc: dict[str, Any], reference_docs: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """构建中英配对审核 rows；未检出配对时返回一条「一致」提示，不产生问题。"""
    main_text = main_doc.get("text") or ""
    main_lang = detect_language(main_text)
    pair = next(
        (
            doc for doc in reference_docs or []
            if detect_language(doc.get("text") or "") in {"zh", "en"}
            and detect_language(doc.get("text") or "") != main_lang
        ),
        None,
    )
    if main_lang not in {"zh", "en"} or pair is None:
        return [_row(
            parameter_name="配对语言识别",
            main_value=f"主文档语言：{main_lang}",
            reference_values=[
                {"filename": doc.get("filename") or "参考文件", "value": detect_language(doc.get("text") or "")}
                for doc in reference_docs or []
            ],
            conclusion="未识别到中英配对（两侧语言相同或无法判定），双语对照未执行；建议改用「核心参数 + 主干流程」模式。",
            level="一致",
            kind="bilingual_pair",
            main_evidence=[],
            reference_evidence=[],
        )]

    rows: list[dict[str, Any]] = []
    for extractor in (_safety_rows, _measure_rows, _caption_rows, _section_rows):
        try:
            rows.extend(extractor(main_doc, pair))
        except Exception:
            # 单维抽取失败不影响其他维度；确定性规则不应让整次审核失败
            continue
    if not rows:
        rows.append(_row(
            parameter_name="双语整体对照",
            main_value="已抽取",
            reference_values=[{"filename": pair.get("filename") or "参考文件", "value": "已抽取"}],
            conclusion="中英两版在安全警示、数值单位、图表编号、章节结构四维度未检出客观差异； wording 级一致性仍需人工复核。",
            level="一致",
            kind="bilingual_pair",
            main_evidence=[],
            reference_evidence=[],
        ))
    return rows
