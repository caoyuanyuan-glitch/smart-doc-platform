import os
import re
from typing import Dict, List, Optional

import httpx

OFFICIAL_BASE = "https://www.mgi-tech.com"
SEARCH_URL = f"{OFFICIAL_BASE}/index/index/manualSeaList"
OFFICIAL_HEADERS = {
    "User-Agent": "Mozilla/5.0 SmartDocManualQA",
    "Origin": OFFICIAL_BASE,
    "Referer": f"{OFFICIAL_BASE}/manual",
    "Content-Type": "application/json",
}
MAX_PDF_BYTES = 80 * 1024 * 1024

CATALOG_RE = re.compile(r"\b\d{3}-\d{6}-\d{2}\b")
FCODE_RE = re.compile(r"\bH-\d{3}-\d{6}-\d{2}\b", re.I)
MODEL_RE = re.compile(
    r"DNBSEQ[- ]?[A-Z0-9]+\+?"
    r"|MGISP[- ]?\d+"
    r"|OmicsNest(?:\s*Lite)?"
    r"|DNBelab[- ]?[A-Z0-9]+"
    r"|PrepALL"
    r"|AlphaTool"
    r"|FLP-L\d*"
    r"|SP[- ]?(?:NE)?\d+"
    r"|T\d+\+"
    r"|G\d+(?:-FR|-ER)?"
    r"|E25",
    re.I,
)
FLEX_MODEL_RE = re.compile(r"\b[A-Za-z]{2,}(?:[\s\-_]*\d+)[A-Za-z0-9+\-]*")


def compact_key(text: str) -> str:
    return re.sub(r"[^a-z0-9+]+", "", (text or "").lower())


def keyword_variants(keyword: str) -> List[str]:
    raw = " ".join((keyword or "").split())
    if not raw:
        return []
    variants: List[str] = []

    def add(value: str) -> None:
        value = " ".join((value or "").split())
        if value and value.lower() not in {item.lower() for item in variants}:
            variants.append(value)

    hyphenated = re.sub(r"[\s_]+", "-", raw)
    letter_digit = re.sub(r"([A-Za-z])[\s_\-]*(\d)", r"\1-\2", raw)
    compact = re.sub(r"[\s\-_]+", "", raw)
    if re.search(r"[\s_]", raw):
        add(hyphenated)
        add(letter_digit)
        add(raw)
        add(compact)
    else:
        add(raw)
        add(letter_digit)
        add(hyphenated)
        add(compact)
    return variants


def fuzzy_text_hit(keyword: str, text: str) -> bool:
    kw = (keyword or "").strip()
    hay = text or ""
    if not kw or not hay:
        return False
    if kw.lower() in hay.lower():
        return True
    compact_kw = compact_key(kw)
    compact_hay = compact_key(hay)
    if compact_kw and compact_kw in compact_hay:
        return True
    tokens = [compact_key(part) for part in re.split(r"[\s\-_]+", kw) if compact_key(part)]
    return bool(tokens) and all(token in compact_hay for token in tokens)


def detect_question_lang(text: str) -> str:
    cn = sum(1 for ch in text or "" if "\u4e00" <= ch <= "\u9fff")
    return "zh" if cn >= 2 else "en"


def title_lang(title: str) -> str:
    t = title or ""
    if "_English_" in t or " User Manual" in t or t.endswith("_English"):
        return "en"
    if "_中文_" in t or "中文" in t:
        return "zh"
    return "unknown"


def extract_search_keyword(question: str, product: str = "") -> str:
    product = (product or "").strip()
    if product:
        return product
    q = (question or "").strip()
    fcodes = FCODE_RE.findall(q)
    if fcodes:
        return fcodes[0]
    arts = CATALOG_RE.findall(q)
    if arts:
        return arts[0]
    models = MODEL_RE.findall(q)
    if models:
        return models[0].strip()
    flex = FLEX_MODEL_RE.findall(q)
    if flex:
        return max(flex, key=len).strip()
    ascii_tokens = re.findall(r"[A-Za-z][A-Za-z0-9+\-]{2,}", q)
    if ascii_tokens:
        return max(ascii_tokens, key=len)
    return q[:40]


def _is_quick_guide(title: str) -> bool:
    t = title or ""
    return "快速" in t or "Quick" in t


def _is_full_manual(title: str) -> bool:
    t = title or ""
    return any(token in t for token in ("系统操作指南", "User Manual", "产品说明书", "使用说明书"))


def _wants_quick(question: str) -> bool:
    q = question or ""
    return "快速" in q or "quick" in q.lower()


def score_manual(item: dict, question: str, keyword: str, lang: str) -> float:
    title = item.get("title") or ""
    score = 0.0
    tl = title_lang(title)
    if lang == "zh" and tl == "en":
        score -= 40
    elif lang == "en" and tl == "zh":
        score -= 40
    elif lang == tl:
        score += 15

    quick = _is_quick_guide(title)
    if quick and not _wants_quick(question):
        score -= 20
    elif quick and _wants_quick(question):
        score += 18
    if _is_full_manual(title) and not quick:
        score += 12

    kw = (keyword or "").strip()
    if kw and fuzzy_text_hit(kw, title):
        score += 20
    artno = item.get("artno") or ""
    if kw and (kw in artno or fuzzy_text_hit(kw, artno)):
        score += 16

    try:
        score += min(int(item.get("updatetime") or 0), 10**12) / 10**12
    except (TypeError, ValueError):
        pass
    return score


def dedup_latest_by_fcode(items: List[dict]) -> List[dict]:
    best: Dict[str, dict] = {}
    leftovers = []
    for item in items:
        fcode = (item.get("fcode") or "").strip()
        if not fcode:
            leftovers.append(item)
            continue
        prev = best.get(fcode)
        if prev is None:
            best[fcode] = item
            continue
        prev_ts = int(prev.get("updatetime") or 0)
        cur_ts = int(item.get("updatetime") or 0)
        if cur_ts >= prev_ts:
            best[fcode] = item
    return list(best.values()) + leftovers


