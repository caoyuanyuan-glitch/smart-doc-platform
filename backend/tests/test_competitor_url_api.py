import json
import unittest
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import competitor
from app.api.auth import create_access_token
from app.database import Base, get_db
from app.models.competitor_task import CompetitorTask
from app.models.user import User


class CompetitorUrlApiTestCase(unittest.TestCase):
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
        app.include_router(competitor.router, prefix="/api/competitor")

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

    def test_create_competitor_task_from_url_extracts_html_content(self):
        html = b"""
        <html>
          <head><title>Sample Manual</title><style>.hidden{display:none}</style></head>
          <body>
            <main>
              <h1>Quick Start</h1>
              <p>Configure the instrument before the first run.</p>
              <p>Review the safety notes before operation.</p>
            </main>
            <script>console.log('skip me')</script>
          </body>
        </html>
        """
        fake_headers = Mock()
        fake_headers.get_content_type.return_value = "text/html"
        fake_headers.get_content_charset.return_value = "utf-8"
        fake_response = Mock()
        fake_response.headers = fake_headers
        fake_response.read.return_value = html
        fake_response.geturl.return_value = "https://docs.example.com/manual.html"
        fake_response.__enter__ = Mock(return_value=fake_response)
        fake_response.__exit__ = Mock(return_value=False)

        with patch("app.api.competitor.request.urlopen", return_value=fake_response):
            response = self.client.post(
                "/api/competitor/url",
                headers=self._auth_headers("writer_user"),
                json={"url": "https://docs.example.com/manual.html"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["file_name"], "Sample_Manual.html")
        self.assertEqual(payload["source_type"], "html")
        self.assertGreater(payload["overall_score"], 0)

        tool_meta = json.loads(payload["tool_analysis"])["meta"]
        self.assertEqual(tool_meta["format"], "HTML")
        self.assertEqual(tool_meta["source_url"], "https://docs.example.com/manual.html")
        self.assertEqual(tool_meta["title"], "Sample Manual")

        readability = json.loads(payload["readability"])
        self.assertGreater(readability["overall_score"], 0)
        self.assertIn("access", readability)
        self.assertIn("findability", readability)
        self.assertIn("usability", readability)
        self.assertIn("Quick Start", payload["report_md"])
        self.assertIn("可获得性分析", payload["report_md"])

        db = self.SessionLocal()
        try:
            tasks = db.query(CompetitorTask).all()
            self.assertEqual(len(tasks), 1)
            self.assertEqual(tasks[0].status, "completed")
        finally:
            db.close()

    def test_create_competitor_task_accepts_local_html_upload(self):
        html = b"""
        <html>
          <head><title>Local Help Center</title></head>
          <body>
            <main>
              <h1>Troubleshooting</h1>
              <p>The instrument is configured before startup.</p>
              <p>Check the connection status and restart the workflow.</p>
            </main>
          </body>
        </html>
        """

        response = self.client.post(
            "/api/competitor/",
            headers=self._auth_headers("writer_user"),
            files={"file": ("local-manual.html", html, "text/html")},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["file_name"], "local-manual.html")
        self.assertEqual(payload["source_type"], "html")
        self.assertGreater(payload["overall_score"], 0)

        tool_meta = json.loads(payload["tool_analysis"])["meta"]
        self.assertEqual(tool_meta["format"], "HTML")
        self.assertEqual(tool_meta["producer"], "Local HTML file")
        self.assertEqual(tool_meta["creator"], "Uploaded file")
        self.assertEqual(tool_meta["pages"], 1)

        readability = json.loads(payload["readability"])
        self.assertGreater(readability["overall_score"], 0)
        self.assertIn("access", readability)
        self.assertIn("Troubleshooting", payload["report_md"])

    def test_read_competitor_report_supports_json_format(self):
        html = b"""
        <html>
          <head><title>JSON Report</title></head>
          <body><main><p>The workflow is started after the checklist is reviewed.</p></main></body>
        </html>
        """

        create_resp = self.client.post(
            "/api/competitor/",
            headers=self._auth_headers("writer_user"),
            files={"file": ("report.html", html, "text/html")},
        )
        self.assertEqual(create_resp.status_code, 200)
        task_id = create_resp.json()["id"]

        report_resp = self.client.get(
            f"/api/competitor/{task_id}/report",
            headers=self._auth_headers("writer_user"),
            params={"format": "json"},
        )

        self.assertEqual(report_resp.status_code, 200)
        payload = report_resp.json()
        self.assertEqual(payload["format"], "json")
        self.assertEqual(payload["content"]["source_type"], "html")
        self.assertEqual(payload["content"]["file_name"], "report.html")
        self.assertIn("overall_score", payload["content"])
        self.assertIn("tool_analysis", payload["content"])
        self.assertIn("readability", payload["content"])
        self.assertIn("access", json.loads(payload["content"]["readability"]))

    def test_create_competitor_task_falls_back_to_memory_when_db_create_fails(self):
        html = b"""
        <html>
          <head><title>Memory Fallback</title></head>
          <body><main><p>The checklist is reviewed before startup.</p></main></body>
        </html>
        """

        with patch("app.crud.competitor.create_competitor_task", side_effect=RuntimeError("db offline")):
            response = self.client.post(
                "/api/competitor/",
                headers=self._auth_headers("writer_user"),
                files={"file": ("memory.html", html, "text/html")},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertGreaterEqual(payload["id"], 1000)
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["source_type"], "html")
        self.assertGreater(payload["overall_score"], 0)

        detail_resp = self.client.get(
            f"/api/competitor/{payload['id']}",
            headers=self._auth_headers("writer_user"),
        )
        self.assertEqual(detail_resp.status_code, 200)
        self.assertEqual(detail_resp.json()["file_name"], "memory.html")

    def test_create_competitor_task_from_url_rejects_invalid_scheme(self):
        response = self.client.post(
            "/api/competitor/url",
            headers=self._auth_headers("writer_user"),
            json={"url": "ftp://docs.example.com/manual.html"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("http/https", response.json()["detail"])
