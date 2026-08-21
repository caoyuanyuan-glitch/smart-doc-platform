"""模板文件一次性解析器 —— 生成 document_profile / example_bank / retrieval_index.

缓存策略：
    - 每个模板文件按 SHA256(filename + raw_bytes) 生成唯一 hash
    - 同时在内存（TEMPLATE_PROFILE_CACHE）和磁盘（/tmp/doc_profiles/<hash>.json）缓存
    - 换模板 → hash 变 → 自动重新生成，完全一次性

文件大小限制：MAX_TEMPLATE_SIZE_BYTES（10MB），超过直接拒绝。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from dataclasses import dataclass, field, asdict
from typing import Callable, Dict, List, Optional, Tuple

from app.utils.document_parser import parse_file

CACHE_DIR = "/tmp/doc_profiles"
TEMPLATE_PROFILE_CACHE: Dict[str, dict] = {}

MAX_TEMPLATE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

PROFILE_MAX_CHARS = 8000
EXAMPLE_MAX_CHARS = 12000

_AI_MAX_RETRIES = 2  # AI JSON 抽取失败时自动重试次数


INTENT_QUERY_KEYWORDS: Dict[str, Dict[str, int]] = {
    "next_step": {
        "操作": 3, "步骤": 3, "流程": 3, "方法": 2, "启动": 2, "打开": 2,
        "按下": 2, "执行": 2, "然后": 1, "随后": 1, "依次": 2, "顺序": 2,
    },
    "expand_detail": {
        "详细": 3, "说明": 3, "定义": 2, "机制": 2, "原理": 2, "特性": 2,
        "特点": 2, "介绍": 2, "具体": 2, "功能": 2, "组成": 2,
    },
    "supplement_parameters": {
        "参数": 3, "数值": 3, "范围": 3, "规格": 3, "电压": 3, "温度": 3,
        "湿度": 3, "容量": 3, "重量": 3, "尺寸": 3, "频率": 3, "功率": 3,
        "电流": 3, "压力": 3, "阈值": 3, "工作条件": 3, "环境要求": 3,
    },
    "supplement_notices": {
        "注意": 3, "须知": 3, "提醒": 3, "提示": 3, "禁止": 3,
        "建议": 2, "应该": 2, "不得": 2, "请勿": 3, "不可": 2,
        "必须": 2, "务必": 2, "须知": 3,
    },
    "safety_warning": {
        "警告": 3, "风险": 3, "安全": 3, "危险": 3, "禁止": 3,
        "限制": 3, "前提": 3, "异常": 3, "可能导致": 3, "切勿": 3,
        "严禁": 3, "当心": 3, "伤害": 3, "火灾": 3, "触电": 3,
        "中毒": 3, "爆炸": 3,
    },
    "troubleshooting": {
        "故障": 3, "异常": 3, "排查": 3, "处理": 3, "错误": 3,
        "报警": 3, "问题": 3, "失效": 3, "停机": 3, "死机": 3,
        "无法": 2, "检查": 2, "恢复": 2, "原因": 2, "解决": 2,
        "重启": 2,
    },
    "custom": {},
}

INTENT_TO_QUERY_LABEL: Dict[str, str] = {
    "next_step": "操作步骤",
    "expand_detail": "详细说明",
    "supplement_parameters": "参数说明",
    "supplement_notices": "注意事项",
    "safety_warning": "安全警告",
    "troubleshooting": "故障处理",
    "custom": "通用",
}


# ── 缓存层 ─────────────────────────────────────────────────────────────────


def _cache_key(filename: str, raw: bytes) -> str:
    seed = (filename or "").encode("utf-8") + (raw or b"")
    return hashlib.sha256(seed).hexdigest()


def _disk_path(key: str) -> str:
    return os.path.join(CACHE_DIR, f"{key}.json")


def _save_cache(key: str, profile: dict) -> None:
    TEMPLATE_PROFILE_CACHE[key] = profile
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(_disk_path(key), "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False)
    except Exception:
        pass


def _load_cache(key: str) -> Optional[dict]:
    if key in TEMPLATE_PROFILE_CACHE:
        return TEMPLATE_PROFILE_CACHE[key]
    try:
        disk = _disk_path(key)
        if os.path.exists(disk):
            with open(disk, "r", encoding="utf-8") as f:
                data = json.load(f)
            TEMPLATE_PROFILE_CACHE[key] = data
            return data
    except Exception:
        pass
    return None


# ── 章节分块 ───────────────────────────────────────────────────────────────


@dataclass
class SectionBlock:
    title: str
    level: int
    content: str
    keywords: List[str] = field(default_factory=list)


_HEADING_RE = re.compile(
    r"^(?:"
    r"#{1,6}\s+(.+?)\s*#*$"
    r"|\s{0,3}(\d+(?:[\.\)、]\s*?)+)([^\d].+?)\s*$"
    r"|\s{0,3}(第[一二三四五六七八九十百千\d]+[章节篇部分][^\s]{0,20})"
    r"|\s{0,3}((?:附录|附件)[A-Z0-9]?\s*.+)"
    r")"
)


def _chunk_by_sections(text: str) -> List[SectionBlock]:
    if not text:
        return []

    lines = text.split("\n")
    chunks: List[SectionBlock] = []
    cur_title = "根"
    cur_level = 0
    cur_buf: List[str] = []

    def flush():
        body = "\n".join(cur_buf).strip()
        if body:
            chunks.append(SectionBlock(
                title=cur_title,
                level=cur_level,
                content=body,
                keywords=_extract_keywords(cur_title + "\n" + body[:400]),
            ))

    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped:
            if cur_buf and cur_buf[-1] != "":
                cur_buf.append("")
            continue

        m = _HEADING_RE.match(raw_line)
        if m:
            flush()
            cur_level = min(6, raw_line.count("#") or 2)
            cur_title = stripped.lstrip("#").strip()
            cur_buf = []
        else:
            cur_buf.append(stripped)

    flush()
    return chunks


def _extract_keywords(text: str, top_k: int = 12) -> List[str]:
    counts: Dict[str, int] = {}
    for token in re.findall(r"[\u4e00-\u9fffA-Za-z]{2,}", text):
        if token.isascii() and len(token) < 3:
            continue
        counts[token] = counts.get(token, 0) + 1
    return [t for t, _ in sorted(counts.items(), key=lambda x: -x[1])[:top_k]]


# ── 检索引擎 ───────────────────────────────────────────────────────────────


def _score_chunk(chunk: SectionBlock, query_terms: Dict[str, int]) -> float:
    content = chunk.content + " " + chunk.title
    if not content:
        return 0.0

    score = 0.0
    for term, weight in query_terms.items():
        if not term:
            continue
        if term in chunk.title:
            score += weight * 3.0
        score += content.count(term) * weight

    if not score and not query_terms:
        tri = {content[i:i+3] for i in range(max(0, len(content)-2))}
        score += len(tri) * 0.001

    length_factor = 1.0 if len(content) < 400 else 0.9
    return score * length_factor


def _rank_chunks(chunks: List[SectionBlock], intent: str, query: str = "", top_k: int = 5) -> List[Tuple[SectionBlock, float]]:
    query_terms: Dict[str, int] = dict(INTENT_QUERY_KEYWORDS.get(intent) or {})
    for token in re.findall(r"[\u4e00-\u9fffA-Za-z]{2,}", query or ""):
        query_terms[token] = max(query_terms.get(token, 1), 3)

    scored = [(_, _score_chunk(_, query_terms)) for _ in chunks]
    scored = [_ for _ in scored if _[1] > 0 or len(query_terms) == 0]
    scored.sort(key=lambda x: -x[1])
    return scored[:top_k]


def retrieve_for_intent(profile: dict, intent: str, query: str = "", max_chars: int = 1500) -> List[dict]:
    sections = profile.get("sections") or []
    chunks = [
        SectionBlock(title=s.get("title", ""), level=s.get("level", 0),
                     content=s.get("content", ""))
        for s in sections if s.get("content")
    ]
    ranked = _rank_chunks(chunks, intent, query, top_k=6)

    picked: List[dict] = []
    budget = max_chars
    for blk, score in ranked:
        if budget <= 0:
            break
        piece = blk.content[:budget]
        picked.append({
            "title": blk.title,
            "content": piece,
            "score": round(score, 2),
        })
        budget -= len(piece)

    return picked


# ── Schema 校验（手写，零额外依赖）────────────────────────────────────────

_SCHEMA_DOC_PROFILE = {
    "writing_style": (str, ""),
    "format_spec": (str, ""),
    "chapter_structure": (list, []),
    "glossary": (list, []),
    "forbidden_expressions": (list, []),
    "typical_sentences": (list, []),
}

_SCHEMA_EXAMPLE_BANK = {k: (list, []) for k in INTENT_QUERY_KEYWORDS}


def _validate_against_schema(data: dict, schema: dict) -> Tuple[dict, bool]:
    """按 schema 校验字典，返回 (补齐默认值的字典, 是否全部通过)。"""
    ok = True
    if not isinstance(data, dict):
        return {k: default for k, (_, default) in schema.items()}, False
    result: dict = {}
    for key, (expected_type, default) in schema.items():
        val = data.get(key)
        if not isinstance(val, expected_type):
            result[key] = default
            ok = False
        else:
            # 对列表里的元素做浅清洗
            if expected_type is list and val:
                cleaned = []
                for item in val[:25]:
                    if isinstance(item, str):
                        s = item.strip()
                        if s:
                            cleaned.append(s)
                    elif isinstance(item, dict):
                        cleaned.append(item)
                result[key] = cleaned
            else:
                result[key] = val
    return result, ok


# ── AI 一次性提取（含重试 + fallback）────────────────────────────────────


_PROFILE_SYSTEM = (
    "[角色] 技术文档分析专家。"
    "[任务] 阅读一份技术说明书，提炼写作风格、格式规范、章节结构、术语表、禁用表达、典型句式。"
    "[输出要求] 严格输出 JSON，键固定为：writing_style / format_spec / chapter_structure / glossary / forbidden_expressions / typical_sentences。"
    "glossary 为 [{\"term\":\"...\",\"def\":\"...\"}] 列表（最多 20 条），其他项为字符串或字符串数组。"
    "禁止输出 JSON 以外的任何文字、Markdown 或解释性段落。"
)

_EXAMPLE_SYSTEM = (
    "[角色] 技术文档样例抽取专家。"
    "[任务] 从说明书中按意图分类抽取高质量的原文样例句子。"
    "[输出要求] 严格输出 JSON，键固定为：next_step / expand_detail / supplement_parameters / supplement_notices / safety_warning / troubleshooting。"
    "每个键对应一个字符串数组，每一项是原文中能代表该类写法的完整句子（不要改写），每类 2-6 条。"
    "若某类在原文中缺失，留空数组。"
    "禁止输出 JSON 以外的任何文字。"
)


def _call_ai_for_json(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 2000,
    timeout_label: str = "",
    schema: Optional[dict] = None,
    retries: int = _AI_MAX_RETRIES,
) -> Tuple[dict, bool]:
    """调 AI 拿 JSON。返回 (dict, schema_ok)。失败则返回默认值并标记 schema_ok=False。"""
    from app.utils.ai_client import ai_client

    last_ok = False
    last_result: dict = {}

    for attempt in range(retries + 1):
        try:
            raw = ai_client.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=max_tokens,
                temperature=0.1,
                kimi_thinking="disabled",
                skip_kimi=False,
                request_label=f"template_profiler:{timeout_label}:try{attempt}",
            )
            parsed = _parse_json_safe(raw)
            if schema is not None:
                validated, ok = _validate_against_schema(parsed, schema)
                last_result = validated
                last_ok = ok
                if ok:
                    return last_result, True
                print(f"[template_profiler] schema mismatch ({timeout_label}), "
                      f"retry {attempt + 1}/{retries}")
            else:
                if parsed:
                    return parsed, True
                last_result = parsed
        except Exception as e:
            print(f"[template_profiler] AI call failed ({timeout_label}, attempt {attempt}): {e}")
            last_result = {}

    # 全部重试失败，返回补齐默认值的字典
    if schema is not None:
        return {k: default for k, (_, default) in schema.items()}, False
    return last_result, False


def _parse_json_safe(text: str) -> dict:
    if not text:
        return {}
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, count=1).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    first, last = cleaned.find("{"), cleaned.rfind("}")
    if first != -1 and last != -1 and last > first:
        try:
            return json.loads(cleaned[first:last+1])
        except Exception:
            pass
    return {}


# ── 本地轻量 fallback ─────────────────────────────────────────────────────


_FALLBACK_WORDS_FORBIDDEN = [
    "请按照说明书操作", "注意安全", "相关信息请参见下文",
    "如有疑问请联系客服", "请妥善保管", "产品以实物为准",
]

_FALLBACK_WORDS_KEY = {
    "forbidden_re": re.compile(r"^(\s|>)*(注意|警告|危险|严禁|切勿|不得|禁止|风险)[^，。；！\n]{2,40}[！。]?", re.MULTILINE),
    "notice_re": re.compile(r"(注意|须知|提醒|提示)[：:][^\n]{2,60}", re.MULTILINE),
    "safety_re": re.compile(r"(警告|危险|严禁|切勿|不得)[^，。；！\n]{2,60}[！]?", re.MULTILINE),
}


def _fallback_profile_local(full_text: str, sections: List[SectionBlock]) -> dict:
    """不调 AI，用正则 + 统计做粗粒度 profile。"""
    lines = full_text.splitlines()

    # chapter_structure：直接用章节标题
    chapter_structure: List[str] = []
    for s in sections[:30]:
        title = s.title.strip()
        if title and title != "根" and len(title) <= 40:
            chapter_structure.append(title)

    # glossary：高频 2-4 字中文名词
    glossary_terms = _extract_keywords(full_text, top_k=15)
    glossary = [{"term": t, "def": ""} for t in glossary_terms]

    # forbidden_expressions
    forbidden: List[str] = list(_FALLBACK_WORDS_FORBIDDEN)

    # typical_sentences：找 notice_re 和 safety_re 命中的行
    typical: List[str] = []
    for m in _FALLBACK_WORDS_KEY["notice_re"].finditer(full_text):
        s = m.group().strip()
        if len(s) > 5 and s not in typical:
            typical.append(s)
    for m in _FALLBACK_WORDS_KEY["safety_re"].finditer(full_text):
        s = m.group().strip()
        if len(s) > 5 and s not in typical:
            typical.append(s)
    typical = typical[:10]

    # writing_style & format_spec：启发式判断
    has_numbered = any(re.match(r"^\s*\d+[\.\)]", l) for l in lines)
    has_bullet = any(re.match(r"^\s*[-*●]", l) for l in lines)
    has_table = "|" in full_text and "\n|" in full_text
    has_cn_punct = "。" in full_text and "：" in full_text

    writing_style_parts = []
    if has_numbered:
        writing_style_parts.append("大量使用数字编号步骤")
    if has_cn_punct:
        writing_style_parts.append("使用中文标点（句号、冒号）等全角符号")
    if has_table:
        writing_style_parts.append("参数以表格形式呈现")
    if not writing_style_parts:
        writing_style_parts.append("结构化、说明性技术文档风格")

    format_spec_parts = []
    if has_numbered:
        format_spec_parts.append("操作步骤用 1. 2. 3. 有序列表")
    if has_bullet:
        format_spec_parts.append("条目用项目符号列表")
    if has_table:
        format_spec_parts.append("技术参数以 Markdown 表格列出")
    if not format_spec_parts:
        format_spec_parts.append("段落式技术说明，标题层级清晰")

    return {
        "writing_style": "；".join(writing_style_parts),
        "format_spec": "；".join(format_spec_parts),
        "chapter_structure": chapter_structure,
        "glossary": glossary,
        "forbidden_expressions": forbidden,
        "typical_sentences": typical,
    }


def _fallback_examples_local(full_text: str) -> dict:
    """不调 AI，按意图关键词从原文里找对应句子。"""
    intent_to_regex: Dict[str, re.Pattern] = {
        "next_step": re.compile(
            r"^\s*\d+[\.\)]\s+[^\n]{4,80}$", re.MULTILINE
        ),
        "supplement_parameters": re.compile(
            r"(?:参数|规格|电压|温度|容量|重量|尺寸)[:：][^\n]{2,60}", re.MULTILINE
        ),
        "supplement_notices": re.compile(
            r"(注意|须知|提醒|提示|禁止|请勿|务必)[：:][^\n]{2,80}", re.MULTILINE
        ),
        "safety_warning": re.compile(
            r"(警告|危险|严禁|切勿|不得)[^\n]{2,80}", re.MULTILINE
        ),
        "troubleshooting": re.compile(
            r"(故障|异常|无法|检查|失效|停机|死机|排查)[^\n]{2,80}", re.MULTILINE
        ),
        "expand_detail": re.compile(
            r"(?:是指|定义为|表示|代表)[^\n]{4,80}", re.MULTILINE
        ),
    }

    result: Dict[str, List[str]] = {k: [] for k in INTENT_QUERY_KEYWORDS}
    for intent, pat in intent_to_regex.items():
        seen = set()
        for m in pat.finditer(full_text):
            s = m.group().strip()
            if 5 < len(s) < 200 and s not in seen:
                seen.add(s)
                result[intent].append(s)
            if len(result[intent]) >= 6:
                break
    return result


# ── 对外入口 ────────────────────────────────────────────────────────────────

ProgressCallback = Optional[Callable[[int, str], None]]


def build_template_profile(
    filename: str,
    raw: bytes,
    progress_cb: ProgressCallback = None,
) -> Optional[dict]:
    """一次性构建模板 profile，换模板自动重新生成。

    progress_cb(step, label) — step ∈ {1,2,3,4,5}
        1=文件校验通过  2=解析完成  3=风格分析完成  4=样例抽取完成  5=已缓存
    """
    # 卡点 2：文件大小限制
    size = len(raw or b"")
    if size > MAX_TEMPLATE_SIZE_BYTES:
        raise ValueError(
            f"模板文件过大：{size / 1024 / 1024:.1f} MB，"
            f"上限 {MAX_TEMPLATE_SIZE_BYTES / 1024 / 1024:.0f} MB"
        )

    key = _cache_key(filename, raw)
    cached = _load_cache(key)
    if cached:
        print(f"[template_profiler] HIT cache for {filename} (key={key[:12]}...)")
        if progress_cb:
            progress_cb(5, "模板资源已缓存，秒级命中")
        return cached

    print(f"[template_profiler] BUILDING profile for {filename} (key={key[:12]}...)")
    t0 = time.time()

    if progress_cb:
        progress_cb(1, "文件校验通过")

    temp_path = None
    try:
        suffix = os.path.splitext(filename or "")[1] or ".txt"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(raw)
            temp_path = tmp.name
        full_text = parse_file(temp_path).strip()
    except Exception:
        try:
            full_text = raw.decode("utf-8", errors="replace").strip()
        except Exception:
            return None
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass

    if not full_text:
        return None

    sections = _chunk_by_sections(full_text)
    section_dicts = [asdict(_) for _ in sections]

    if progress_cb:
        progress_cb(2, f"文档解析完成（{len(sections)} 章节，{len(full_text)} 字）")

    # 3) AI 提取 document_profile（含 schema 校验 + 最多 2 次重试）
    profile_text = full_text[:PROFILE_MAX_CHARS]
    doc_profile, doc_ok = _call_ai_for_json(
        _PROFILE_SYSTEM,
        f"=== 文档名称 ===\n{filename or '未命名'}\n\n=== 文档内容 ===\n{profile_text}\n\n请输出 JSON。",
        max_tokens=1600,
        timeout_label="profile",
        schema=_SCHEMA_DOC_PROFILE,
        retries=_AI_MAX_RETRIES,
    )

    if not doc_ok:
        print(f"[template_profiler] AI profile 抽取未通过 schema 校验 → 本地 fallback")
        doc_profile = _fallback_profile_local(full_text, sections)

    if progress_cb:
        progress_cb(3, "风格/术语/章节分析完成")

    # 4) AI 提取 example_bank
    example_text = full_text[:EXAMPLE_MAX_CHARS]
    example_bank, ex_ok = _call_ai_for_json(
        _EXAMPLE_SYSTEM,
        f"=== 文档名称 ===\n{filename or '未命名'}\n\n=== 文档内容 ===\n{example_text}\n\n请输出 JSON。",
        max_tokens=2000,
        timeout_label="examples",
        schema=_SCHEMA_EXAMPLE_BANK,
        retries=_AI_MAX_RETRIES,
    )

    if not ex_ok:
        print(f"[template_profiler] AI examples 抽取未通过 schema 校验 → 本地 fallback")
        example_bank = _fallback_examples_local(full_text)

    if progress_cb:
        progress_cb(4, "意图样例抽取完成")

    # 5) 组装
    parse_status = "ai" if (doc_ok and ex_ok) else "fallback"
    fallback_reason = None
    if parse_status == "fallback":
        reasons = []
        if not doc_ok:
            reasons.append("document_profile 未通过 schema 校验")
        if not ex_ok:
            reasons.append("example_bank 未通过 schema 校验")
        fallback_reason = "；".join(reasons)

    profile = {
        "hash": key,
        "name": filename or "未命名模板",
        "size_bytes": size,
        "char_count": len(full_text),
        "section_count": len(sections),
        "built_at": int(time.time()),
        "parse_status": parse_status,
        "fallback_reason": fallback_reason,
        "document_profile": doc_profile,
        "example_bank": example_bank,
        "sections": section_dicts,
        "full_text_preview": full_text[:2000],
    }

    _save_cache(key, profile)
    elapsed = time.time() - t0
    print(f"[template_profiler] BUILT {filename} in {elapsed:.1f}s, "
          f"sections={len(sections)}, chars={len(full_text)}, "
          f"parse_status={parse_status}")

    if progress_cb:
        progress_cb(5, f"分析完成（{elapsed:.1f}s），已缓存")

    return profile


def _normalize_document_profile(raw: dict) -> dict:
    default = {
        "writing_style": "",
        "format_spec": "",
        "chapter_structure": [],
        "glossary": [],
        "forbidden_expressions": [],
        "typical_sentences": [],
    }
    if not isinstance(raw, dict):
        return default
    for k in default:
        if k in raw:
            default[k] = raw[k]
    return default


def _normalize_example_bank(raw: dict) -> dict:
    default = {k: [] for k in INTENT_QUERY_KEYWORDS}
    if not isinstance(raw, dict):
        return default
    for k in default:
        val = raw.get(k, [])
        if isinstance(val, str):
            val = [val] if val else []
        if isinstance(val, list):
            default[k] = [str(x).strip() for x in val if str(x).strip()]
    return default


def invalidate_profile(filename: str, raw: bytes) -> None:
    key = _cache_key(filename, raw)
    TEMPLATE_PROFILE_CACHE.pop(key, None)
    try:
        disk = _disk_path(key)
        if os.path.exists(disk):
            os.remove(disk)
    except Exception:
        pass
