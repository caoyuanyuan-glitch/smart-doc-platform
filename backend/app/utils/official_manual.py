import os
import re
import json
import shutil
import hashlib
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import httpx
import requests
from requests.adapters import HTTPAdapter

from app.utils.runtime_paths import runtime_root

OFFICIAL_BASE = "https://www.mgi-tech.com"
SEARCH_URL = f"{OFFICIAL_BASE}/index/index/manualSeaList"
ZH_LIBRARY_URL = "https://mgi-tech.com/manual"
OFFICIAL_HEADERS = {
    "User-Agent": "Mozilla/5.0 SmartDocManualQA",
    "Origin": OFFICIAL_BASE,
    "Referer": ZH_LIBRARY_URL,
    "Content-Type": "application/json",
}
EN_OFFICIAL_BASE = "https://global-mgitech.com"
EN_LIBRARY_URL = f"{EN_OFFICIAL_BASE}/resources/manual-library/"
EN_SEARCH_URL = f"{EN_OFFICIAL_BASE}/wp-json/cua/v1/search"
EN_OFFICIAL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": EN_LIBRARY_URL,
    "Accept": "application/json",
}
EN_DOWNLOAD_HEADERS = {
    "User-Agent": EN_OFFICIAL_HEADERS["User-Agent"],
    "Referer": EN_LIBRARY_URL,
    "Accept": "application/pdf,application/octet-stream,*/*",
}
MAX_PDF_BYTES = 80 * 1024 * 1024

logger = logging.getLogger(__name__)

_EN_SESSION = None


def _english_session():
    global _EN_SESSION
    if _EN_SESSION is None:
        sess = requests.Session()
        sess.headers.update({
            "User-Agent": EN_OFFICIAL_HEADERS["User-Agent"],
        })
        adapter = HTTPAdapter(pool_connections=4, pool_maxsize=4, max_retries=0)
        sess.mount("https://", adapter)
        sess.mount("http://", adapter)
        _EN_SESSION = sess
    return _EN_SESSION


def _reset_english_session():
    global _EN_SESSION
    sess = _EN_SESSION
    _EN_SESSION = None
    if sess is not None:
        try:
            sess.close()
        except Exception:
            pass


class OfficialSearchError(Exception):
    def __init__(self, site: str, library_url: str, message: str = ""):
        self.site = site
        self.library_url = library_url
        super().__init__(message or f"cannot open {library_url}")


def _requests_call(method: str, url: str, *, retries: int = 3, timeout: float = 30.0, stream: bool = False, **kwargs):
    last_err = None
    for attempt in range(retries):
        try:
            resp = _english_session().request(method, url, timeout=timeout, stream=stream, **kwargs)
            resp.raise_for_status()
            return resp
        except Exception as exc:
            last_err = exc
            _reset_english_session()
            logger.warning("official %s %s attempt %s failed: %s", method, url, attempt + 1, exc)
            time.sleep(0.5 * (attempt + 1))
    raise last_err

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


def normalize_site(site: str) -> str:
    s = (site or "").strip().lower()
    if s in {"en", "english", "global", "en-us", "en_us"}:
        return "en"
    return "zh"


def official_site(site: str = "zh") -> dict:
    if normalize_site(site) == "en":
        return {
            "site": "en",
            "base": EN_OFFICIAL_BASE,
            "library_url": EN_LIBRARY_URL,
            "search_url": EN_SEARCH_URL,
            "headers": EN_OFFICIAL_HEADERS,
            "kind": "en_wp",
        }
    return {
        "site": "zh",
        "base": OFFICIAL_BASE,
        "library_url": ZH_LIBRARY_URL,
        "search_url": SEARCH_URL,
        "headers": OFFICIAL_HEADERS,
        "kind": "cn_api",
    }


def _effdate_ts(value) -> int:
    if value is None or value == "":
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        pass
    text = str(value).strip()[:10]
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return int(datetime.strptime(text, fmt).timestamp())
        except ValueError:
            continue
    return 0


