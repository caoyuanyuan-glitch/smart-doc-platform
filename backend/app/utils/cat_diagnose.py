"""CAT 候选分类映射（G1）与开放式 AI 诊断（G2）。

只给智能润色副本叠加字段和建议，不改正文。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from contextlib import contextmanager
from typing import Any, Optional


logger = logging.getLogger(__name__)

CATEGORIES = (
    "spelling",
    "grammar",
    "word",
    "term",
    "ambiguity",
    "redundancy",
    "syntax",
    "logic",
    "missing",
    "register",
    "audience",
    "risk",
    "other",
)

SEVERITIES = ("low", "medium", "high")

CATEGORY_LABELS = {
    "spelling": "拼写标点",
    "grammar": "语法",
    "word": "用词",
    "term": "术语",
    "ambiguity": "歧义",
    "redundancy": "冗余",
    "syntax": "句式",
    "logic": "逻辑",
    "missing": "缺失",
    "register": "语体",
    "audience": "受众",
    "risk": "风险",
    "other": "其他",
}

SEVERITY_RANK = {"high": 3, "medium": 2, "low": 1}

# 交接包真实 type → (category, severity)
_TYPE_MAP = {
    "term": ("term", "high"),
    "typo": ("spelling", "high"),
    "imperative": ("register", "low"),
    "format": ("spelling", "low"),
    "punctuation": ("spelling", "low"),
    "terminology_rule": ("term", "high"),
    "forbidden_words": ("word", "high"),
    "double_negative": ("logic", "medium"),
    "passive_voice": ("syntax", "low"),
    "pronoun_reference": ("ambiguity", "medium"),
    "sentence_length": ("syntax", "low"),
    "informal": ("register", "medium"),
    "preferred_sentences": ("syntax", "low"),
    "template": ("syntax", "low"),
    "ai": ("register", "medium"),
    "text": ("other", "low"),
    "image": ("other", "low"),
    "unsupported": ("other", "low"),
}

_RULE_NAME_MAP = {
    "术语替换": ("term", "high"),
    "错别字修正": ("spelling", "high"),
    "祈使句规范": ("register", "low"),
    "数字单位空格": ("spelling", "low"),
    "中英文空格": ("spelling", "low"),
    "标点规范": ("spelling", "low"),
}

_RULE_SOURCE_MAP = {
    "sentence_guide": ("syntax", "low"),
    "surface_rules": ("word", "medium"),
}

_DIAGNOSE_PROMPT = """你是{product}平台的仪器文档资深编辑。请逐句审查用户文本，找出句式库之外的
语义问题：术语不规范、歧义、风险弱化、语体不符、逻辑缺失等。

规则（必须遵守）：
1. 只报告确定的问题。拿不准的不要报，宁缺毋滥。
2. 没有问题的句子，不要出现在结果里。
3. 修改必须忠于原意，不得增删事实与参数。
4. 术语必须与给定术语表一致；术语表没有的，保留原文。
5. category 只能从枚举取；severity 按以下标准判定：
   - high：客观事实错误、参数/数值错误、安全风险弱化、逻辑矛盾
   - medium：术语不规范、歧义、语体不符、缺失关键限定
   - low：风格优化、可读性建议、轻微措辞问题
   术语同义替换、风格统一类问题不得报 high。
6. 只输出 JSON，不要任何解释文字。
7. 若该问题可沉淀为可复用规则，设置 ruleable=true，并给出 rule_hint（匹配模式或替换说明）；否则 ruleable=false、rule_hint 为空。
8. problem 只写一句结论，不超过 24 字，只描述原文句子本身的问题（如"术语与术语表不一致""逻辑顺序颠倒"），不要引用任何外部依据，不要出现"版本记录""产品信息""章节""图示""表格""标准""规范"等来源字样。
9. 禁止引用任何外部来源。你只能看到待审查句子、术语表和风格指南，看不到文档章节结构、版本记录、产品信息或文档主题。problem 不得以任何形式提及或暗示外部来源；判断依据只能来自句子本身、术语表或风格指南。

category 枚举：spelling, grammar, word, term, ambiguity, redundancy, syntax, logic, missing, register, audience, risk, other

【术语表】
{terminology_md}

【风格指南】
{sentence_guide}

【待审查句子】
{json_sentences}

输出格式：
{{"diagnoses":[{{"sentence_index":0,"quote":"...","category":"term","severity":"high","problem":"...","revised":"...","ruleable":false,"rule_hint":""}}]}}
无问题返回 {{"diagnoses":[]}}。
"""




_REWRITE_PROMPT = """你是文本润色助手。你只负责改写，不解释理由。

【输入】待润色的原句。
【任务】原句存在语病、错别字、逻辑不通、表述不当等明显问题时，输出修订版；
        没有明显问题时，原样输出原句。