def rank_manuals(items: List[dict], question: str, keyword: str) -> List[dict]:
    lang = detect_question_lang(question)
    ranked = []
    for item in dedup_latest_by_fcode(items):
        row = dict(item)
        row["_score"] = score_manual(item, question, keyword, lang)
        ranked.append(row)
    ranked.sort(key=lambda x: x["_score"], reverse=True)
    return ranked


def select_manuals(ranked: List[dict], question: str, max_count: int = 1) -> List[dict]:
    if not ranked:
        return []
    selected = [ranked[0]]
    wants_multi = any(token in (question or "") for token in ("和", "以及", "与", " and "))
    if wants_multi and max_count > 1 and len(ranked) > 1:
        first_code = ranked[0].get("fcode")
        for item in ranked[1:]:
            if item.get("fcode") != first_code and item.get("_score", 0) >= ranked[0].get("_score", 0) * 0.85:
                selected.append(item)
                break
    return selected[:max_count]


def should_strict_filter(keyword: str) -> bool:
    return len(compact_key(keyword)) >= 3


def matches_keyword(item: dict, keyword: str) -> bool:
    return any(
        fuzzy_text_hit(keyword, item.get(field) or "")
        for field in ("title", "artno", "fcode")
    )


def filter_manuals_by_keyword(items: List[dict], keyword: str) -> List[dict]:
    if not should_strict_filter(keyword):
        return list(items)
    return [item for item in items if matches_keyword(item, keyword)]


def family_key(item: dict, keyword: str = "") -> str:
    artnos = re.split(r"[、,;/]+", item.get("artno") or "")
    arts = [compact_key(part) for part in artnos if compact_key(part)]
    if arts:
        return "art:" + min(arts)
    title = item.get("title") or ""
    tokens = [compact_key(tok) for tok in re.findall(r"[A-Za-z]{2,}[A-Za-z0-9+\-]*", title)]
    kwc = compact_key(keyword)
    for token in tokens:
        if kwc and kwc in token:
            return "m:" + token
    if tokens:
        return "m:" + tokens[0]
    return "t:" + compact_key(title)[:24]


def needs_user_choice(items: List[dict], keyword: str = "") -> bool:
    if len(items) <= 1:
        return False
    return len({family_key(item, keyword) for item in items}) > 1


def public_item(item: dict) -> dict:
    download = item.get("downloadurl") or "/manual"
    if not str(download).startswith("http"):
        download = OFFICIAL_BASE + download
    return {
        "official_id": item.get("id") or item.get("official_id"),
        "title": item.get("title") or "",
        "fcode": item.get("fcode") or "",
        "docuversion": item.get("docuversion") or "",
        "softversion": item.get("softversion") or "",
        "size": item.get("size") or "",
        "create_time": item.get("create_time") or "",
        "pline": item.get("pline") or "",
        "artno": item.get("artno") or "",
        "files": item.get("files") or "",
        "updatetime": item.get("updatetime") or 0,
        "official_url": download,
        "score": round(float(item.get("_score") or 0), 3),
    }


def search_official_manuals(keyword: str, limit: int = 10, client: Optional[httpx.Client] = None) -> List[dict]:
    keyword = (keyword or "").strip()
    if not keyword:
        return []
    own_client = client is None
    http = client or httpx.Client(timeout=20.0, follow_redirects=True)
    try:
        merged: List[dict] = []
        seen = set()
        for kw in keyword_variants(keyword):
            payload = {
                "page": 1,
                "limit": limit,
                "keyword": kw,
                "type": "",
                "style": "",
                "title": "",
                "ref": "",
                "pn": "",
            }
            resp = http.post(SEARCH_URL, json=payload, headers=OFFICIAL_HEADERS)
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, dict) or data.get("status") != 1:
                continue
            rows = ((data.get("data") or {}).get("data")) or []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                oid = row.get("id")
                if oid in seen:
                    continue
                seen.add(oid)
                merged.append(row)
            if merged:
                break
    finally:
        if own_client:
            http.close()
    return merged[:limit]


def download_official_pdf(files_path: str, dest_path: str, client: Optional[httpx.Client] = None) -> None:
    rel = (files_path or "").strip()
    if not rel:
        raise ValueError("missing pdf path")
    url = rel if rel.startswith("http") else OFFICIAL_BASE + rel
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    tmp_path = dest_path + ".part"
    own_client = client is None
    http = client or httpx.Client(timeout=120.0, follow_redirects=True)
    try:
        with http.stream("GET", url, headers=OFFICIAL_HEADERS) as resp:
            resp.raise_for_status()
            written = 0
            with open(tmp_path, "wb") as fh:
                for chunk in resp.iter_bytes(65536):
                    written += len(chunk)
                    if written > MAX_PDF_BYTES:
                        raise ValueError("pdf too large")
                    fh.write(chunk)
        os.replace(tmp_path, dest_path)
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise
    finally:
        if own_client:
            http.close()


def cache_file_id(item: dict) -> str:
    oid = item.get("id") or item.get("official_id") or "0"
    stamp = item.get("updatetime") or item.get("create_time") or "0"
    return f"off_{oid}_{stamp}"


def pick_from_candidates(candidates: List[dict], official_ids: List[int]) -> List[dict]:
    wanted = {int(i) for i in official_ids}
    picked = []
    for item in candidates:
        oid = item.get("id") or item.get("official_id")
        try:
            oid = int(oid)
        except (TypeError, ValueError):
            continue
        if oid in wanted:
            picked.append(item)
    return picked
