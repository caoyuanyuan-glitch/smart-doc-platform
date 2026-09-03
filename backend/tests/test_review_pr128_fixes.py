import asyncio
import json
import subprocess
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import polish_rules, review as review_api
from app.api.auth import create_access_token
from app.crud.review import apply_review_pairing, create_review, create_issue, get_review, list_false_positive_memory, reclaim_stale_running_reviews
from app.database import Base, get_db
from app.models.document import Document
from app.models.false_positive_memory import FalsePositiveMemory
from app.models.issue import Issue
from app.models.review import Review
from app.models.user import User
from app.models.polish_learning_rule import PolishLearningRule
from app.review_engine.pairing import resolve_input_pairing
from app.schemas.review import IssueCreate, ReviewCreate

REPO_ROOT = Path(__file__).resolve().parents[2]


def _memory_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine), engine


def test_pairing_explicit_keeps_same_user_gate():
    docx = SimpleNamespace(id=1, file_type="docx", filename="a.docx", user_id=1)
    pdf = SimpleNamespace(id=2, file_type="pdf", filename="a.pdf", user_id=2)
    result = resolve_input_pairing(docx, pdf, explicit=True, same_user=False, same_task=True)
    assert result.pairing_status == "unpaired"


def test_pairing_persistence_survives_new_session():
    SessionLocal, engine = _memory_session()
    db = SessionLocal()
    try:
        db.add(Document(id=1, filename="manual.docx", file_type="docx", content="word", user_id=1))
        db.add(Document(id=2, filename="manual.pdf", file_type="pdf", content="pdf", user_id=1))
        db.commit()
        review = create_review(db, ReviewCreate(document_id=1, mode="hybrid", visual_document_id=2, pairing_confirmed=True))
        pairing = resolve_input_pairing(
            SimpleNamespace(id=1, file_type="docx", filename="manual.docx", user_id=1),
            SimpleNamespace(id=2, file_type="pdf", filename="manual.pdf", user_id=1),
            explicit=True,
            same_user=True,
        )
        apply_review_pairing(db, review.id, pairing, pairing_confirmed=True)
        review_id = review.id
    finally:
        db.close()

    db2 = SessionLocal()
    try:
        loaded = get_review(db2, review_id)
        assert loaded.visual_document_id == 2
        assert loaded.pairing_status == "paired"
        assert loaded.input_mode == "paired"
        assert bool(loaded.pairing_confirmed) is True
    finally:
        db2.close()
        engine.dispose()


def test_pairing_persistence_docx_only():
    SessionLocal, engine = _memory_session()
    db = SessionLocal()
    try:
        db.add(Document(id=3, filename="solo.docx", file_type="docx", content="word", user_id=1))
        db.commit()
        review = create_review(db, ReviewCreate(document_id=3, mode="hybrid"))
        pairing = resolve_input_pairing(SimpleNamespace(id=3, file_type="docx", filename="solo.docx", user_id=1), None)
        apply_review_pairing(db, review.id, pairing, pairing_confirmed=False)
        loaded = get_review(db, review.id)
        assert loaded.input_mode == "docx_only"
        assert loaded.pairing_status == "docx_only"
    finally:
        db.close()
        engine.dispose()


def test_pairing_persistence_pdf_only():
    SessionLocal, engine = _memory_session()
    db = SessionLocal()
    try:
        db.add(Document(id=4, filename="solo.pdf", file_type="pdf", content="pdf", user_id=1))
        db.commit()
        review = create_review(db, ReviewCreate(document_id=4, mode="hybrid"))
        pairing = resolve_input_pairing(SimpleNamespace(id=4, file_type="pdf", filename="solo.pdf", user_id=1), None)
        apply_review_pairing(db, review.id, pairing, pairing_confirmed=False)
        loaded = get_review(db, review.id)
        assert loaded.input_mode == "pdf_only"
        assert loaded.pairing_status == "pdf_only"
    finally:
        db.close()
        engine.dispose()