【规则】
1. 你没有任何本句之外的信息：无上下文、无章节、无图示、无版本记录、
   无术语表、无文档主题。
2. 禁止因为任何句外信息（包括你以为的"文档其他地方应该怎样"）改动本句。
3. 只改有问题的部分，保持原句语义与术语不变。
4. 不要解释修改原因。
【输出】只输出修订后的句子文本，不要任何附加内容。

【待改写句子】
{json_sentences}

批量时只输出 JSON：{{"revisions":[{{"sentence_index":0,"revised":"..."}}]}}
无改动的句子可省略或 revised 填原文。
"""

_VALIDATE_PROMPT = """你是审校评审。你的任务：严格检验一份修订是否成立，并解释其动机。

【输入】原句 + 修订版。
【任务】二选一：
- 修订版相对原句有实质改进 → 输出问题描述（原句的缺陷，即修订的原因），
  并给出严重程度。
- 修订版与原句无实质差异，或修订版引入了新问题（改变语义、改错术语等）→
  输出"无需修改"。

【问题描述要求】
1. 一句话，不超过24字。
2. 只能描述原句本身的缺陷，措辞只能引用原句中的词。
3. 严禁提及任何本句之外的内容。以下字样及同义表达一律禁止：
   版本/版本记录/修订、图示/图X、上下文/上文/前文、章节/X.Y节、
   文档主题/主题、术语表、表格/表X、标准、如图/见表/见图/参引。
4. 你只能看到原句和修订版这两个文本；除此之外不存在任何文档内容。

【严重程度标准】
high = 客观错误（错别字、数值错误、语义颠倒、逻辑硬伤）
medium = 术语不规范、指代歧义、表述不清
low = 语体风格、标点、冗余

【倾向】默认接受修订，除非修订明显更差。
【输出】"问题描述 | 严重程度"，或"无需修改"。

【原句与修订】
{json_pairs}

