import hashlib
import logging
import os
import threading
from typing import Iterable

try:
    from elasticsearch import Elasticsearch, helpers
except Exception:  # pragma: no cover - optional dependency
    Elasticsearch = None
    helpers = None


logger = logging.getLogger(__name__)


class AuditBasisSearchService:
    def __init__(self):
        self.enabled = bool(os.getenv("REVIEW_ES_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"})
        self.index_name = str(os.getenv("REVIEW_ES_INDEX", "review-audit-basis") or "review-audit-basis").strip()
        self._client = None
        self._client_ready = False
        self._availability_checked = False
        self._unavailable_reason = ""
        self._sync_lock = threading.Lock()
        self._last_sync_signature = ""

    def is_available(self) -> bool:
        if not self.enabled:
            self._unavailable_reason = "disabled"
            return False
        if Elasticsearch is None or helpers is None:
            self._unavailable_reason = "dependency_missing"
            return False
        client = self._get_client()
        return client is not None

    def warmup(self, basis_sections: list[dict] | None = None) -> bool:
        if not self.is_available():
            return False
        if basis_sections:
            self._sync_basis_sections(basis_sections)
        return self._client is not None

    def search(self, query_text: str, basis_sections: list[dict], document_language: str | None = None, limit: int = 4) -> list[dict]:
        query_text = str(query_text or "").strip()
        if not query_text or not basis_sections or limit <= 0:
            return []
        if not self.is_available():
            return []
        client = self._get_client()
        if client is None:
            return []
        self._sync_basis_sections(basis_sections)
        allowed_languages = self._build_allowed_languages(document_language)
        try:
            response = client.search(
                index=self.index_name,
                size=max(1, min(int(limit), 10)),
                query={
                    "function_score": {
                        "query": {
                            "bool": {
                                "must": [
                                    {
                                        "multi_match": {
                                            "query": query_text,
                                            "fields": ["label^4", "text^2", "basis_type^2", "tags^3"],
                                            "type": "best_fields",
                                        }
                                    }
                                ],
                                "filter": [
                                    {"terms": {"language": allowed_languages}},
                                ],
                            }
                        },
                        "score_mode": "sum",
                        "boost_mode": "sum",
                        "functions": [
                            {"field_value_factor": {"field": "priority", "factor": 0.35, "missing": 0}},
                            {"filter": {"term": {"is_checklist": True}}, "weight": 1.8},
                            {"filter": {"term": {"is_summary": True}}, "weight": 0.6},
                            {"filter": {"term": {"is_cyy_example": True}}, "weight": 1.1},
                        ],
                    }
                },
            )
        except Exception as exc:
            logger.warning("审核依据 ES 搜索失败，回退本地匹配: %s", exc)
            return []
        hits = []
        for item in (response.get("hits") or {}).get("hits", []):
            source = item.get("_source") or {}
            section = {
                "label": source.get("label") or "审核依据",
                "text": source.get("text") or "",
                "priority": int(source.get("priority") or 0),
                "language": source.get("language") or "both",
                "basis_type": source.get("basis_type") or "general",
                "es_score": float(item.get("_score") or 0.0),
            }
            if source.get("is_summary"):
                section["is_summary"] = True
            if source.get("is_checklist"):
                section["is_checklist"] = True
            if source.get("is_cyy_example"):
                section["is_cyy_example"] = True
            hits.append(section)
        return hits

    def _get_client(self):
        if self._client_ready:
            return self._client
        self._client_ready = True
        hosts_raw = str(os.getenv("REVIEW_ES_URLS") or os.getenv("REVIEW_ES_URL") or "").strip()
        if not hosts_raw:
            self._unavailable_reason = "missing_url"
            return None
        hosts = [item.strip() for item in hosts_raw.split(",") if item.strip()]
        kwargs = {}
        username = str(os.getenv("REVIEW_ES_USERNAME") or "").strip()
        password = str(os.getenv("REVIEW_ES_PASSWORD") or "").strip()
        api_key = str(os.getenv("REVIEW_ES_API_KEY") or "").strip()
        verify_certs = str(os.getenv("REVIEW_ES_VERIFY_CERTS", "1")).strip().lower() in {"1", "true", "yes", "on"}
        request_timeout = float(os.getenv("REVIEW_ES_TIMEOUT", "2.5") or "2.5")
        if api_key:
            kwargs["api_key"] = api_key
        elif username and password:
            kwargs["basic_auth"] = (username, password)
        kwargs["verify_certs"] = verify_certs
        kwargs["request_timeout"] = request_timeout
        ca_certs = str(os.getenv("REVIEW_ES_CA_CERTS") or "").strip()
        if ca_certs:
            kwargs["ca_certs"] = ca_certs
        try:
            client = Elasticsearch(hosts, **kwargs)
            if not client.ping():
                self._unavailable_reason = "ping_failed"
                return None
            self._client = client
            self._availability_checked = True
            return self._client
        except Exception as exc:
            self._unavailable_reason = str(exc)
            logger.warning("审核依据 ES 客户端初始化失败，将回退本地匹配: %s", exc)
            self._client = None
            return None

    def _sync_basis_sections(self, basis_sections: list[dict]):
        client = self._client
        if client is None or not basis_sections:
            return
        signature = self._build_signature(basis_sections)
        if signature == self._last_sync_signature:
            return
        with self._sync_lock:
            if signature == self._last_sync_signature:
                return
            self._ensure_index(client)
            actions = []
            for section in basis_sections:
                text = str(section.get("text") or "").strip()
                label = str(section.get("label") or "审核依据").strip()
                if not text:
                    continue
                section_id = str(section.get("section_id") or self._section_id(label, text))
                actions.append({
                    "_op_type": "index",
                    "_index": self.index_name,
                    "_id": section_id,
                    "label": label,
                    "text": text,
                    "priority": int(section.get("priority") or 0),
                    "language": str(section.get("language") or "both"),
                    "basis_type": str(section.get("basis_type") or "general"),
                    "tags": list(section.get("tags") or []),
                    "is_summary": bool(section.get("is_summary") or False),
                    "is_checklist": bool(section.get("is_checklist") or False),
                    "is_cyy_example": bool(section.get("is_cyy_example") or False),
                    "signature": signature,
                })
            if not actions:
                self._last_sync_signature = signature
                return
            try:
                helpers.bulk(client, actions, refresh="wait_for")
                self._last_sync_signature = signature
            except Exception as exc:
                logger.warning("审核依据 ES 同步失败，回退本地匹配: %s", exc)

    def _ensure_index(self, client):
        try:
            if client.indices.exists(index=self.index_name):
                return
            client.indices.create(
                index=self.index_name,
                mappings={
                    "properties": {
                        "label": {"type": "text"},
                        "text": {"type": "text"},
                        "priority": {"type": "integer"},
                        "language": {"type": "keyword"},
                        "basis_type": {"type": "keyword"},
                        "tags": {"type": "keyword"},
                        "is_summary": {"type": "boolean"},
                        "is_checklist": {"type": "boolean"},
                        "is_cyy_example": {"type": "boolean"},
                        "signature": {"type": "keyword"},
                    }
                },
            )
        except Exception as exc:
            logger.warning("审核依据 ES 索引创建失败: %s", exc)

    def _build_signature(self, basis_sections: Iterable[dict]) -> str:
        rows = []
        for section in basis_sections:
            rows.append("||".join([
                str(section.get("label") or ""),
                str(section.get("text") or ""),
                str(section.get("priority") or 0),
                str(section.get("language") or "both"),
                str(section.get("basis_type") or "general"),
            ]))
        raw = "\n".join(rows)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def _section_id(self, label: str, text: str) -> str:
        raw = f"{label}||{text[:200]}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def _build_allowed_languages(self, document_language: str | None) -> list[str]:
        language = str(document_language or "both").strip().lower()
        if language == "cn":
            return ["cn", "both"]
        if language == "en":
            return ["en", "both"]
        return ["cn", "en", "both"]


_audit_basis_search_service = AuditBasisSearchService()


def get_audit_basis_search_service() -> AuditBasisSearchService:
    return _audit_basis_search_service