def _seed_review_issues(db):
    db.add(User(id=1, username="alice", password_hash="x", role="user", status="active"))
    db.add(Document(id=1, filename="a.docx", file_type="docx", content="word", user_id=1))
    db.add(Document(id=2, filename="b.docx", file_type="docx", content="other", user_id=1))
    db.commit()
    review_a = create_review(db, ReviewCreate(document_id=1, mode="hybrid"))
    review_b = create_review(db, ReviewCreate(document_id=2, mode="hybrid"))
    issue_a = create_issue(db, IssueCreate(
        review_id=review_a.id, severity="general", category="x", rule="R1",
        chapter="", original_text="foo", suggestion="bar", status="pending",
    ))
    issue_b = create_issue(db, IssueCreate(
        review_id=review_b.id, severity="general", category="x", rule="R1",
        chapter="", original_text="foo", suggestion="bar", status="pending",
    ))
    return review_a, review_b, issue_a, issue_b


def test_batch_judge_same_review_success():
    SessionLocal, engine = _memory_session()
    db = SessionLocal()
    try:
        review_a, _, issue_a, _ = _seed_review_issues(db)
        result = asyncio.run(review_api.batch_judge_issues(
            review_a.id,
            {"judgments": [{"issue_id": issue_a.id, "status": "confirmed"}]},
            db=db,
            current_user=SimpleNamespace(id=1, role="user"),
        ))
        assert result["updated"] == 1
        db.refresh(issue_a)
        assert issue_a.status == "confirmed"
    finally:
        db.close()
        engine.dispose()


def test_batch_judge_rejects_foreign_issue_atomically():
    SessionLocal, engine = _memory_session()
    db = SessionLocal()
    try:
        review_a, review_b, issue_a, issue_b = _seed_review_issues(db)
        try:
            asyncio.run(review_api.batch_judge_issues(
                review_a.id,
                {"judgments": [
                    {"issue_id": issue_a.id, "status": "confirmed"},
                    {"issue_id": issue_b.id, "status": "false_positive"},
                ]},
                db=db,
                current_user=SimpleNamespace(id=1, role="user"),
            ))
            raise AssertionError("expected HTTPException")
        except HTTPException as exc:
            assert exc.status_code == 404
        db.refresh(issue_a)
        db.refresh(issue_b)
        assert issue_a.status == "pending"
        assert issue_b.status == "pending"
    finally:
        db.close()
        engine.dispose()


def test_batch_judge_missing_issue_does_not_partial_commit():
    SessionLocal, engine = _memory_session()
    db = SessionLocal()
    try:
        review_a, _, issue_a, _ = _seed_review_issues(db)
        try:
            asyncio.run(review_api.batch_judge_issues(
                review_a.id,
                {"judgments": [
                    {"issue_id": issue_a.id, "status": "confirmed"},
                    {"issue_id": 99999, "status": "confirmed"},
                ]},
                db=db,
                current_user=SimpleNamespace(id=1, role="user"),
            ))
            raise AssertionError("expected HTTPException")
        except HTTPException as exc:
            assert exc.status_code == 404
        db.refresh(issue_a)
        assert issue_a.status == "pending"
    finally:
        db.close()
        engine.dispose()


def test_batch_judge_false_positive_syncs_memory():
    SessionLocal, engine = _memory_session()
    db = SessionLocal()
    try:
        review_a, _, issue_a, _ = _seed_review_issues(db)
        asyncio.run(review_api.batch_judge_issues(
            review_a.id,
            {"judgments": [{"issue_id": issue_a.id, "status": "false_positive"}]},
            db=db,
            current_user=SimpleNamespace(id=1, role="user"),
        ))
        db.refresh(issue_a)
        assert issue_a.status == "false_positive"
        items, total = list_false_positive_memory(db)
        assert total >= 1
        assert any(item["source_issue_id"] == issue_a.id for item in items)
    finally:
        db.close()
        engine.dispose()


