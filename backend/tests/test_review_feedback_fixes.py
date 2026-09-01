import asyncio
import inspect
import time
from pathlib import Path
from types import SimpleNamespace

from app.api import review as review_api
from app.review_engine.bounded_cache import BoundedTTLCache
from app.review_engine.task_state import clear_task_state
from app.review_engine.versions import PROMPT_VERSION


def _patch_list_reviews(monkeypatch, reviews, total=None, query_capture=None):
    def fake_query(db, document_id=None, status=None, latest_only=False, limit=100, skip=0):
        if query_capture is not None:
            query_capture.update({
                "document_id": document_id,
                "status": status,
                "latest_only": latest_only,
                "limit": limit,
                "skip": skip,
            })
        return reviews

    monkeypatch.setattr(review_api, "_query_review_rows", fake_query)
    monkeypatch.setattr(review_api, "_count_review_rows", lambda *a, **k: total if total is not None else len(reviews))
    monkeypatch.setattr(review_api, "_reconcile_review_runtime_state", lambda db, review: review)
    monkeypatch.setattr(review_api, "get_progress", lambda review_id: {"status": "running", "step": "视觉复核", "progress": 70, "message": "处理中"})
    monkeypatch.setattr(
        review_api,
        "get_documents_by_ids",
        lambda db, document_ids: [SimpleNamespace(id=1, filename="manual.docx", file_type="docx")],
    )


def test_history_list_includes_all_statuses(monkeypatch):
    reviews = [
        SimpleNamespace(id=1, document_id=1, status="completed", summary="{}", total_issues=3),
        SimpleNamespace(id=2, document_id=1, status="failed", summary='{"error_code":"pairing_failed","error_detail":"visual missing"}', total_issues=0),
        SimpleNamespace(id=3, document_id=1, status="cancelled", summary='{"error_detail":"stopped"}', total_issues=1),
        SimpleNamespace(id=4, document_id=1, status="running", summary="", total_issues=0),
        SimpleNamespace(id=5, document_id=1, status="timeout", summary='{"error_code":"timeout","error_detail":"expired"}', total_issues=0),
        SimpleNamespace(id=6, document_id=1, status="mystery", summary="", total_issues=0),
    ]
    _patch_list_reviews(monkeypatch, reviews)
    result = asyncio.run(review_api.list_reviews(db=None, skip=0, limit=20))
    statuses = [item["status"] for item in result["items"]]
    assert statuses == ["completed", "failed", "cancelled", "running", "timeout", "mystery"]
    failed = next(item for item in result["items"] if item["status"] == "failed")
    assert failed["error_code"] == "pairing_failed"
    assert "visual missing" in (failed.get("error_detail") or failed.get("message") or "")
    timeout = next(item for item in result["items"] if item["status"] == "timeout")
    assert timeout["error_code"] == "timeout"


def test_history_list_default_is_not_latest_only(monkeypatch):
    captured = {}
    reviews = [SimpleNamespace(id=9, document_id=1, status="completed", summary="{}", total_issues=1)]
    _patch_list_reviews(monkeypatch, reviews, query_capture=captured)
    asyncio.run(review_api.list_reviews(db=None, skip=0, limit=20))
    assert captured["latest_only"] is False
    assert captured["skip"] == 0


def test_history_pagination_beyond_500(monkeypatch):
    captured = {}
    reviews = [SimpleNamespace(id=501, document_id=1, status="failed", summary="{}", total_issues=0)]
    _patch_list_reviews(monkeypatch, reviews, total=600, query_capture=captured)
    result = asyncio.run(review_api.list_reviews(db=None, skip=500, limit=20))
    assert captured["skip"] == 500
    assert captured["limit"] == 20
    assert result["total"] == 600
    assert result["skip"] == 500
    assert result["limit"] == 20
    assert len(result["items"]) == 1


def test_normalize_status_keeps_timeout_and_unknown():
    assert review_api._normalize_review_status("timeout") == "timeout"
    assert review_api._normalize_review_status("error") == "error"
    assert review_api._normalize_review_status("mystery") == "mystery"
    assert review_api._normalize_review_status(None) is None


def test_frontend_history_does_not_filter_completed_only():
    vue = Path("/workspace/frontend/src/views/Review.vue").read_text(encoding="utf-8")
    assert "historyReviews = computed(() => reviews.value || [])" in vue
    assert "filter(review => review.status === 'completed')" not in vue
    assert "reportRequestSeq" in vue
    assert "reviewAPI.get(id)" in vue
    assert "reviewAPI.getIssues(id)" in vue
    assert "seq !== reportRequestSeq" in vue


def test_runtime_symbols_importable():
    from app.review_engine.pairing import resolve_input_pairing
    from app.database import OrphanReviewDataError, _prepare_review_fk_parents, collect_orphan_review_report
    from app.services.chunker import create_smart_chunker
    assert callable(resolve_input_pairing)
    assert callable(collect_orphan_review_report)
    assert callable(_prepare_review_fk_parents)
    assert "sampling_mode" in inspect.signature(create_smart_chunker).parameters
    assert OrphanReviewDataError is not None
    review_api._assert_review_runtime_ready()


