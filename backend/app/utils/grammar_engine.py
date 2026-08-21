import hashlib
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx


LT_PUBLIC_CHECK_URL = "https://api.languagetool.org/v2/check"
_LT_CACHE = {}
_LT_CACHE_LOCK = threading.Lock()
_LT_RATE_LIMIT_LOCK = threading.Lock()
_LT_REQUEST_TIMESTAMPS = []


def _env_int(name, default):
    try:
        return int(str(os.getenv(name, default)).strip())
    except (TypeError, ValueError):
        return default


def _env_float(name, default):
    try:
        return float(str(os.getenv(name, default)).strip())
    except (TypeError, ValueError):
        return default


def _get_lt_mode():
    mode = str(os.getenv("LT_MODE", "off") or "off").strip().lower()
    if mode in {"off", "public", "selfhosted"}:
        return mode
    return "off"


def _get_check_url(mode):
    if mode == "public":
        return LT_PUBLIC_CHECK_URL
    if mode != "selfhosted":
        return ""
    base_url = str(os.getenv("LT_BASE_URL", "") or "").strip().rstrip("/")
    if not base_url:
        return ""
    if base_url.endswith("/v2/check"):
        return base_url
    return f"{base_url}/v2/check"


def _get_chunk_size():
    return max(200, _env_int("LT_CHUNK_SIZE", 1800))


def _get_timeout():
    return max(1.0, _env_float("LT_TIMEOUT", 15.0))


def _get_max_workers(mode, chunk_count):
    if chunk_count <= 1:
        return 1
    default_workers = 2 if mode == "public" else 6
    return max(1, min(chunk_count, default_workers))


def _split_sentences(text):
    sentences = []
    for match in re.finditer(r".+?(?:[.!?](?=\s|$)|\n+|$)", text or "", re.S):
        sentence = match.group(0)
        if sentence:
            sentences.append(sentence)
    return sentences


def _chunk_text(text, size):
    chunks = []
    current_parts = []
    current_start = 0
    current_size = 0
    cursor = 0

    def flush_current():
        nonlocal current_parts, current_start, current_size
        if not current_parts:
            return
        chunks.append({"text": "".join(current_parts), "offset": current_start})
        current_parts = []
        current_size = 0

    for sentence in _split_sentences(text):
        sentence_start = text.find(sentence, cursor)
        if sentence_start < 0:
            sentence_start = cursor
        cursor = sentence_start + len(sentence)

        if len(sentence) > size:
            flush_current()
            slice_start = 0
            while slice_start < len(sentence):
                slice_end = min(slice_start + size, len(sentence))
                chunks.append({
                    "text": sentence[slice_start:slice_end],
                    "offset": sentence_start + slice_start,
                })
                slice_start = slice_end
            continue

        if not current_parts:
            current_start = sentence_start

        if current_parts and current_size + len(sentence) > size:
            flush_current()
            current_start = sentence_start

        current_parts.append(sentence)
        current_size += len(sentence)

    flush_current()
    return chunks


def _cache_key(text, lang):
    payload = f"{lang}|{text}".encode("utf-8")
    return hashlib.md5(payload).hexdigest()


def _rate_limit_wait(mode):
    if mode != "public":
        return
    request_limit = max(1, _env_int("LT_RATE_LIMIT", 20))
    while True:
        with _LT_RATE_LIMIT_LOCK:
            now = time.time()
            _LT_REQUEST_TIMESTAMPS[:] = [stamp for stamp in _LT_REQUEST_TIMESTAMPS if now - stamp < 60]
            if len(_LT_REQUEST_TIMESTAMPS) < request_limit:
                _LT_REQUEST_TIMESTAMPS.append(now)
                return
            wait_seconds = max(0.0, 60 - (now - _LT_REQUEST_TIMESTAMPS[0]))
        if wait_seconds > 0:
            time.sleep(wait_seconds)


def _map_match_to_issue(match, text, chunk_offset):
    offset = match.get("offset")
    length = match.get("length")
    if not isinstance(offset, int) or not isinstance(length, int) or offset < 0 or length <= 0:
        return None

    global_start = chunk_offset + offset
    global_end = global_start + length
    matched_text = text[offset:offset + length]
    category_id = str(match.get("rule", {}).get("category", {}).get("id") or "")
    is_typo = category_id.upper() == "TYPOS"
    replacements = match.get("replacements") or []
    suggestion = ""
    if replacements:
        suggestion = str(replacements[0].get("value") or "").strip()

    return {
        "severity": "error" if category_id.upper() in {"TYPOS", "GRAMMAR"} else "warning",
        "category": "grammar",
        "source": "spellcheck" if is_typo else "languagetool",
        "original_text": matched_text,
        "context": text[max(0, offset - 50):min(len(text), offset + length + 50)],
        "description": str(match.get("message") or "LanguageTool 检测到潜在语法问题"),
        "suggestion": suggestion,
        "position": f"{global_start}-{global_end}",
        "_word": matched_text,
    }


def _lt_check_chunk(text, lang, chunk_offset, check_url, mode):
    key = _cache_key(text, lang)
    with _LT_CACHE_LOCK:
        cached_matches = _LT_CACHE.get(key)

    if cached_matches is None:
        _rate_limit_wait(mode)
        response = httpx.post(
            check_url,
            data={"text": text, "language": lang},
            timeout=_get_timeout(),
        )
        response.raise_for_status()
        data = response.json() or {}
        cached_matches = data.get("matches") or []
        with _LT_CACHE_LOCK:
            _LT_CACHE[key] = cached_matches

    issues = []
    for match in cached_matches:
        issue = _map_match_to_issue(match, text, chunk_offset)
        if issue is not None:
            issues.append(issue)
    return issues


def _post_filter_whitelist(issues, exact_whitelist):
    if not exact_whitelist:
        return issues
    filtered = []
    for issue in issues:
        if issue.get("_word") in exact_whitelist:
            continue
        filtered.append(issue)
    return filtered


def check_grammar_with_languagetool(text, lang="en-US", exact_whitelist=None):
    mode = _get_lt_mode()
    if mode == "off" or not str(text or "").strip():
        return []

    check_url = _get_check_url(mode)
    if not check_url:
        return []

    chunks = _chunk_text(text, _get_chunk_size())
    if not chunks:
        return []

    issues = []
    try:
        max_workers = _get_max_workers(mode, len(chunks))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(_lt_check_chunk, chunk["text"], lang, chunk["offset"], check_url, mode): chunk
                for chunk in chunks
            }
            for future in as_completed(future_map):
                try:
                    issues.extend(future.result())
                except Exception:
                    continue
    except Exception:
        return []

    return _post_filter_whitelist(issues, set(exact_whitelist or set()))
