import os
import tempfile
import unittest
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import knowledge
from app.api.auth import create_access_token
from app.database import Base, get_db
from app.models.knowledge import Folder, KnowledgeFile, KnowledgeFileCall
from app.models.user import User
from app.utils import knowledge_usage


class KnowledgeUsageTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=cls.engine)
        Base.metadata.create_all(bind=cls.engine)
        cls._orig_session = knowledge_usage.SessionLocal
        knowledge_usage.SessionLocal = cls.SessionLocal

        app = FastAPI()
        app.include_router(knowledge.router, prefix="/api/knowledge")

        def override_get_db():
            db = cls.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        knowledge_usage.SessionLocal = cls._orig_session

    def setUp(self):
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        knowledge_usage._usage_actor.set(None)
        knowledge_usage._request_calls.set(None)
        self.admin_id = self._create_user("admin_user", "admin")
        self.user_id = self._create_user("normal_user", "user")
        self.temp_paths = []

    def tearDown(self):
        for path in self.temp_paths:
            if os.path.exists(path):
                os.unlink(path)

    def _create_user(self, username: str, role: str) -> int:
        db = self.SessionLocal()
        try:
            user = User(username=username, password_hash="test-hash", display_name=username, role=role, status="active")
            db.add(user)
            db.commit()
            db.refresh(user)
            return user.id
        finally:
            db.close()

    def _auth_headers(self, username: str) -> dict:
        token = create_access_token({"sub": username})
        return {"Authorization": "Bearer " + token}

    def _create_temp_file(self, suffix: str, content: bytes) -> str:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.write(content)
        tmp.close()
        self.temp_paths.append(tmp.name)
        return tmp.name

    def _seed_file(self) -> int:
        db = self.SessionLocal()
        try:
            folder = Folder(name="写作规范", created_by=self.admin_id)
            db.add(folder)
            db.flush()
            knowledge_file = KnowledgeFile(
                name="guide.md",
                filename="guide.md",
                file_path=self._create_temp_file(".md", b"hello knowledge"),
                file_size=16,
                file_type="md",
                folder_id=folder.id,
                created_by=self.admin_id,
            )
            db.add(knowledge_file)
            db.commit()
            db.refresh(knowledge_file)
            return knowledge_file.id
        finally:
            db.close()

    def test_record_call_uses_guest_without_actor(self):
        file_id = self._seed_file()
        knowledge_usage.record_knowledge_file_call(file_id, knowledge_usage.MODULE_QA, 12)
        db = self.SessionLocal()
        try:
            row = db.query(KnowledgeFileCall).one()
            self.assertEqual(row.file_id, file_id)
            self.assertEqual(row.module, "qa")
            self.assertEqual(row.username, "guest")
            self.assertEqual(row.duration_ms, 12)
        finally:
            db.close()

    def test_record_call_uses_bound_user(self):
        file_id = self._seed_file()
        token = knowledge_usage.set_usage_actor(SimpleNamespace(id=self.admin_id, username="admin_user"))
        try:
            knowledge_usage.record_knowledge_file_call(file_id, knowledge_usage.MODULE_POLISH, 8)
        finally:
            knowledge_usage.reset_usage_actor(token)
        db = self.SessionLocal()
        try:
            row = db.query(KnowledgeFileCall).one()
            self.assertEqual(row.username, "admin_user")
            self.assertEqual(row.user_id, self.admin_id)
            self.assertEqual(row.module, "polish")
        finally:
            db.close()

    def test_admin_can_read_summary_and_details(self):
        file_id = self._seed_file()
        knowledge_usage.record_knowledge_file_call(
            file_id, knowledge_usage.MODULE_TRANSLATION, 20,
            user=SimpleNamespace(id=self.admin_id, username="admin_user"),
        )
        headers = self._auth_headers("admin_user")
        summary = self.client.get("/api/knowledge/usage/summary", headers=headers)
        self.assertEqual(summary.status_code, 200, summary.text)
        payload = summary.json()
        self.assertEqual(payload["file_count"], 1)
        self.assertEqual(payload["total_calls"], 1)
        self.assertEqual(payload["items"][0]["file_name"], "guide.md")
        self.assertEqual(payload["items"][0]["modules"], ["translation"])
        self.assertEqual(payload["items"][0]["folder_path"], "写作规范")
        self.assertEqual(payload["module_stats"][0]["module"], "translation")
        self.assertEqual(payload["module_stats"][0]["call_count"], 1)

        details = self.client.get(f"/api/knowledge/usage/files/{file_id}", headers=headers)
        self.assertEqual(details.status_code, 200, details.text)
        item = details.json()["items"][0]
        self.assertEqual(item["username"], "admin_user")
        self.assertEqual(item["module_label"], "AI翻译")
        self.assertEqual(item["duration_ms"], 20)

    def test_user_cannot_read_usage_stats(self):
        headers = self._auth_headers("normal_user")
        summary = self.client.get("/api/knowledge/usage/summary", headers=headers)
        self.assertEqual(summary.status_code, 403)
        details = self.client.get("/api/knowledge/usage/files/1", headers=headers)
        self.assertEqual(details.status_code, 403)

    def test_polish_file_load_writes_call(self):
        from app.api.polish_lab import _load_file_content

        file_id = self._seed_file()
        db = self.SessionLocal()
        try:
            content = _load_file_content(db, file_id)
            self.assertIn("hello knowledge", content)
        finally:
            db.close()
        db = self.SessionLocal()
        try:
            row = db.query(KnowledgeFileCall).one()
            self.assertEqual(row.file_id, file_id)
            self.assertEqual(row.module, "polish")
            self.assertGreaterEqual(row.duration_ms, 1)
        finally:
            db.close()

    def test_middleware_does_not_500_on_sync_route(self):
        file_id = self._seed_file()
        app = FastAPI()
        knowledge_usage.install_knowledge_usage_middleware(app)

        @app.get("/ping")
        def ping():
            knowledge_usage.record_knowledge_file_call(file_id, knowledge_usage.MODULE_POLISH, 5)
            return {"ok": True}

        client = TestClient(app)
        resp = client.get("/ping", headers=self._auth_headers("admin_user"))
        self.assertEqual(resp.status_code, 200, resp.text)
        db = self.SessionLocal()
        try:
            row = db.query(KnowledgeFileCall).one()
            self.assertEqual(row.username, "admin_user")
            self.assertEqual(row.module, "polish")
        finally:
            db.close()

    def test_middleware_uses_guest_without_token(self):
        file_id = self._seed_file()
        app = FastAPI()
        knowledge_usage.install_knowledge_usage_middleware(app)

        @app.get("/ping")
        def ping():
            knowledge_usage.record_knowledge_file_call(file_id, knowledge_usage.MODULE_QA, 3)
            return {"ok": True}

        client = TestClient(app)
        resp = client.get("/ping")
        self.assertEqual(resp.status_code, 200, resp.text)
        db = self.SessionLocal()
        try:
            row = db.query(KnowledgeFileCall).one()
            self.assertEqual(row.username, "guest")
        finally:
            db.close()

    def test_zero_duration_is_recorded_as_one_ms(self):
        file_id = self._seed_file()
        knowledge_usage.record_knowledge_file_call(file_id, knowledge_usage.MODULE_POLISH, 0)
        db = self.SessionLocal()
        try:
            row = db.query(KnowledgeFileCall).one()
            self.assertEqual(row.duration_ms, 1)
        finally:
            db.close()

    def test_same_request_dedupes_file_calls(self):
        file_id = self._seed_file()
        knowledge_usage._request_calls.set({})
        try:
            knowledge_usage.record_knowledge_file_call(file_id, knowledge_usage.MODULE_POLISH, 4)
            knowledge_usage.record_knowledge_file_call(file_id, knowledge_usage.MODULE_POLISH, 6)
            knowledge_usage.record_knowledge_file_call(file_id, knowledge_usage.MODULE_QA, 3)
        finally:
            knowledge_usage._request_calls.set(None)
        db = self.SessionLocal()
        try:
            rows = db.query(KnowledgeFileCall).order_by(KnowledgeFileCall.module.asc()).all()
            self.assertEqual(len(rows), 2)
            polish_row = next(row for row in rows if row.module == "polish")
            qa_row = next(row for row in rows if row.module == "qa")
            self.assertEqual(polish_row.duration_ms, 10)
            self.assertEqual(qa_row.duration_ms, 3)
        finally:
            db.close()