def test_runtime_missing_creates_failed_task(monkeypatch):
    statuses = []
    monkeypatch.setattr(review_api, "_assert_review_runtime_ready", lambda: (_ for _ in ()).throw(RuntimeError("runtime_missing:pairing")))
    monkeypatch.setattr("app.crud.review.reclaim_stale_running_reviews", lambda *a, **k: None)
    monkeypatch.setattr(review_api, "get_document", lambda db, document_id=None: SimpleNamespace(id=1, file_type="docx", filename="a.docx", user_id=1))
    monkeypatch.setattr(review_api, "_ensure_document_access", lambda doc, user: doc)
    monkeypatch.setattr(review_api, "_get_active_review_for_document", lambda *a, **k: None)
    monkeypatch.setattr(review_api, "create_review", lambda db=None, review=None: SimpleNamespace(id=55, document_id=1))
    monkeypatch.setattr(review_api, "update_review_status", lambda db, rid, status, total, summary: statuses.append((rid, status, summary)))
    monkeypatch.setattr(review_api, "set_progress", lambda *a, **k: None)
    result = asyncio.run(review_api.create_review_task(
        1,
        mode="hybrid",
        db=None,
        current_user=SimpleNamespace(id=1, role="admin"),
    ))
    assert result["status"] == "failed"
    assert result["error_code"] == "runtime_missing"
    assert statuses[0][1] == "failed"


def test_visual_page_jobs_render_each_page_once(monkeypatch):
    renders = []

    class DummySem:
        def acquire(self):
            return True

        def release(self):
            return None

    monkeypatch.setattr(review_api, "_visual_semaphore", lambda: DummySem())
    monkeypatch.setattr(review_api, "_int_env", lambda *a, **k: 2)
    monkeypatch.setattr(review_api, "_render_pdf_page_png_bytes", lambda path, page: renders.append(page) or b"png")
    monkeypatch.setattr(review_api, "_verify_review_issue_visually", lambda *a, **k: {"decision": "verified", "visual_status": "verified"})
    jobs = [(1, {"id": 1}), (1, {"id": 2}), (2, {"id": 3})]
    results = review_api._run_visual_page_jobs(9, "demo.pdf", jobs)
    assert set(renders) == {1, 2}
    assert len(renders) == 2
    assert set(results) == {1, 2}


def test_content_issues_persisted_before_visual():
    source = Path(review_api.__file__).read_text(encoding="utf-8")
    persist_pos = source.find("_persist_review_issues(db, review_id, issues)")
    visual_pos = source.find("_apply_pdf_visual_verification(")
    assert persist_pos > 0
    assert visual_pos > persist_pos


def test_persist_review_issues_skips_already_saved(monkeypatch):
    created = []

    class FakeIssue:
        def __init__(self, issue_id):
            self.id = issue_id

    def fake_create(db=None, issue=None):
        created.append(issue)
        return FakeIssue(len(created))

    monkeypatch.setattr(review_api, "create_issue", fake_create)
    issues = [{"severity": "general", "category": "错别字", "rule": "R1", "original_text": "交户界面"}]
    review_api._persist_review_issues(None, 12, issues)
    review_api._persist_review_issues(None, 12, issues)
    assert len(created) == 1
    assert issues[0]["_db_id"] == 1


def test_cache_key_isolates_pairing_and_prompt(monkeypatch):
    monkeypatch.setattr(review_api, "_review_cache_version", lambda: "v1")
    document = SimpleNamespace(id=1, filename="demo.docx", file_type="docx", file_size=10, content="same")
    visual = SimpleNamespace(id=2, filename="demo.pdf", file_type="pdf", file_size=11, content="pdf")
    single = review_api._build_review_cache_key(document, "hybrid")
    paired = review_api._build_review_cache_key(document, "hybrid", visual_document=visual, pairing_confirmed=True)
    unconfirmed = review_api._build_review_cache_key(document, "hybrid", visual_document=visual, pairing_confirmed=False)
    assert single != paired
    assert paired != unconfirmed
    monkeypatch.setattr("app.review_engine.versions.PROMPT_VERSION", PROMPT_VERSION + "-changed")
    # fingerprint reads PROMPT_VERSION from versions at call time inside function
    from app.review_engine import versions as version_mod
    monkeypatch.setattr(version_mod, "PROMPT_VERSION", "prompt-changed")
    changed = review_api._build_review_cache_key(document, "hybrid", visual_document=visual, pairing_confirmed=True)
    assert changed != paired


def test_bounded_ttl_cache_expiry_and_eviction():
    cache = BoundedTTLCache(max_items=2, ttl_seconds=60)
    cache.set("a", {"n": 1})
    cache.set("b", {"n": 2})
    cache.set("c", {"n": 3})
    assert cache.get("a") is None
    assert cache.get("c") == {"n": 3}
    cache._items["b"]["ts"] = time.time() - 120
    assert cache.get("b") is None
    assert cache.get("missing", default={"ok": True}) == {"ok": True}


def test_task_state_isolated_between_reviews():
    review_api._store_basis_trace(101, {"basis_source": "local", "review_id": 101})
    review_api._store_basis_trace(102, {"basis_source": "es", "review_id": 102})
    review_api.set_progress(101, "running", "内容审核", 40, "A")
    review_api.set_progress(102, "running", "视觉复核", 80, "B")
    assert review_api._load_basis_trace(101)["basis_source"] == "local"
    assert review_api.get_progress(101)["message"] == "A"
    assert review_api.get_progress(102)["step"] == "视觉复核"
    clear_task_state(101)
    review_api._review_observation_store.pop("101:basis_trace", None)
    assert review_api._load_basis_trace(102)["basis_source"] == "es"
    assert review_api.get_progress(102)["message"] == "B"


def test_delete_document_keeps_formal_review_history():
    api_source = Path("/workspace/backend/app/api/documents.py").read_text(encoding="utf-8")
    crud_source = Path("/workspace/backend/app/crud/document.py").read_text(encoding="utf-8")
    assert "if filename.startswith(\"文本片段_\"):" in api_source
    assert "delete_reviews_by_document(db, document_id)" in api_source
    assert "deleted_at" in crud_source
    assert "has_reviews" in crud_source
