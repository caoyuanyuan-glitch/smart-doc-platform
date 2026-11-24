from datetime import datetime
from types import SimpleNamespace
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import qa
from app.api.auth import get_current_user
from app.database import Base, get_db
from app.models.qa_history import QaMessage, QaSession
from app.models.user import User


class QaHistoryApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=cls.engine)
        Base.metadata.create_all(bind=cls.engine)
        cls.current_user = SimpleNamespace(id=2, role="user", username="rolecheck_user", status="active")

        app = FastAPI()
        app.include_router(qa.router, prefix="/api/qa")

        def override_get_db():
            db = cls.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        def override_user():
            return cls.current_user

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_user
        cls.client = TestClient(app)

    def setUp(self):
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.__class__.current_user = SimpleNamespace(id=2, role="user", username="rolecheck_user", status="active")
        db = self.SessionLocal()
        try:
            db.add(User(id=1, username="admin", password_hash="x", display_name="管理员", role="admin", status="active"))
            db.add(User(id=2, username="rolecheck_user", password_hash="x", display_name="普通用户", role="user", status="active"))
            own = QaSession(user_id=2, session_type="general", title="普通用户的问题", created_at=datetime(2026, 11, 23, 1, 0, 0), updated_at=datetime(2026, 11, 23, 1, 0, 0))
            other = QaSession(user_id=1, session_type="general", title="管理员的问题", created_at=datetime(2026, 11, 23, 1, 0, 0), updated_at=datetime(2026, 11, 23, 1, 0, 0))
            db.add(own)
            db.add(other)
            db.flush()
            db.add(QaMessage(session_id=own.id, role="user", content="普通用户的问题"))
            db.add(QaMessage(session_id=own.id, role="assistant", content="回答", duration_ms=12500))
            db.commit()
            self.own_id = own.id
            self.other_id = other.id
        finally:
            db.close()

    def test_regular_user_lists_own_sessions(self):
        response = self.client.get("/api/qa/history/sessions", params={"type": "general"})
        self.assertEqual(response.status_code, 200)
        titles = [item["title"] for item in response.json()["sessions"]]
        self.assertEqual(titles, ["普通用户的问题"])

    def test_regular_user_cannot_open_others_session(self):
        response = self.client.get(f"/api/qa/history/sessions/{self.other_id}")
        self.assertEqual(response.status_code, 404)

    def test_session_duration_is_returned(self):
        listed = self.client.get("/api/qa/history/sessions", params={"type": "general"})
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["sessions"][0]["duration_ms"], 12500)

        detail = self.client.get(f"/api/qa/history/sessions/{self.own_id}")
        self.assertEqual(detail.status_code, 200)
        body = detail.json()
        self.assertEqual(body["session"]["duration_ms"], 12500)
        assistant = next(item for item in body["messages"] if item["role"] == "assistant")
        self.assertEqual(assistant["duration_ms"], 12500)