def normalize_official_item(item: dict, site: str = "zh") -> dict:
    row = dict(item or {})
    if normalize_site(site) != "en":
        return row
    title = row.get("cua_title") or row.get("title") or ""
    fcode = row.get("cua_fcode") or row.get("fcode") or ""
    file_url = row.get("file_url") or row.get("url") or row.get("files") or ""
    eff = row.get("cua_effdate") or row.get("create_time") or ""
    row.update({
        "title": title,
        "fcode": fcode,
        "docuversion": row.get("cua_docuver") or row.get("docuversion") or "",
        "softversion": row.get("cua_softversion") or row.get("softversion") or "",
        "create_time": eff,
        "pline": row.get("cua_pline") or row.get("pline") or "",
        "artno": row.get("artno") or "",
        "files": file_url,
        "downloadurl": file_url,
        "updatetime": row.get("updatetime") or _effdate_ts(eff),
    })
    return row


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
    if "_English_" in t or " User Manual" in t or t.endswith("_English") or "System Guide" in t:
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


def extract_search_keywords(question: str, product: str = "") -> List[str]:
    product = (product or "").strip()
    if product:
        parts = [p.strip() for p in re.split(r"[,，、;/|]+", product) if p.strip()]
        if len(parts) == 1:
            maybe = [p.strip() for p in re.split(r"\s+", parts[0]) if p.strip()]
            if len(maybe) >= 2 and all(re.search(r"[A-Za-z0-9]", p) and not re.search(r"[\u4e00-\u9fff]", p) for p in maybe):
                parts = maybe
        return parts or [product]
    models = [m.strip() for m in MODEL_RE.findall(question or "") if m.strip()]
    uniq: List[str] = []
    seen = set()
    for model in models:
        key = compact_key(model)
        if key and key not in seen:
            seen.add(key)
            uniq.append(model)
    if len(uniq) >= 2:
        return uniq
    single = extract_search_keyword(question, "")
    return [single] if single else []


def _is_quick_guide(title: str) -> bool:
    t = title or ""
    return "快速" in t or "Quick" in t


def _is_full_manual(title: str) -> bool:
    t = title or ""
    return any(token in t for token in ("系统操作指南", "User Manual", "产品说明书", "使用说明书", "System Guide"))


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


def rank_manuals(items: List[dict], question: str, keyword: str, lang: Optional[str] = None) -> List[dict]:
    lang = lang or detect_question_lang(question)
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


def filter_manuals_by_keywords(items: List[dict], keywords: List[str]) -> List[dict]:
    keywords = [k.strip() for k in (keywords or []) if (k or "").strip()]
    if not keywords:
        return list(items)
    if not any(should_strict_filter(kw) for kw in keywords):
        return list(items)
    return [item for item in items if any(matches_keyword(item, kw) for kw in keywords)]


def filter_manuals_by_lang(items: List[dict], lang: str) -> List[dict]:
    want = normalize_site(lang)
    kept = []
    for item in items:
        tl = title_lang(item.get("title") or "")
        if tl == want or tl == "unknown":
            kept.append(item)
    return kept


def rank_manuals_for_keywords(
    items: List[dict],
    question: str,
    keywords: List[str],
    lang: Optional[str] = None,
) -> List[dict]:
    keywords = [k.strip() for k in (keywords or []) if (k or "").strip()]
    if not keywords:
        return rank_manuals(items, question, "", lang=lang)
    best: Dict[object, dict] = {}
    for kw in keywords:
        for row in rank_manuals(items, question, kw, lang=lang):
            oid = row.get("id") or row.get("official_id")
            prev = best.get(oid)
            if prev is None or float(row.get("_score") or 0) > float(prev.get("_score") or 0):
                best[oid] = row
    ranked = list(best.values())
    ranked.sort(key=lambda x: x.get("_score") or 0, reverse=True)
    return ranked


def select_manuals_for_keywords(
    ranked: List[dict],
    question: str,
    keywords: List[str],
    max_per_keyword: int = 1,
) -> List[dict]:
    keywords = [k.strip() for k in (keywords or []) if (k or "").strip()]
    if len(keywords) <= 1:
        return select_manuals(ranked, question, max_count=1)
    selected = []
    seen = set()
    for kw in keywords:
        matched = [item for item in ranked if matches_keyword(item, kw)]
        picked = select_manuals(matched or ranked, question, max_count=max_per_keyword)
        for item in picked:
            oid = item.get("id") or item.get("official_id")
            if oid in seen:
                continue
            seen.add(oid)
            selected.append(item)
    return selected


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


def needs_user_choice_for_keywords(items: List[dict], keywords: List[str]) -> bool:
    keywords = [k.strip() for k in (keywords or []) if (k or "").strip()]
    if len(keywords) <= 1:
        return needs_user_choice(items, keywords[0] if keywords else "")
    return False


