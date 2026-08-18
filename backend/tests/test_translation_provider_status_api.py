import sys
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.api import translation  # noqa: E402
from app.api.auth import create_access_token  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.models.user import User  # noqa: E402


class TranslationProviderStatusApiTestCase(unittest.TestCase):
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
        app.include_router(translation.router, prefix="/api/translation")

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
        self._create_user("writer_user", "writer")

    def _create_user(self, username: str, role: str):
        db = self.SessionLocal()
        try:
            user = User(username=username, password_hash="test-hash", display_name=username, role=role, status="active")
            db.add(user)
            db.commit()
        finally:
            db.close()

    def _auth_headers(self, username: str) -> dict:
        token = create_access_token({"sub": username})
        return {"Authorization": f"Bearer {token}"}

    def test_provider_status_requires_login(self):
        response = self.client.get("/api/translation/providers/status")
        self.assertEqual(response.status_code, 401)

    def test_provider_status_allows_non_admin_user(self):
        response = self.client.get(
            "/api/translation/providers/status",
            headers=self._auth_headers("writer_user"),
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("priority", payload)
        self.assertIn("available", payload)