def test_cached_issues_do_not_leak_task_metadata():
    dirty = [{
        "original_text": "foo",
        "suggestion": "bar",
        "review_id": 1,
        "document_id": 2,
        "status": "false_positive",
        "visual_verification": {"page": 9, "bbox": [1, 2, 3, 4]},
        "providers": "[\"qwen\"]",
        "manual_note": "old",
    }]
    stored = review_api._content_only_cached_issues(dirty)
    assert stored[0]["original_text"] == "foo"
    assert "review_id" not in stored[0]
    assert "status" not in stored[0]
    assert "visual_verification" not in stored[0]
    assert "providers" not in stored[0]
    bound_a = review_api._bind_cached_issues(stored, review_id=88, document_id=9)
    bound_b = review_api._bind_cached_issues(stored, review_id=89, document_id=10)
    assert bound_a[0]["review_id"] == 88
    assert bound_b[0]["review_id"] == 89
    assert bound_a[0]["status"] == "pending"
    assert bound_b[0]["status"] == "pending"
    assert bound_a[0]["document_id"] == 9


def test_chunk_cache_hit_rebinds_review_id(monkeypatch):
    review_api._ai_review_chunk_cache.clear()
    calls = []

    def fake_audit(*args, **kwargs):
        calls.append(1)
        return {"issues": [{"original_text": "x", "suggestion": "y", "review_id": 1, "status": "confirmed"}]}

    monkeypatch.setattr(review_api.ai_client, "audit_document", fake_audit)
    monkeypatch.setattr(review_api, "_call_with_timeout", lambda func, timeout, *a, **k: func(*a, **k))
    monkeypatch.setattr(review_api, "_ensure_review_not_cancelled", lambda *a, **k: None)
    monkeypatch.setattr(review_api, "_record_review_observations", lambda *a, **k: None)
    monkeypatch.setattr(review_api, "_AI_REVIEW_SEMAPHORE", SimpleNamespace(acquire=lambda: None, release=lambda: None))

    first, hit1 = review_api._run_cached_ai_chunk_review(11, "chunk", "cn", "basis", 10)
    second, hit2 = review_api._run_cached_ai_chunk_review(22, "chunk", "cn", "basis", 10)
    assert hit1 is False
    assert hit2 is True
    assert first[0]["review_id"] == 11
    assert second[0]["review_id"] == 22
    assert first[0]["status"] == "pending"
    assert second[0]["status"] == "pending"
    assert len(calls) == 1


def test_reclaim_stale_running_reviews_marks_timeout():
    SessionLocal, engine = _memory_session()
    db = SessionLocal()
    try:
        db.add(Document(id=1, filename="a.docx", file_type="docx", content="word", user_id=1))
        db.commit()
        review = create_review(db, ReviewCreate(document_id=1, mode="hybrid"))
        review.status = "running"
        review.heartbeat_at = datetime(2020, 1, 1)
        db.commit()
        count = reclaim_stale_running_reviews(db, timeout_seconds=30)
        db.refresh(review)
        assert count == 1
        assert review.status == "timeout"
        assert review.error_code == "timeout"
    finally:
        db.close()
        engine.dispose()


def test_sanitize_error_detail_strips_secrets_and_paths():
    raw = "failed api_key=sk-abcdefghijklmnopqrstuvwxyz /workspace/backend/app/api/review.py"
    cleaned = review_api._sanitize_error_detail(raw)
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in cleaned
    assert "/workspace/backend" not in cleaned


def test_frontend_source_uses_relative_repo_root():
    vue = (REPO_ROOT / "frontend/src/views/Review.vue").read_text(encoding="utf-8")
    assert "function reviewListItems(payload)" in vue
    assert "reviewListRequestSerial" in vue
    assert "from '@/utils/issueDiff'" in vue
    assert '.diff-delete' in vue
    pkg = (REPO_ROOT / "frontend/package.json").read_text(encoding="utf-8")
    assert '"@ctrl/tinycolor"' in pkg