def public_item(item: dict) -> dict:
    download = item.get("downloadurl") or "/manual"
    if not str(download).startswith("http"):
        files = str(item.get("files") or "")
        site = "en" if "global-mgitech.com" in files else "zh"
        cfg = official_site(site)
        download = cfg["base"] + download
    else:
        site = "en" if "global-mgitech.com" in str(download) else "zh"
        cfg = official_site(site)
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
        "library_url": cfg["library_url"],
        "score": round(float(item.get("_score") or 0), 3),
        "cached": bool(item.get("_cached")),
    }


def _en_cache_dir() -> Path:
    path = runtime_root() / "manual-cache" / "en"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _en_search_cache_path(keyword: str) -> Path:
    digest = hashlib.sha1(compact_key(keyword).encode("utf-8")).hexdigest()
    return _en_cache_dir() / f"search-{digest}.json"


def _read_en_search_cache(keyword: str) -> List[dict]:
    path = _en_search_cache_path(keyword)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    items = data.get("items") if isinstance(data, dict) else None
    return items if isinstance(items, list) else []


def _write_en_search_cache(keyword: str, items: List[dict]) -> None:
    if not items:
        return
    path = _en_search_cache_path(keyword)
    payload = {"keyword": keyword, "cached_at": int(time.time()), "items": items}
    tmp_path = path.with_name(path.name + ".tmp")
    try:
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp_path, path)
    except OSError as exc:
        logger.warning("en search cache write failed: %s", exc)
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def _read_en_search_cache_fuzzy(keyword: str) -> List[dict]:
    target = compact_key(keyword)
    if not target:
        return []
    best_items: List[dict] = []
    best_overlap = 0
    for path in _en_cache_dir().glob("search-*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        stored = compact_key(data.get("keyword") or "") if isinstance(data, dict) else ""
        if not stored:
            continue
        if stored in target or target in stored:
            overlap = len(stored)
            items = data.get("items")
            if isinstance(items, list) and overlap > best_overlap:
                best_overlap = overlap
                best_items = items
    return best_items


def _en_pdf_cache_path(url: str) -> Path:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
    path = _en_cache_dir() / "pdf"
    path.mkdir(parents=True, exist_ok=True)
    return path / f"{digest}.pdf"


def _cache_en_pdf(url: str, source_path: str) -> None:
    try:
        shutil.copy2(source_path, _en_pdf_cache_path(url))
    except OSError as exc:
        logger.warning("en pdf cache write failed: %s", exc)


def _restore_cached_en_pdf(url: str, dest_path: str) -> bool:
    cached = _en_pdf_cache_path(url)
    if not cached.exists():
        return False
    try:
        shutil.copy2(cached, dest_path)
        logger.warning("en pdf download failed, restored cached copy: %s", url)
        return True
    except OSError as exc:
        logger.warning("en pdf cache restore failed: %s", exc)
        return False


def has_cached_en_pdf(url: str) -> bool:
    return bool(url) and _en_pdf_cache_path(url).exists()


def _fetch_official_rows(http, cfg: dict, keyword: str, limit: int) -> List[dict]:
    try:
        if cfg.get("kind") == "en_wp":
            params = {"q": keyword, "per_page": str(limit), "page": "1"}
            if http is None:
                resp = _requests_call(
                    "GET",
                    cfg["search_url"],
                    params=params,
                    headers=cfg["headers"],
                    timeout=20,
                )
            else:
                resp = http.get(cfg["search_url"], params=params, headers=cfg["headers"])
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, dict) or int(data.get("status") or 0) != 1:
                return []
            rows = data.get("items") or []
            return [row for row in rows if isinstance(row, dict)]
        payload = {
            "page": 1,
            "limit": limit,
            "keyword": keyword,
            "type": "",
            "style": "",
            "title": "",
            "ref": "",
            "pn": "",
        }
        resp = http.post(cfg["search_url"], json=payload, headers=cfg["headers"])
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict) or data.get("status") != 1:
            return []
        rows = ((data.get("data") or {}).get("data")) or []
        return [row for row in rows if isinstance(row, dict)]
    except OfficialSearchError:
        raise
    except Exception as exc:
        raise OfficialSearchError(cfg.get("site") or "zh", cfg.get("library_url") or "", str(exc)) from exc


