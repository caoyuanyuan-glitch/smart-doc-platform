import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import review
from app.api.auth import create_access_token
from app.database import Base, get_db
from app.models.document import Document
from app.models.false_positive_memory import FalsePositiveMemory
from app.models.issue import Issue
from app.models.review import Review
from app.models.user import User


class FalsePositiveMemoryApiTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=cls.engine)
        Base.metadata.create_all(bind=cls.engine)

        app = FastAPI()
        app.include_router(review.router, prefix="/api/review")

        def override_get_db():
            db = cls.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

    def setUp(self):
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.admin_id = self._create_user("admin_user", "admin")
        self.writer_id = self._create_user("writer_user", "writer")

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
        return {"Authorization": f"Bearer {token}"}

    def _seed_memory(self):
        db = self.SessionLocal()
        try:
            document = Document(
                filename="ifu-demo.pdf",
                file_type="pdf",
                file_size=128,
                content="demo content",
                status="ready",
                preview="demo",
                user_id=self.writer_id,
            )
            db.add(document)
            db.flush()

            review_row = Review(
                document_id=document.id,
                mode="hybrid",
                provider="kimi",
                status="completed",
                total_issues=1,
                summary="{}",
            )
            db.add(review_row)
            db.flush()

            issue = Issue(
                review_id=review_row.id,
                severity="general",
                category="格式规范",
                rule="R013",
                chapter="1.1",
                original_text="This is a false positive sample",
                context="context",
                suggestion="suggestion",
                description="description",
                audit_basis="basis",
                confidence=90,
                source="ai",
                status="false_positive",
                position="{}",
                providers='["kimi"]',
            )
            db.add(issue)
            db.flush()

            entry = FalsePositiveMemory(
                source_issue_id=issue.id,
                signature="r013:false-positive-sample",
                rule="R013",
                category="格式规范",
                original_text="This is a false positive sample",
                enabled=True,
            )
            db.add(entry)
            db.commit()
            db.refresh(entry)
            return entry.id
        finally:
            db.close()

    def test_list_false_positive_memory_requires_admin(self):
        self._seed_memory()

        response = self.client.get("/api/review/false-positive-memory")
        self.assertEqual(response.status_code, 401)

        response = self.client.get(
            "/api/review/false-positive-memory",
            headers=self._auth_headers("writer_user"),
        )
        self.assertEqual(response.status_code, 403)

    def test_list_false_positive_memory_supports_keyword_search(self):
        self._seed_memory()

        response = self.client.get(
            "/api/review/false-positive-memory",
            headers=self._auth_headers("admin_user"),
            params={"keyword": "ifu-demo", "limit": 20},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["items"][0]["document_name"], "ifu-demo.pdf")
        self.assertEqual(payload["items"][0]["rule"], "R013")

    def test_delete_false_positive_memory_removes_entry(self):
        entry_id = self._seed_memory()

        response = self.client.delete(
            f"/api/review/false-positive-memory/{entry_id}",
            headers=self._auth_headers("admin_user"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["success"], True)

        response = self.client.get(
            "/api/review/false-positive-memory",
            headers=self._auth_headers("admin_user"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 0)