批量时只输出 JSON：{{"results":[{{"sentence_index":0,"output":"问题描述 | 严重程度"}}]}}
无需修改时 output 为"无需修改"。
"""

_SEVERITY_ALIASES = {
    "high": "high",
    "medium": "medium",
    "low": "low",
    "高": "high",
    "中": "medium",
    "低": "low",
}


def lab_ai_provider_name() -> str:
    return str(os.getenv("POLISH_LAB_AI_PROVIDER", "deepseek") or "deepseek").strip().lower() or "deepseek"


@contextmanager
def use_lab_ai_provider():
    """润色副本调用期间优先使用 DeepSeek，结束后恢复原默认供应商。"""
    from app.utils.ai_client import ai_client

    provider = lab_ai_provider_name()
    old = getattr(ai_client, "default_provider", None)
    ai_client.default_provider = provider
    try:
        yield ai_client
    finally:
        ai_client.default_provider = old


def lab_ai_chat(messages, max_tokens=2048, temperature=0.3, request_label=None, timeout=None):
    """润色副本专用聊天：优先 DeepSeek，失败再走原 failover。"""
    from app.utils.ai_client import ai_client

    provider = lab_ai_provider_name()
    result = None
    try:
        result = ai_client.chat_with_provider(
            provider,
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
            request_label=request_label,
        )
    except Exception as exc:
        logger.warning("[CAT_DIAGNOSE] %s 调用失败，回退默认链路: %s", provider, exc)
        result = None
    if result:
        return result
    return ai_client.chat(
        messages,
        max_tokens=max_tokens,
        temperature=temperature,
        request_label=request_label,
        timeout=timeout,
    )


def _truthy_env(name: str, default: str = "false") -> bool:
    return str(os.getenv(name, default) or "").strip().lower() in {"1", "true", "yes", "on"}


def is_ai_diagnose_enabled() -> bool:
    return _truthy_env("AI_DIAGNOSE_ENABLED", "true")


def diagnose_timeout() -> float:
    try:
        return float(os.getenv("AI_DIAGNOSE_TIMEOUT", "20") or 20)
    except (TypeError, ValueError):
        return 20.0


def diagnose_batch_size() -> int:
    try:
        value = int(os.getenv("AI_DIAGNOSE_BATCH_SIZE", "15") or 15)
    except (TypeError, ValueError):
        value = 15
    return max(1, value)


_active_diagnose_mode: Optional[str] = None
_last_decoupled_stats: dict[str, int] = {
    "stage1_no_change": 0,
    "stage1_revised": 0,
    "stage2_rejected": 0,
    "produced": 0,
}


def diagnose_mode(explicit: Optional[str] = None) -> str:
    if explicit is not None:
        raw = str(explicit)
    elif _active_diagnose_mode:
        raw = str(_active_diagnose_mode)
    else:
        raw = str(os.getenv("AI_DIAGNOSE_MODE", "decoupled") or "decoupled")
    value = raw.strip().lower()
    return "single" if value == "single" else "decoupled"


def last_decoupled_stats() -> dict[str, int]:
    return dict(_last_decoupled_stats)


def _reset_decoupled_stats() -> None:
    for key in _last_decoupled_stats:
        _last_decoupled_stats[key] = 0


def _add_decoupled_stats(**counts: int) -> None:
    for key, value in counts.items():
        _last_decoupled_stats[key] = int(_last_decoupled_stats.get(key) or 0) + int(value or 0)


def diagnose_guide_max_chars() -> int:
    try:
        value = int(os.getenv("AI_DIAGNOSE_GUIDE_CHARS", "2400") or 2400)
    except (TypeError, ValueError):
        value = 2400
    return max(200, value)


def _clip_text(text: str, max_chars: int) -> str:
    raw = str(text or "").strip()
    if len(raw) <= max_chars:
        return raw
    return raw[: max_chars - 1] + "..."


def _is_identity_revision(quote: Any, revised: Any, original: Any = "") -> bool:
    rev = _norm_text(revised)
    if not rev:
        return True
    if rev == _norm_text(quote):
        return True
    original_norm = _norm_text(original)
    return bool(original_norm) and rev == original_norm


def _parse_ruleable(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


HINT_ONLY_CATEGORIES = frozenset({"logic", "missing", "ambiguity"})


def hint_import_requires_replacement(category: Any, revised: Any) -> bool:
    return str(category or "") in HINT_ONLY_CATEGORIES and not str(revised or "").strip()


def _log_diagnose_drop(
    stage: str,
    category: Any,
    quote: Any,
    revised: Any,
    reason: str = "",
    sentence_index: Any = None,
) -> None:
    logger.info(
        "[CAT_DIAGNOSE] drop stage=%s reason=%s category=%s quote=%s revised=%s sentence_index=%s",
        stage,
        str(reason or ""),
        str(category or ""),
        str(quote or ""),
        str(revised or ""),
        "" if sentence_index is None else sentence_index,
    )


def map_rule_to_category(
    issue: Any = None,
    rule_source: str = "",
    rule_name: str = "",
    match_detail: Optional[dict] = None,
    issue_type: str = "",
) -> tuple[str, str]:
    """本地规则命中 → (category, severity)。先 type，再 rule_name，再 rule_source，最后 other。"""
    payload: dict = {}
    if isinstance(issue, dict):
        payload.update(issue)
    if isinstance(match_detail, dict):
        payload.update(match_detail)

    type_val = str(issue_type or payload.get("type") or "").strip()
    name_val = str(rule_name or payload.get("rule_name") or "").strip()
    source_val = str(rule_source or payload.get("rule_source") or "").strip()

    if type_val in _TYPE_MAP:
        return _TYPE_MAP[type_val]
    if name_val in _RULE_NAME_MAP:
        return _RULE_NAME_MAP[name_val]
    if source_val in _RULE_SOURCE_MAP:
        return _RULE_SOURCE_MAP[source_val]
    return ("other", "low")


def annotate_cat_candidates(items: Optional[list]) -> list:
    """给现有 candidate 补 category，已有字段不覆盖。"""
    for item in items or []:
        if not isinstance(item, dict):
            continue
        for candidate in item.get("candidates") or []:
            if not isinstance(candidate, dict):
                continue
            mapped_category, _mapped_severity = map_rule_to_category(
                issue=candidate,
                rule_source=str(candidate.get("rule_source") or ""),
                rule_name=str(candidate.get("rule_name") or ""),
                match_detail=candidate,
                issue_type=str(candidate.get("type") or item.get("type") or ""),
            )
            if not candidate.get("category"):
                candidate["category"] = mapped_category
    return items or []


def _norm_text(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip()


def _format_terminology(terminology: Any) -> str:
    if not terminology:
        return "（无）"
    if isinstance(terminology, str):
        text = terminology.strip()
        return text or "（无）"
    if isinstance(terminology, dict):
        lines = []
        for key, value in terminology.items():
            key_text = str(key or "").strip()
            value_text = str(value or "").strip()
            if key_text and value_text:
                lines.append(f"- {key_text} → {value_text}")
        return "\n".join(lines) if lines else "（无）"
    return str(terminology)


def extract_json_object(text: str) -> Optional[dict]:
    raw = str(text or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(raw[start : end + 1])
    except Exception:
        return None
    return data if isinstance(data, dict) else None


_ICON_PLACEHOLDER_RE = re.compile(
    r"[\u4e00-\u9fa5][·~～\s]\s*(?:按钮|图标|键|符号|菜单|选项|控件)"
)


def _is_icon_placeholder_quote(quote: str) -> bool:
    return bool(_ICON_PLACEHOLDER_RE.search(quote or ""))


_DIAGNOSE_PROBLEM_MAX = 24
_DIAGNOSE_SENTENCE_SEPS = ("。", "！", "？", "!", "?")


def _first_diagnose_sentence(text: str) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    positions = [value.find(sep) for sep in _DIAGNOSE_SENTENCE_SEPS if value.find(sep) >= 0]
    if not positions:
        return value
    return value[: min(positions)].strip()


def compact_diagnose_text(text: str, max_chars: int) -> str:
    value = _first_diagnose_sentence(text)
    if not value or len(value) <= max_chars:
        return value
    chunks = re.split(r"(?<=[，、；;：:])", value)
    assembled = ""
    for chunk in chunks:
        piece = str(chunk or "").strip()
        if not piece:
            continue
        nxt = f"{assembled}{piece}"
        if assembled and len(nxt) > max_chars:
            break
        assembled = nxt
        if len(assembled) >= max_chars:
            break
    clipped = (assembled or value)[:max_chars]
    return clipped.rstrip("，、；;：: ")


def _normalize_diagnosis(raw: Any, allowed_indexes: Optional[set] = None) -> Optional[dict]:
    if not isinstance(raw, dict):
        _log_diagnose_drop("normalize", "", "", "", reason="bad_shape")
        return None
    try:
        sentence_index = int(raw.get("sentence_index"))
    except (TypeError, ValueError):
        _log_diagnose_drop(
            "normalize",
            raw.get("category"),
            raw.get("quote"),
            raw.get("revised"),
            reason="bad_index",
        )
        return None
    if allowed_indexes is not None and sentence_index not in allowed_indexes:
        _log_diagnose_drop(
            "normalize",
            raw.get("category"),
            raw.get("quote"),
            raw.get("revised"),
            reason="index_not_allowed",
            sentence_index=sentence_index,
        )
        return None
    category = str(raw.get("category") or "").strip()
    severity = str(raw.get("severity") or "").strip()
    if category not in CATEGORIES or severity not in SEVERITIES:
        _log_diagnose_drop(
            "normalize",
            category,
            raw.get("quote"),
            raw.get("revised"),
            reason="bad_category",
            sentence_index=sentence_index,
        )
        return None
    quote = str(raw.get("quote") or "").strip()
    revised = str(raw.get("revised") or "").strip()
    problem = str(raw.get("problem") or "").strip()
    if category == "missing" and _is_icon_placeholder_quote(quote):
        _log_diagnose_drop(
            "normalize",
            category,
            quote,
            revised,
            reason="icon_placeholder",
            sentence_index=sentence_index,
        )
        return None
    if category in HINT_ONLY_CATEGORIES:
        if not quote or not problem:
            _log_diagnose_drop("normalize", category, quote, revised, reason="empty", sentence_index=sentence_index)
            return None
        if revised and _is_identity_revision(quote, revised):
            revised = ""
    else:
        if not quote or not revised or not problem:
            _log_diagnose_drop("normalize", category, quote, revised, reason="empty", sentence_index=sentence_index)
            return None
        if _is_identity_revision(quote, revised):
            _log_diagnose_drop("normalize", category, quote, revised, reason="identity", sentence_index=sentence_index)
            return None
    problem = compact_diagnose_text(problem, _DIAGNOSE_PROBLEM_MAX)
    return {
        "sentence_index": sentence_index,
        "quote": quote,
        "category": category,
        "severity": severity,
        "problem": problem,
        "revised": revised,
        "ruleable": _parse_ruleable(raw.get("ruleable")),
        "rule_hint": str(raw.get("rule_hint") or "").strip(),
    }


def parse_diagnoses_payload(payload: Any, allowed_indexes: Optional[set] = None) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    diagnoses = payload.get("diagnoses")
    if not isinstance(diagnoses, list):
        return []
    normalized = []
    for item in diagnoses:
        parsed = _normalize_diagnosis(item, allowed_indexes=allowed_indexes)
        if parsed:
            normalized.append(parsed)
    return normalized


def diagnosis_to_candidate(diag: dict, original_text: str = "") -> dict:
    quote = str(diag.get("quote") or "").strip()
    revised = str(diag.get("revised") or "").strip()
    original = str(original_text or quote).strip()
    if quote and original and quote in original and revised:
        template_text = original.replace(quote, revised, 1)
    else:
        template_text = revised or original
    return {
        "template_text": template_text,
        "raw_template_text": template_text,
        "template_id": "ai_diagnose",
        "rule_source": "ai_diagnose",
        "match_tier": "diagnose",
        "category": diag.get("category") or "other",
        "severity": diag.get("severity") or "low",
        "quote": quote,
        "revised": revised,
        "problem": str(diag.get("problem") or ""),
        "ruleable": bool(diag.get("ruleable")),
        "rule_hint": str(diag.get("rule_hint") or ""),
    }


def diagnoses_to_cat_items(diagnoses: list[dict], sentence_items: list[dict]) -> list[dict]:
    sentence_by_index = {
        item.get("sentence_index"): item
        for item in sentence_items or []
        if isinstance(item, dict)
    }
    results = []
    for diag in diagnoses or []:
        if not isinstance(diag, dict):
            continue
        idx = diag.get("sentence_index")
        sent = sentence_by_index.get(idx) or {}
        original = str(
            sent.get("source_sentence_text")
            or sent.get("text")
            or sent.get("original_text")
            or diag.get("quote")
            or ""
        ).strip()
        candidate = diagnosis_to_candidate(diag, original)
        results.append(
            {
                "original_text": original,
                "candidates": [candidate],
                "paragraph_index": sent.get("source_paragraph_index", sent.get("paragraph_index", 0)),
                "sentence_index": idx,
                "source_paragraph_index": sent.get("source_paragraph_index", sent.get("paragraph_index", 0)),
                "source_paragraph_text": sent.get("source_paragraph_text") or original,
                "source_sentence_text": original,
                "has_candidates": True,
            }
        )
    return results


def merge_local_and_diagnoses(
    cat_items: Optional[list],
    diagnoses: Optional[list],
    sentence_items: Optional[list] = None,
) -> tuple[list, list]:
    """文本路径合并去重：本地优先；同 quote 留本地；同类留更高 severity；不同类都保留。"""
    items = [item for item in (cat_items or []) if isinstance(item, dict)]
    items_by_index: dict[Any, dict] = {}
    for item in items:
        items_by_index[item.get("sentence_index")] = item

    sentence_by_index = {
        item.get("sentence_index"): item
        for item in sentence_items or []
        if isinstance(item, dict)
    }
    kept_diagnoses = []

    for diag in diagnoses or []:
        if not isinstance(diag, dict):
            continue
        idx = diag.get("sentence_index")
        quote_key = _norm_text(diag.get("quote"))
        category = diag.get("category")
        severity = str(diag.get("severity") or "low")
        sent_preview = sentence_by_index.get(idx) or {}
        original_preview = str(
            sent_preview.get("source_sentence_text")
            or sent_preview.get("text")
            or sent_preview.get("original_text")
            or diag.get("quote")
            or ""
        ).strip()
        if _is_identity_revision(diag.get("quote"), diag.get("revised"), original_preview):
            if category in HINT_ONLY_CATEGORIES:
                diag = dict(diag)
                diag["revised"] = ""
            else:
                _log_diagnose_drop(
                    "merge",
                    category,
                    diag.get("quote"),
                    diag.get("revised"),
                    reason="identity",
                    sentence_index=idx,
                )
                continue
        local = items_by_index.get(idx)
        local_categories = set()
        local_quotes = set()
        if local:
            local_quotes.add(_norm_text(local.get("original_text")))
            for candidate in local.get("candidates") or []:
                if not isinstance(candidate, dict):
                    continue
                local_categories.add(candidate.get("category"))
                local_quotes.add(_norm_text(candidate.get("template_text")))
                local_quotes.add(_norm_text(candidate.get("quote")))
        if quote_key and quote_key in local_quotes:
            continue
        if local and category in local_categories:
            for candidate in local.get("candidates") or []:
                if not isinstance(candidate, dict):
                    continue
                if candidate.get("category") != category:
                    continue
                if SEVERITY_RANK.get(severity, 0) > SEVERITY_RANK.get(str(candidate.get("severity") or ""), 0):
                    candidate["severity"] = severity
                break
            continue
        sent = sentence_by_index.get(idx) or local or {}
        original = str(
            sent.get("source_sentence_text")
            or sent.get("text")
            or sent.get("original_text")
            or diag.get("quote")
            or ""
        ).strip()
        candidate = diagnosis_to_candidate(diag, original)
        if local:
            local.setdefault("candidates", []).append(candidate)
            local["has_candidates"] = True
        else:
            new_item = {
                "original_text": original,
                "candidates": [candidate],
                "paragraph_index": sent.get("source_paragraph_index", sent.get("paragraph_index", 0)),
                "sentence_index": idx,
                "source_paragraph_index": sent.get("source_paragraph_index", sent.get("paragraph_index", 0)),
                "source_paragraph_text": sent.get("source_paragraph_text") or original,
                "source_sentence_text": original,
                "has_candidates": True,
            }
            items_by_index[idx] = new_item
            items.append(new_item)
        kept_diagnoses.append(diag)
    return items, kept_diagnoses


def _build_prompt(sentences: list[dict], terminology: Any, sentence_guide: str, product_type: str) -> str:
    payload = []
    for item in sentences:
        payload.append(
            {
                "sentence_index": item.get("sentence_index"),
                "text": str(item.get("text") or item.get("source_sentence_text") or item.get("original_text") or ""),
            }
        )
    product = str(product_type or "").strip() or "仪器"
    return _DIAGNOSE_PROMPT.format(
        product=product,
        terminology_md=_format_terminology(terminology),
        sentence_guide=_clip_text((sentence_guide or "").strip() or "（无）", diagnose_guide_max_chars()),
        json_sentences=json.dumps(payload, ensure_ascii=False),
    )


def _chat_diagnose(prompt: str, request_label: str = "polish.diagnose") -> str:
    from app.utils.ai_client import ai_client

    if not ai_client or not getattr(ai_client, "has_any_client", False):
        return ""
    result = lab_ai_chat(
        [{"role": "user", "content": prompt}],
        max_tokens=2048,
        temperature=0,
        request_label=request_label,
        timeout=int(max(1, diagnose_timeout())),
    )
    if isinstance(result, dict):
        return str(result.get("content") or result.get("text") or "")
    return str(result or "")


def _item_text(item: dict) -> str:
    return str(item.get("text") or item.get("source_sentence_text") or item.get("original_text") or "").strip()


def _infer_category(problem: str) -> str:
    text = str(problem or "")
    rules = (
        (r"术语|专名", "term"),
        (r"标点|错别字|拼写|空格|单位", "spelling"),
        (r"语法", "grammar"),
        (r"用词|口语", "word"),
        (r"歧义|指代", "ambiguity"),
        (r"冗余|重复", "redundancy"),
        (r"语体|祈使", "register"),
        (r"逻辑|顺序|矛盾", "logic"),
        (r"缺失|缺少", "missing"),
        (r"风险|安全", "risk"),
    )
    for pattern, category in rules:
        if re.search(pattern, text):
            return category
    return "other"


def parse_validate_output(raw: str) -> Optional[tuple[str, str]]:
    text = str(raw or "").strip().strip("\"'")
    if not text:
        return None
    compact = re.sub(r"\s+", "", text)
    if compact in {"无需修改", "无需修改。"}:
        return None
    parts = re.split(r"\s*[|｜]\s*", text)
    if len(parts) < 2:
        return None
    severity_token = parts[-1].strip()
    severity = _SEVERITY_ALIASES.get(severity_token.lower()) or _SEVERITY_ALIASES.get(severity_token)
    if severity not in SEVERITIES:
        return None
    problem = "|".join(parts[:-1]).strip()
    if not problem:
        return None
    return problem, severity


def parse_revisions_payload(payload: Any, sentences: list[dict]) -> dict:
    items = []
    if isinstance(payload, dict):
        raw = payload.get("revisions")
        if raw is None:
            raw = payload.get("diagnoses")
        if isinstance(raw, list):
            items = raw
    elif isinstance(payload, list):
        items = payload
    originals = {item.get("sentence_index"): _item_text(item) for item in sentences}
    by_index = {}
    for raw in items:
        if not isinstance(raw, dict):
            continue
        try:
            idx = int(raw.get("sentence_index"))
        except (TypeError, ValueError):
            continue
        if idx not in originals:
            continue
        revised = str(raw.get("revised") or raw.get("text") or "").strip()
        if not revised:
            continue
        original = originals.get(idx) or ""
        if _is_identity_revision(original, revised, original):
            continue
        by_index[idx] = revised
    return by_index


def parse_validate_payload(payload: Any) -> dict:
    items = []
    if isinstance(payload, dict):
        raw = payload.get("results")
        if raw is None:
            raw = payload.get("diagnoses")
        if isinstance(raw, list):
            items = raw
    elif isinstance(payload, list):
        items = payload
    parsed = {}
    for raw in items:
        if not isinstance(raw, dict):
            continue
        try:
            idx = int(raw.get("sentence_index"))
        except (TypeError, ValueError):
            continue
        output = str(raw.get("output") or raw.get("verdict") or "").strip()
        if not output and raw.get("problem") and raw.get("severity"):
            output = f"{raw.get('problem')} | {raw.get('severity')}"
        parsed[idx] = parse_validate_output(output)
    return parsed


async def _chat_json(prompt: str, request_label: str) -> Optional[dict]:
    timeout = diagnose_timeout()
    try:
        raw = await asyncio.wait_for(
            asyncio.to_thread(_chat_diagnose, prompt, request_label),
            timeout=timeout,
        )
    except Exception as exc:
        logger.warning("[CAT_DIAGNOSE] %s 调用失败: %s", request_label, exc)
        return None
    payload = extract_json_object(raw)
    if payload is not None:
        return payload
    retry_prompt = prompt + "\n\n上次输出不是合法 JSON。请只输出 JSON 对象。"
    try:
        raw = await asyncio.wait_for(
            asyncio.to_thread(_chat_diagnose, retry_prompt, request_label),
            timeout=timeout,
        )
    except Exception as exc:
        logger.warning("[CAT_DIAGNOSE] %s JSON 重试失败: %s", request_label, exc)
        return None
    return extract_json_object(raw)


async def _diagnose_batch_single(
    sentences: list[dict],
    terminology: Any,
    sentence_guide: str,
    product_type: str,
    allowed_indexes: Optional[set] = None,
    original_by_index: Optional[dict] = None,
) -> list[dict]:
    if not sentences:
        return []
    allowed = allowed_indexes if allowed_indexes is not None else {item.get("sentence_index") for item in sentences}
    prompt = _build_prompt(sentences, terminology, sentence_guide, product_type)
    timeout = diagnose_timeout()
    try:
        raw = await asyncio.wait_for(asyncio.to_thread(_chat_diagnose, prompt), timeout=timeout)
    except Exception as exc:
        logger.warning("[CAT_DIAGNOSE] 批次调用失败: %s", exc)
        return []
    payload = extract_json_object(raw)
    if payload is None:
        retry_prompt = prompt + "\n\n上次输出不是合法 JSON。请只输出 JSON 对象。"
        try:
            raw = await asyncio.wait_for(asyncio.to_thread(_chat_diagnose, retry_prompt), timeout=timeout)
        except Exception as exc:
            logger.warning("[CAT_DIAGNOSE] JSON 重试失败: %s", exc)
            return []
        payload = extract_json_object(raw)
        if payload is None:
            return []
    raw_items = payload.get("diagnoses") if isinstance(payload, dict) else []
    if isinstance(raw_items, list):
        logger.info("[CAT_DIAGNOSE] batch raw_diagnoses=%s", len(raw_items))
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue
            logger.info(
                "[CAT_DIAGNOSE] raw category=%s quote=%s revised=%s sentence_index=%s",
                str(raw_item.get("category") or ""),
                str(raw_item.get("quote") or ""),
                str(raw_item.get("revised") or ""),
                raw_item.get("sentence_index"),
            )
    parsed = parse_diagnoses_payload(payload, allowed_indexes=allowed)
    originals = dict(original_by_index or {})
    for item in sentences:
        originals.setdefault(
            item.get("sentence_index"),
            str(item.get("text") or item.get("source_sentence_text") or item.get("original_text") or ""),
        )
    kept = []
    for diag in parsed:
        original = originals.get(diag.get("sentence_index"), "")
        if _is_identity_revision(diag.get("quote"), diag.get("revised"), original):
            if diag.get("category") in HINT_ONLY_CATEGORIES:
                diag = dict(diag)
                diag["revised"] = ""
            else:
                _log_diagnose_drop(
                    "batch",
                    diag.get("category"),
                    diag.get("quote"),
                    diag.get("revised"),
                    reason="identity",
                    sentence_index=diag.get("sentence_index"),
                )
                continue
        kept.append(diag)
    return kept


async def _diagnose_batch_decoupled(
    sentences: list[dict],
    allowed_indexes: Optional[set] = None,
    original_by_index: Optional[dict] = None,
) -> list[dict]:
    if not sentences:
        return []
    allowed = allowed_indexes if allowed_indexes is not None else {item.get("sentence_index") for item in sentences}
    originals = dict(original_by_index or {})
    payload_sentences = []
    for item in sentences:
        idx = item.get("sentence_index")
        text = _item_text(item)
        originals.setdefault(idx, text)
        payload_sentences.append({"sentence_index": idx, "text": text})
    rewrite_prompt = _REWRITE_PROMPT.format(json_sentences=json.dumps(payload_sentences, ensure_ascii=False))
    rewrite_payload = await _chat_json(rewrite_prompt, "polish.rewrite")
    revisions = parse_revisions_payload(rewrite_payload, sentences)
    logger.info("[CAT_DIAGNOSE] decoupled rewrite changed=%s / %s", len(revisions), len(sentences))
    batch_n = len(sentences)
    batch_m = len(revisions)
    if not revisions:
        _add_decoupled_stats(
            stage1_no_change=batch_n,
            stage1_revised=0,
            stage2_rejected=0,
            produced=0,
        )
        return []
    pairs = []
    for item in sentences:
        idx = item.get("sentence_index")
        revised = revisions.get(idx)
        if not revised:
            continue
        pairs.append({
            "sentence_index": idx,
            "original": originals.get(idx) or _item_text(item),
            "revised": revised,
        })
    if not pairs:
        _add_decoupled_stats(
            stage1_no_change=batch_n - batch_m,
            stage1_revised=batch_m,
            stage2_rejected=0,
            produced=0,
        )
        return []
    validate_prompt = _VALIDATE_PROMPT.format(json_pairs=json.dumps(pairs, ensure_ascii=False))
    validate_payload = await _chat_json(validate_prompt, "polish.validate")
    verdicts = parse_validate_payload(validate_payload)
    raw_items = []
    batch_k = 0
    for pair in pairs:
        idx = pair["sentence_index"]
        if idx not in allowed:
            continue
        parsed = verdicts.get(idx)
        if not parsed:
            batch_k += 1
            _log_diagnose_drop(
                "validate",
                "",
                pair["original"],
                pair["revised"],
                reason="no_change",
                sentence_index=idx,
            )
            continue
        problem, severity = parsed
        raw_items.append({
            "sentence_index": idx,
            "quote": pair["original"],
            "category": _infer_category(problem),
            "severity": severity,
            "problem": problem,
            "revised": pair["revised"],
            "ruleable": False,
            "rule_hint": "",
        })
    kept = parse_diagnoses_payload({"diagnoses": raw_items}, allowed_indexes=allowed)
    _add_decoupled_stats(
        stage1_no_change=batch_n - batch_m,
        stage1_revised=batch_m,
        stage2_rejected=batch_k,
        produced=len(kept),
    )
    return kept


async def _diagnose_batch(
    sentences: list[dict],
    terminology: Any,
    sentence_guide: str,
    product_type: str,
    allowed_indexes: Optional[set] = None,
    original_by_index: Optional[dict] = None,
) -> list[dict]:
    if diagnose_mode() == "single":
        return await _diagnose_batch_single(
            sentences,
            terminology,
            sentence_guide,
            product_type,
            allowed_indexes=allowed_indexes,
            original_by_index=original_by_index,
        )
    return await _diagnose_batch_decoupled(
        sentences,
        allowed_indexes=allowed_indexes,
        original_by_index=original_by_index,
    )


async def open_diagnose_sentences(
    sentences: list[dict],
    terminology: dict,
    sentence_guide: str,
    product_type: str = "",
    mode: Optional[str] = None,
) -> list[dict]:
    """开放式病句诊断。无问题或失败时返回空数组。"""
    if not is_ai_diagnose_enabled():
        return []
    items = [item for item in sentences or [] if isinstance(item, dict)]
    if not items:
        return []
    global _active_diagnose_mode
    previous_mode = _active_diagnose_mode
    _active_diagnose_mode = diagnose_mode(mode)
    batch_size = diagnose_batch_size()
    diagnoses: list[dict] = []
    all_allowed = {item.get("sentence_index") for item in items}
    all_originals = {
        item.get("sentence_index"): str(
            item.get("text") or item.get("source_sentence_text") or item.get("original_text") or ""
        )
        for item in items
    }
    try:
        if _active_diagnose_mode == "decoupled":
            _reset_decoupled_stats()
        total_batches = (len(items) + batch_size - 1) // batch_size
        logger.info(
            "[CAT_DIAGNOSE] start mode=%s sentences=%s batch_size=%s batches=%s timeout=%s",
            _active_diagnose_mode,
            len(items),
            batch_size,
            total_batches,
            diagnose_timeout(),
        )
        for start in range(0, len(items), batch_size):
            batch = items[start : start + batch_size]
            logger.info(
                "[CAT_DIAGNOSE] batch %s/%s size=%s",
                start // batch_size + 1,
                total_batches,
                len(batch),
            )
            diagnoses.extend(
                await _diagnose_batch(
                    batch,
                    terminology,
                    sentence_guide,
                    product_type,
                    allowed_indexes=all_allowed,
                    original_by_index=all_originals,
                )
            )
    except Exception as exc:
        logger.warning("[CAT_DIAGNOSE] 诊断失败，静默降级: %s", exc)
        return []
    finally:
        if _active_diagnose_mode == "decoupled":
            stats = _last_decoupled_stats
            logger.info(
                "[CAT_DIAGNOSE] decoupled stage1_no_change=%s stage1_revised=%s stage2_rejected=%s produced=%s",
                stats.get("stage1_no_change", 0),
                stats.get("stage1_revised", 0),
                stats.get("stage2_rejected", 0),
                stats.get("produced", 0),
            )
        _active_diagnose_mode = previous_mode
    return diagnoses