def search_official_manuals(
    keyword: str,
    limit: int = 10,
    client: Optional[httpx.Client] = None,
    site: str = "zh",
) -> List[dict]:
    keyword = (keyword or "").strip()
    if not keyword:
        return []
    cfg = official_site(site)
    is_en = cfg.get("kind") == "en_wp"
    created_http = False
    http = client
    if http is None and cfg.get("kind") != "en_wp":
        http = httpx.Client(timeout=20.0, follow_redirects=True)
        created_http = True
    try:
        merged: List[dict] = []
        seen = set()
        last_err = None
        for kw in keyword_variants(keyword):
            try:
                rows = _fetch_official_rows(http, cfg, kw, limit)
            except OfficialSearchError as exc:
                last_err = exc
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                oid = row.get("id")
                if oid in seen:
                    continue
                seen.add(oid)
                merged.append(normalize_official_item(row, cfg["site"]))
            if merged:
                break
        if not merged and last_err:
            if is_en:
                cached = _read_en_search_cache(keyword) or _read_en_search_cache_fuzzy(keyword)
                if cached:
                    logger.warning(
                        "en search %s failed, using cached %s items: %s",
                        keyword, len(cached), last_err,
                    )
                    return [{**item, "_cached": True} for item in cached][:limit]
            raise last_err
        if is_en and merged:
            _write_en_search_cache(keyword, merged[:limit])
    finally:
        if created_http:
            http.close()
    return merged[:limit]


def search_official_manuals_for_keywords(
    keywords: List[str],
    limit: int = 10,
    client: Optional[httpx.Client] = None,
    site: str = "zh",
) -> List[dict]:
    keywords = [k.strip() for k in (keywords or []) if (k or "").strip()]
    if not keywords:
        return []
    created_http = False
    http = client
    if http is None and normalize_site(site) != "en":
        http = httpx.Client(timeout=20.0, follow_redirects=True)
        created_http = True
    try:
        merged: List[dict] = []
        seen = set()
        for kw in keywords:
            for row in search_official_manuals(kw, limit=limit, client=http, site=site):
                oid = row.get("id")
                if oid in seen:
                    continue
                seen.add(oid)
                merged.append(row)
        cap = max(limit, limit * len(keywords))
        return merged[:cap]
    finally:
        if created_http:
            http.close()


def download_official_pdf(files_path: str, dest_path: str, client: Optional[httpx.Client] = None) -> None:
    rel = (files_path or "").strip()
    if not rel:
        raise ValueError("missing pdf path")
    url = rel if rel.startswith("http") else OFFICIAL_BASE + rel
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    tmp_path = dest_path + ".part"
    if client is None and "global-mgitech.com" in url:
        last_err = None
        for attempt in range(3):
            try:
                resp = _requests_call(
                    "GET",
                    url,
                    headers=EN_DOWNLOAD_HEADERS,
                    timeout=120,
                    stream=True,
                    retries=1,
                )
                written = 0
                with open(tmp_path, "wb") as fh:
                    for chunk in resp.iter_content(65536):
                        if not chunk:
                            continue
                        written += len(chunk)
                        if written > MAX_PDF_BYTES:
                            raise ValueError("pdf too large")
                        fh.write(chunk)
                resp.close()
                os.replace(tmp_path, dest_path)
                _cache_en_pdf(url, dest_path)
                return
            except Exception as exc:
                last_err = exc
                logger.warning("en pdf download attempt %s failed: %s", attempt + 1, exc)
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
                time.sleep(0.6 * (attempt + 1))
        if _restore_cached_en_pdf(url, dest_path):
            return
        raise last_err
    headers = EN_DOWNLOAD_HEADERS if "global-mgitech.com" in url else OFFICIAL_HEADERS
    own_client = client is None
    http = client or httpx.Client(timeout=120.0, follow_redirects=True)
    try:
        with http.stream("GET", url, headers=headers) as resp:
            resp.raise_for_status()
            written = 0
            with open(tmp_path, "wb") as fh:
                for chunk in resp.iter_bytes(65536):
                    written += len(chunk)
                    if written > MAX_PDF_BYTES:
                        raise ValueError("pdf too large")
                    fh.write(chunk)
        os.replace(tmp_path, dest_path)
        if "global-mgitech.com" in url:
            _cache_en_pdf(url, dest_path)
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        if "global-mgitech.com" in url and _restore_cached_en_pdf(url, dest_path):
            return
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