def test_pairing_explicit_name_mismatch_persists():
    SessionLocal, engine = _memory_session()
    db = SessionLocal()
    try:
        db.add(Document(id=1, filename="manual.docx", file_type="docx", content="word", user_id=1))
        db.add(Document(id=2, filename="other.pdf", file_type="pdf", content="pdf", user_id=1))
        db.commit()
        review = create_review(db, ReviewCreate(document_id=1, mode="hybrid", visual_document_id=2, pairing_confirmed=True))
        pairing = resolve_input_pairing(
            SimpleNamespace(id=1, file_type="docx", filename="manual.docx", user_id=1),
            SimpleNamespace(id=2, file_type="pdf", filename="other.pdf", user_id=1),
            explicit=True,
            same_user=True,
        )
        apply_review_pairing(db, review.id, pairing, pairing_confirmed=True)
        loaded = get_review(db, review.id)
        assert pairing.pairing_status == "paired"
        assert loaded.pairing_status == "paired"
        assert loaded.input_mode == "paired"
        assert loaded.visual_document_id == 2
        item = review_api._serialize_review_list_item(
            db,
            loaded,
            {1: SimpleNamespace(id=1, filename="manual.docx", file_type="docx")},
        )
        assert item["visual_document_id"] == 2
        assert item["input_pairing"]["pairing_status"] == "paired"
    finally:
        db.close()
        engine.dispose()


def test_serialize_pairing_does_not_mix_reviews():
    SessionLocal, engine = _memory_session()
    db = SessionLocal()
    try:
        db.add(Document(id=1, filename="a.docx", file_type="docx", content="a", user_id=1))
        db.add(Document(id=2, filename="a.pdf", file_type="pdf", content="p", user_id=1))
        db.add(Document(id=3, filename="b.docx", file_type="docx", content="b", user_id=1))
        db.commit()
        r1 = create_review(db, ReviewCreate(document_id=1, mode="hybrid"))
        r2 = create_review(db, ReviewCreate(document_id=3, mode="hybrid"))
        apply_review_pairing(
            db,
            r1.id,
            resolve_input_pairing(
                SimpleNamespace(id=1, file_type="docx", filename="a.docx", user_id=1),
                SimpleNamespace(id=2, file_type="pdf", filename="a.pdf", user_id=1),
                explicit=True,
                same_user=True,
            ),
            pairing_confirmed=True,
        )
        apply_review_pairing(
            db,
            r2.id,
            resolve_input_pairing(SimpleNamespace(id=3, file_type="docx", filename="b.docx", user_id=1), None),
            pairing_confirmed=False,
        )
        docs = {
            1: SimpleNamespace(id=1, filename="a.docx", file_type="docx"),
            3: SimpleNamespace(id=3, filename="b.docx", file_type="docx"),
        }
        item1 = review_api._serialize_review_list_item(db, get_review(db, r1.id), docs)
        item2 = review_api._serialize_review_list_item(db, get_review(db, r2.id), docs)
        assert item1["visual_document_id"] == 2
        assert item2.get("visual_document_id") in (None, "")
        assert item1["input_pairing"]["pairing_status"] == "paired"
        assert item2["input_pairing"]["pairing_status"] == "docx_only"
    finally:
        db.close()
        engine.dispose()


def test_review_cache_key_isolates_single_and_paired():
    document = SimpleNamespace(id=1, filename="demo.docx", file_type="docx", file_size=10, content="same")
    visual = SimpleNamespace(id=2, filename="demo.pdf", file_type="pdf", file_size=11, content="pdf")
    single = review_api._build_review_cache_key(document, "hybrid")
    paired = review_api._build_review_cache_key(document, "hybrid", visual_document=visual, pairing_confirmed=True)
    assert single != paired


