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
5. category 只能从枚举取；severity 只能是 low/medium/high。
6. 只输出 JSON，不要任何解释文字。
7. 诊断成立时：logic、missing、ambiguity 三类允许 revised 为空（写清 problem 与 rationale 即可）。其他类别若你能给出忠实改写则必须给出；若你识别出问题但给不出忠实改写，请改用 logic/missing/ambiguity 类别并把 revised 留空——这优于沉默。
8. 若该问题可沉淀为可复用规则，设置 ruleable=true，并给出 rule_hint（匹配模式或替换说明）；否则 ruleable=false、rule_hint 为空。

category 枚举：spelling, grammar, word, term, ambiguity, redundancy, syntax, logic, missing, register, audience, risk, other

【术语表】
{terminology_md}

【风格指南】
{sentence_guide}

【待审查句子】
{json_sentences}

输出格式：
{{"diagnoses":[{{"sentence_index":0,"quote":"...","category":"term","severity":"high","problem":"...","revised":"...","rationale":"...","ruleable":false,"rule_hint":""}}]}}
无问题返回 {{"diagnoses":[]}}。
"""



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


def _log_diagnose_drop(stage: str, category: Any, quote: Any, revised: Any) -> None:
    logger.info(
        "[CAT_DIAGNOSE] drop stage=%s category=%s quote=%s revised=%s",
        stage,
        str(category or ""),
        str(quote or ""),
        str(revised or ""),
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
    """给现有 candidate 补 category/severity，已有字段不覆盖。"""
    for item in items or []:
        if not isinstance(item, dict):
            continue
        for candidate in item.get("candidates") or []:
            if not isinstance(candidate, dict):
                continue
            mapped_category, mapped_severity = map_rule_to_category(
                issue=candidate,
                rule_source=str(candidate.get("rule_source") or ""),
                rule_name=str(candidate.get("rule_name") or ""),
                match_detail=candidate,
                issue_type=str(candidate.get("type") or item.get("type") or ""),
            )
            if not candidate.get("category"):
                candidate["category"] = mapped_category
            if not candidate.get("severity"):
                candidate["severity"] = mapped_severity
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


def _normalize_diagnosis(raw: Any, allowed_indexes: Optional[set] = None) -> Optional[dict]:
    if not isinstance(raw, dict):
        return None
    try:
        sentence_index = int(raw.get("sentence_index"))
    except (TypeError, ValueError):
        return None
    if allowed_indexes is not None and sentence_index not in allowed_indexes:
        return None
    category = str(raw.get("category") or "").strip()
    severity = str(raw.get("severity") or "").strip()
    if category not in CATEGORIES or severity not in SEVERITIES:
        return None
    quote = str(raw.get("quote") or "").strip()
    revised = str(raw.get("revised") or "").strip()
    problem = str(raw.get("problem") or "").strip()
    if category in HINT_ONLY_CATEGORIES:
        if not quote or not problem:
            _log_diagnose_drop("normalize", category, quote, revised)
            return None
        if revised and _is_identity_revision(quote, revised):
            revised = ""
    else:
        if not quote or not revised or not problem:
            _log_diagnose_drop("normalize", category, quote, revised)
            return None
        if _is_identity_revision(quote, revised):
            _log_diagnose_drop("normalize", category, quote, revised)
            return None
    return {
        "sentence_index": sentence_index,
        "quote": quote,
        "category": category,
        "severity": severity,
        "problem": problem,
        "revised": revised,
        "rationale": str(raw.get("rationale") or "").strip(),
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
        "rationale": str(diag.get("rationale") or ""),
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
                _log_diagnose_drop("merge", category, diag.get("quote"), diag.get("revised"))
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


def _chat_diagnose(prompt: str) -> str:
    from app.utils.ai_client import ai_client

    if not ai_client or not getattr(ai_client, "has_any_client", False):
        return ""
    result = lab_ai_chat(
        [{"role": "user", "content": prompt}],
        max_tokens=2048,
        temperature=0.1,
        request_label="polish.diagnose",
        timeout=int(max(1, diagnose_timeout())),
    )
    if isinstance(result, dict):
        return str(result.get("content") or result.get("text") or "")
    return str(result or "")


async def _diagnose_batch(sentences: list[dict], terminology: Any, sentence_guide: str, product_type: str) -> list[dict]:
    if not sentences:
        return []
    allowed = {item.get("sentence_index") for item in sentences}
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
                "[CAT_DIAGNOSE] raw category=%s quote=%s revised=%s",
                str(raw_item.get("category") or ""),
                str(raw_item.get("quote") or ""),
                str(raw_item.get("revised") or ""),
            )
    parsed = parse_diagnoses_payload(payload, allowed_indexes=allowed)
    original_by_index = {
        item.get("sentence_index"): str(
            item.get("text") or item.get("source_sentence_text") or item.get("original_text") or ""
        )
        for item in sentences
    }
    kept = []
    for diag in parsed:
        original = original_by_index.get(diag.get("sentence_index"), "")
        if _is_identity_revision(diag.get("quote"), diag.get("revised"), original):
            if diag.get("category") in HINT_ONLY_CATEGORIES:
                diag = dict(diag)
                diag["revised"] = ""
            else:
                _log_diagnose_drop("batch", diag.get("category"), diag.get("quote"), diag.get("revised"))
                continue
        kept.append(diag)
    return kept


async def open_diagnose_sentences(
    sentences: list[dict],
    terminology: dict,
    sentence_guide: str,
    product_type: str = "",
) -> list[dict]:
    """开放式病句诊断。无问题或失败时返回空数组。"""
    if not is_ai_diagnose_enabled():
        return []
    items = [item for item in sentences or [] if isinstance(item, dict)]
    if not items:
        return []
    batch_size = diagnose_batch_size()
    diagnoses: list[dict] = []
    try:
        total_batches = (len(items) + batch_size - 1) // batch_size
        logger.info(
            "[CAT_DIAGNOSE] start sentences=%s batch_size=%s batches=%s timeout=%s",
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
            diagnoses.extend(await _diagnose_batch(batch, terminology, sentence_guide, product_type))
    except Exception as exc:
        logger.warning("[CAT_DIAGNOSE] 诊断失败，静默降级: %s", exc)
        return []
    return diagnoses
