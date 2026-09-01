import asyncio
import json
from types import SimpleNamespace

from app.api import review as review_api
from app.review_engine.pairing import resolve_input_pairing


def test_pairing_module_and_resolve_callable():
    from app.review_engine import pairing
    assert hasattr(pairing, "resolve_input_pairing")
    assert callable(resolve_input_pairing)


def test_unconfirmed_name_mismatch_does_not_silent_pair():
    docx = SimpleNamespace(id=1, file_type="docx", filename="manual.docx", user_id=3)
    pdf = SimpleNamespace(id=2, file_type="pdf", filename="other.pdf", user_id=3)
    result = resolve_input_pairing(docx, pdf, explicit=False)
    assert result.pairing_status == "unpaired"
    assert result.needs_user_confirm is True


def test_explicit_pairing_confirmed_pairs_even_if_names_differ():
    docx = SimpleNamespace(id=1, file_type="docx", filename="manual.docx", user_id=3)
    pdf = SimpleNamespace(id=2, file_type="pdf", filename="other.pdf", user_id=3)
    result = resolve_input_pairing(docx, pdf, explicit=True)
    assert result.pairing_status == "paired"
    assert result.input_mode == "A"
    assert result.visual_source_file_id == 2


def test_create_review_parses_visual_and_pairing_params(monkeypatch):
    captured = {}

    def fake_get_document(db, document_id=None):
        if document_id == 1:
            return SimpleNamespace(id=1, file_type="docx", filename="G99RS.docx", user_id=8, content="word")
        if document_id == 2:
            return SimpleNamespace(id=2, file_type="pdf", filename="G99RS.pdf", user_id=8, content="pdf")
        return None

    monkeypatch.setattr("app.crud.review.reclaim_stale_running_reviews", lambda *a, **k: None)
    monkeypatch.setattr(review_api, "get_document", fake_get_document)
    monkeypatch.setattr(review_api, "_ensure_document_access", lambda doc, user: doc)
    monkeypatch.setattr(review_api, "_get_active_review_for_document", lambda *a, **k: None)
    monkeypatch.setattr(review_api, "_assert_review_runtime_ready", lambda: None)
    monkeypatch.setattr(review_api, "_find_cached_completed_review", lambda *a, **k: (None, None))
    monkeypatch.setattr(review_api, "_should_reuse_cached_review", lambda *a, **k: False)
    monkeypatch.setattr(review_api, "create_review", lambda db=None, review=None: captured.setdefault("created", SimpleNamespace(id=88, document_id=1)))
    monkeypatch.setattr(review_api, "update_review_status", lambda *a, **k: None)
    monkeypatch.setattr(review_api, "set_progress", lambda *a, **k: None)

    result = asyncio.run(review_api.create_review_task(
        1,
        mode="hybrid",
        visual_document_id=2,
        pairing_confirmed=True,
        db=None,
        current_user=SimpleNamespace(id=8, role="admin"),
    ))
    assert result["status"] == "running"
    assert result["review_id"] == 88
    assert result["pairing_status"] == "paired"
    assert result["visual_document_id"] == 2


def test_missing_visual_document_creates_failed_review(monkeypatch):
    statuses = []

    def fake_get_document(db, document_id=None):
        if document_id == 1:
            return SimpleNamespace(id=1, file_type="docx", filename="a.docx", user_id=1, content="word")
        return None

    monkeypatch.setattr("app.crud.review.reclaim_stale_running_reviews", lambda *a, **k: None)
    monkeypatch.setattr(review_api, "get_document", fake_get_document)
    monkeypatch.setattr(review_api, "_ensure_document_access", lambda doc, user: doc)
    monkeypatch.setattr(review_api, "_get_active_review_for_document", lambda *a, **k: None)
    monkeypatch.setattr(review_api, "_assert_review_runtime_ready", lambda: None)
    monkeypatch.setattr(review_api, "create_review", lambda db=None, review=None: SimpleNamespace(id=77, document_id=1))
    monkeypatch.setattr(review_api, "update_review_status", lambda db, rid, status, total, summary: statuses.append((rid, status, summary)))
    monkeypatch.setattr(review_api, "set_progress", lambda *a, **k: None)

    result = asyncio.run(review_api.create_review_task(
        1,
        mode="hybrid",
        visual_document_id=99,
        pairing_confirmed=True,
        db=None,
        current_user=SimpleNamespace(id=1, role="admin"),
    ))
    assert result["status"] == "failed"
    assert result["error_code"] == "pairing_failed"
    assert statuses[0][0] == 77
    assert statuses[0][1] == "failed"
    payload = json.loads(statuses[0][2])
    assert payload["error_code"] == "pairing_failed"


def test_unconfirmed_mismatch_creates_failed_not_word_only(monkeypatch):
    statuses = []

    def fake_get_document(db, document_id=None):
        if document_id == 1:
            return SimpleNamespace(id=1, file_type="docx", filename="manual.docx", user_id=1, content="word")
        if document_id == 2:
            return SimpleNamespace(id=2, file_type="pdf", filename="other.pdf", user_id=1, content="pdf")
        return None

    monkeypatch.setattr("app.crud.review.reclaim_stale_running_reviews", lambda *a, **k: None)
    monkeypatch.setattr(review_api, "get_document", fake_get_document)
    monkeypatch.setattr(review_api, "_ensure_document_access", lambda doc, user: doc)
    monkeypatch.setattr(review_api, "_get_active_review_for_document", lambda *a, **k: None)
    monkeypatch.setattr(review_api, "_assert_review_runtime_ready", lambda: None)
    monkeypatch.setattr(review_api, "create_review", lambda db=None, review=None: SimpleNamespace(id=70, document_id=1))
    monkeypatch.setattr(review_api, "update_review_status", lambda db, rid, status, total, summary: statuses.append((status, summary)))
    monkeypatch.setattr(review_api, "set_progress", lambda *a, **k: None)

    result = asyncio.run(review_api.create_review_task(
        1,
        mode="hybrid",
        visual_document_id=2,
        pairing_confirmed=False,
        db=None,
        current_user=SimpleNamespace(id=1, role="admin"),
    ))
    assert result["status"] == "failed"
    assert result["error_code"] == "pairing_failed"
    assert statuses[0][0] == "failed"


def test_frontend_create_sends_pairing_params():
    vue = open("/workspace/frontend/src/views/Review.vue", encoding="utf-8").read()
    api = open("/workspace/frontend/src/api/index.js", encoding="utf-8").read()
    assert "visual_document_id: visualDocumentId" in vue
    assert "pairing_confirmed: Boolean(visualDocumentId)" in vue
    assert "params.visual_document_id" in api
    assert "params.pairing_confirmed = true" in api