def test_issue_suggestion_diff_html_via_node():
    script = REPO_ROOT / "frontend/src/utils/issueDiff.js"
    code = r"""
import { issueSuggestionDiffHtml } from 'file://%s';
const del = issueSuggestionDiffHtml({ original_text: 'abc', suggestion: 'abx' });
const esc = issueSuggestionDiffHtml({ original_text: '<b>a', suggestion: '<b>a<script>' });
const empty = issueSuggestionDiffHtml({ original_text: 'abc', suggestion: '' });
const same = issueSuggestionDiffHtml({ original_text: 'abc', suggestion: 'abc' });
const issue = { original_text: 'abc', suggestion: 'abx', status: 'confirmed' };
issueSuggestionDiffHtml(issue);
console.log(JSON.stringify({ del, esc, empty, same, status: issue.status, original: issue.original_text }));
""" % script.as_posix()
    result = subprocess.run(["node", "--input-type=module", "-e", code], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout.strip().splitlines()[-1])
    assert 'class="diff-delete"' in data["del"]
    assert 'class="diff-insert"' in data["del"]
    assert "&lt;script&gt;" in data["esc"]
    assert "<script>" not in data["esc"]
    assert data["empty"] == ""
    assert data["same"] == ""
    assert data["status"] == "confirmed"
    assert data["original"] == "abc"


def test_polish_rules_require_admin():
    SessionLocal, engine = _memory_session()

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    db = SessionLocal()
    try:
        db.add(User(username="admin_user", password_hash="x", role="admin", status="active"))
        db.add(User(username="writer_user", password_hash="x", role="writer", status="active"))
        db.commit()
    finally:
        db.close()

    app = FastAPI()
    app.include_router(polish_rules.router)
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[polish_rules.get_db] = override_get_db
    client = TestClient(app)

    assert client.get("/api/polish-rules/").status_code == 401
    writer = {"Authorization": f"Bearer {create_access_token({'sub': 'writer_user'})}"}
    assert client.get("/api/polish-rules/", headers=writer).status_code == 403
    admin = {"Authorization": f"Bearer {create_access_token({'sub': 'admin_user'})}"}
    listed = client.get("/api/polish-rules/", headers=admin)
    assert listed.status_code == 200
    created = client.post("/api/polish-rules/", headers=admin, json={
        "rule_name": "t",
        "rule_type": "replacement_rule",
        "rule_key": "rk-1",
        "match_pattern": "foo",
        "replacement_text": "bar",
    })
    assert created.status_code == 200, created.text
    rule_id = created.json()["id"]
    updated = client.put(f"/api/polish-rules/{rule_id}", headers=admin, json={"enabled": False})
    assert updated.status_code == 200
    exported = client.get("/api/polish-rules/export/json", headers=admin)
    assert exported.status_code == 200
    forbidden_write = client.post("/api/polish-rules/", headers=writer, json={
        "rule_name": "t2",
        "rule_type": "replacement_rule",
        "rule_key": "rk-2",
        "match_pattern": "foo",
        "replacement_text": "bar",
    })
    assert forbidden_write.status_code == 403
    imported = client.post(
        "/api/polish-rules/import/json",
        headers=admin,
        files={"file": ("rules.json", json.dumps([{
            "rule_name": "imp",
            "rule_type": "replacement_rule",
            "rule_key": "rk-import",
            "match_pattern": "aaa",
            "replacement_text": "bbb",
        }]), "application/json")},
    )
    assert imported.status_code == 200, imported.text
    forbidden_import = client.post(
        "/api/polish-rules/import/json",
        headers=writer,
        files={"file": ("rules.json", json.dumps([]), "application/json")},
    )
    assert forbidden_import.status_code == 403
    deleted = client.delete(f"/api/polish-rules/{rule_id}", headers=admin)
    assert deleted.status_code == 200
    engine.dispose()
