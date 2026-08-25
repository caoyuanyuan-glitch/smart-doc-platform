from app.services import audit_basis_search as search_module


class _FakeIndices:
    def __init__(self):
        self.exists_calls = []
        self.create_calls = []
        self._exists = False

    def exists(self, index):
        self.exists_calls.append(index)
        return self._exists

    def create(self, index, mappings):
        self.create_calls.append((index, mappings))
        self._exists = True


class _FakeClient:
    def __init__(self, hosts, **kwargs):
        self.hosts = hosts
        self.kwargs = kwargs
        self.indices = _FakeIndices()
        self.search_calls = []
        self.ping_calls = 0
        self.search_response = {"hits": {"hits": []}}

    def ping(self):
        self.ping_calls += 1
        return True

    def search(self, **kwargs):
        self.search_calls.append(kwargs)
        return self.search_response


def test_search_service_returns_empty_when_disabled(monkeypatch):
    monkeypatch.setenv("REVIEW_ES_ENABLED", "0")
    service = search_module.AuditBasisSearchService()

    result = service.search("版本记录", [{"label": "A", "text": "B"}], document_language="cn")

    assert result == []
    assert service.is_available() is False


def test_search_service_warmup_syncs_basis_sections_once(monkeypatch):
    fake_client = _FakeClient(["http://localhost:9200"])
    bulk_calls = []

    monkeypatch.setenv("REVIEW_ES_ENABLED", "1")
    monkeypatch.setenv("REVIEW_ES_URL", "http://localhost:9200")
    monkeypatch.setattr(search_module, "Elasticsearch", lambda hosts, **kwargs: fake_client)
    monkeypatch.setattr(
        search_module,
        "helpers",
        type("Helpers", (), {"bulk": staticmethod(lambda client, actions, refresh=None: bulk_calls.append((client, actions, refresh)))})(),
    )

    service = search_module.AuditBasisSearchService()
    sections = [
        {
            "label": "说明书发布前自检 Checklist",
            "text": "检查版本记录与引用完整性。",
            "priority": 5,
            "language": "both",
            "basis_type": "checklist",
            "tags": ["checklist"],
            "is_checklist": True,
        }
    ]

    assert service.warmup(sections) is True
    assert service.warmup(sections) is True
    assert fake_client.indices.exists_calls == ["review-audit-basis"]
    assert len(fake_client.indices.create_calls) == 1
    assert len(bulk_calls) == 1
    assert bulk_calls[0][2] == "wait_for"
    assert bulk_calls[0][1][0]["label"] == "说明书发布前自检 Checklist"


def test_search_service_search_builds_language_filter_and_maps_hits(monkeypatch):
    fake_client = _FakeClient(["http://localhost:9200"])
    fake_client.search_response = {
        "hits": {
            "hits": [
                {
                    "_score": 8.5,
                    "_source": {
                        "label": "技术文档常见错误清单",
                        "text": "避免术语不一致。",
                        "priority": 3,
                        "language": "both",
                        "basis_type": "common_errors",
                        "is_summary": False,
                        "is_checklist": False,
                        "is_cyy_example": True,
                    },
                }
            ]
        }
    }

    monkeypatch.setenv("REVIEW_ES_ENABLED", "1")
    monkeypatch.setenv("REVIEW_ES_URL", "http://localhost:9200")
    monkeypatch.setattr(search_module, "Elasticsearch", lambda hosts, **kwargs: fake_client)
    monkeypatch.setattr(
        search_module,
        "helpers",
        type("Helpers", (), {"bulk": staticmethod(lambda client, actions, refresh=None: None)})(),
    )

    service = search_module.AuditBasisSearchService()
    result = service.search(
        "术语不一致",
        [{"label": "技术文档常见错误清单", "text": "避免术语不一致。", "language": "both"}],
        document_language="cn",
        limit=2,
    )

    assert len(result) == 1
    assert result[0]["label"] == "技术文档常见错误清单"
    assert result[0]["es_score"] == 8.5
    assert result[0]["is_cyy_example"] is True
    query = fake_client.search_calls[0]["query"]["function_score"]
    assert query["query"]["bool"]["filter"] == [{"terms": {"language": ["cn", "both"]}}]
    assert query["query"]["bool"]["must"][0]["multi_match"]["fields"] == ["label^4", "text^2", "basis_type^2", "tags^3"]
    assert query["functions"][0]["field_value_factor"] == {"field": "priority", "factor": 0.35, "missing": 0}
    assert {item["weight"] for item in query["functions"][1:]} == {1.8, 0.6, 1.1}
