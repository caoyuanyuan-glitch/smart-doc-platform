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

# 公网 IP 的 getaddrinfo 假结果（family, type, proto, canonname, sockaddr）
_FAKE_PUBLIC_ADDRINFO = [(2, 1, 6, "", ("93.184.216.34", 443))]


def _fake_urlopen_response(html: bytes, final_url: str):
    fake_headers = Mock()
    fake_headers.get_content_type.return_value = "text/html"
    fake_headers.get_content_charset.return_value = "utf-8"
    fake_response = Mock()
    fake_response.headers = fake_headers
    fake_response.read.return_value = html
    fake_response.geturl.return_value = final_url
    fake_response.__enter__ = Mock(return_value=fake_response)
    fake_response.__exit__ = Mock(return_value=False)
    return fake_response


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
        """URL 分析：正文去噪（nav/footer 不入正文）+ Flare 证据链 + 元数据落库。"""
        # main 正文超过低内容阈值，且含 Flare 结构特征
        body_paragraphs = "\n".join(
            f"<p>Configure the instrument before the first run. Review the safety notes "
            f"before operation and check the sequencing reagents. Step {i} of the startup "
            f"procedure must be completed by a trained operator with valid certification.</p>"
            for i in range(1, 6)
        )
        html = f"""
        <html>
          <head>
            <title>Sample Manual</title>
            <style>.hidden{{display:none}}</style>
            <link rel="stylesheet" href="/Skins/Default/Stylesheets/Topic.css">
          </head>
          <body data-mc-topics-name="Topic">
            <nav><a>HomeNAV</a><a>ProductsNAV</a></nav>
            <footer><span>FooterLegalBoilerplate</span></footer>
            <main>
              <h1>Quick Start</h1>
              {body_paragraphs}
            </main>
            <script src="/Content/Resources/MadCapAll.js"></script>
            <script>console.log('skip me')</script>
          </body>
        </html>
        """.encode("utf-8")

        with patch("app.utils.competitor_html.socket.getaddrinfo", return_value=_FAKE_PUBLIC_ADDRINFO), \
             patch("app.utils.competitor_html.request.build_opener",
                   return_value=Mock(open=Mock(return_value=_fake_urlopen_response(
                       html, "https://docs.example.com/Content/IN/Topic.htm")))):
            response = self.client.post(
                "/api/competitor/url",
                headers=self._auth_headers("writer_user"),
                json={"url": "https://docs.example.com/Content/IN/Topic.htm"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "completed")

        tool_analysis = json.loads(payload["tool_analysis"])
        tool_meta = tool_analysis["meta"]
        self.assertEqual(tool_meta["format"], "HTML")
        self.assertEqual(tool_meta["source_url"], "https://docs.example.com/Content/IN/Topic.htm")
        self.assertEqual(tool_meta["title"], "Sample Manual")

        # Flare 证据链：URL /Content/ + Skins CSS + data-mc 属性 + MadCapAll.js → 高置信
        tools = tool_analysis["tools"]
        self.assertTrue(tools, "应识别出编辑工具")
        self.assertEqual(tools[0]["name"], "MadCap Flare")
        self.assertEqual(tools[0]["confidence"], "high")
        self.assertGreaterEqual(len(tool_analysis.get("html_evidence", [])), 2)

        # 正文去噪：nav/footer 噪声不进正文与报告
        self.assertNotIn("HomeNAV", payload["report_md"])
        self.assertNotIn("FooterLegalBoilerplate", payload["report_md"])
        # v1.1 样本量三档：本样例仅 15 句（<100），报告应标注样本不足而非输出评分
        self.assertIn("样本不足（未评分）", payload["report_md"])
        readability = json.loads(payload["readability"])
        self.assertIsNone(readability.get("overall_score"))
        self.assertEqual(readability.get("level"), "insufficient")
        self.assertTrue(any("样本量不足" in w for w in readability.get("warnings", [])))
        # 正文提取有效：去噪后句子计数与样例一致（5 段 × 3 句）
        self.assertEqual(readability["stats"]["sentence_count"], 15)

        # 不应出现低内容警告（正文抽取本身成功，样本不足≠低内容）
        self.assertFalse(any("文本量较少" in w for w in readability.get("warnings", [])))

        db = self.SessionLocal()
        try:
            tasks = db.query(CompetitorTask).all()
            self.assertEqual(len(tasks), 1)
            self.assertEqual(tasks[0].status, "completed")
            # URL 分析流程的来源类型语义
            self.assertEqual(tasks[0].source_type, "url")
        finally:
            db.close()

    def _seed_completed_task(self, **overrides) -> int:
        """直接落库一条已完成任务，用于报告端点测试。"""
        db = self.SessionLocal()
        try:
            task = CompetitorTask(
                file_name=overrides.get("file_name", "manual.html"),
                file_size=1024,
                status="completed",
                source_type=overrides.get("source_type", "html"),
                user_id=self._current_user_id("writer_user"),
                tool_analysis=overrides.get("tool_analysis", '{"meta": {"format": "HTML"}, "tools": []}'),
                readability=overrides.get("readability", '{"overall_score": 82.5, "level": "good"}'),
                experience=overrides.get("experience", '{"access": {"score": 60.0}}'),
                overall_score=overrides.get("overall_score", 82.5),
                report_md=overrides.get("report_md", "# 竞品文档分析报告\n\n正文。"),
            )
            db.add(task)
            db.commit()
            db.refresh(task)
            return task.id
        finally:
            db.close()

    def _current_user_id(self, username: str) -> int:
        db = self.SessionLocal()
        try:
            user = db.query(User).filter(User.username == username).first()
            return user.id
        finally:
            db.close()

    def test_read_competitor_report_supports_json_format(self):
        """format=json：返回结构化结果（tool_analysis/readability/experience 为已解析对象）。"""
        task_id = self._seed_completed_task()
        response = self.client.get(
            f"/api/competitor/{task_id}/report",
            params={"format": "json"},
            headers=self._auth_headers("writer_user"),
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["format"], "json")

        content = payload["content"]
        self.assertEqual(content["id"], task_id)
        self.assertEqual(content["source_type"], "html")
        self.assertEqual(content["file_name"], "manual.html")
        self.assertEqual(content["overall_score"], 82.5)

        # 字符串字段应解析为对象，而非二次编码的字符串
        self.assertIsInstance(content["tool_analysis"], dict)
        self.assertEqual(content["tool_analysis"]["meta"]["format"], "HTML")
        self.assertIsInstance(content["readability"], dict)
        self.assertEqual(content["readability"]["level"], "good")
        self.assertIsInstance(content["experience"], dict)
        self.assertIn("access", content["experience"])
        # 报告 Markdown 全文以字符串原样返回
        self.assertTrue(content["report_md"].startswith("# 竞品文档分析报告"))

    def test_read_competitor_report_json_falls_back_on_broken_payload(self):
        """format=json：历史脏数据（非法 JSON 字符串）原样返回，不 500。"""
        task_id = self._seed_completed_task(readability="{broken json")
        response = self.client.get(
            f"/api/competitor/{task_id}/report",
            params={"format": "json"},
            headers=self._auth_headers("writer_user"),
        )

        self.assertEqual(response.status_code, 200)
        content = response.json()["content"]
        self.assertEqual(content["readability"], "{broken json")

    def test_upload_html_file_marks_source_type_html(self):
        """本地 HTML 上传：source_type=html（区别于普通文档 file 与网页链接 url）。"""
        body_paragraphs = "\n".join(
            f"<p>Configure the instrument before the first run. Review the safety notes "
            f"and check the sequencing reagents. Step {i} must be completed by a trained "
            f"operator with valid certification before starting the sequencing run.</p>"
            for i in range(1, 6)
        )
        html = f"""
        <html><head><title>Uploaded Manual</title></head><body>
          <main><h1>Quick Start</h1>{body_paragraphs}</main>
        </body></html>
        """.encode("utf-8")

        import tempfile
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("app.api.competitor.UPLOAD_DIR", tmp_dir):
                response = self.client.post(
                    "/api/competitor/",
                    headers=self._auth_headers("writer_user"),
                    files={"file": ("uploaded_manual.html", html, "text/html")},
                )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["source_type"], "html")
        # 上传流程走 HTML 正文抽取：format 应识别为 HTML
        tool_analysis = json.loads(payload["tool_analysis"])
        self.assertEqual(tool_analysis["meta"]["format"], "HTML")
        self.assertIn("uploaded", payload["report_md"])

        db = self.SessionLocal()
        try:
            tasks = db.query(CompetitorTask).all()
            self.assertEqual(len(tasks), 1)
            self.assertEqual(tasks[0].source_type, "html")
        finally:
            db.close()

    def test_create_competitor_task_from_url_flags_low_content_page(self):
        """JS 骨架页：可提取文本过少时应输出低内容警告而非静默误导。"""
        html = b"""
        <html><head><title>Skeleton</title></head><body>
          <nav><a>Menu1</a></nav>
          <main><p>Loading...</p></main>
        </body></html>
        """
        with patch("app.utils.competitor_html.socket.getaddrinfo", return_value=_FAKE_PUBLIC_ADDRINFO), \
             patch("app.utils.competitor_html.request.build_opener",
                   return_value=Mock(open=Mock(return_value=_fake_urlopen_response(
                       html, "https://docs.example.com/skeleton")))):
            response = self.client.post(
                "/api/competitor/url",
                headers=self._auth_headers("writer_user"),
                json={"url": "https://docs.example.com/skeleton"},
            )

        self.assertEqual(response.status_code, 200)
        readability = json.loads(response.json()["readability"])
        self.assertTrue(any("文本量较少" in w or "过少" in w for w in readability.get("warnings", [])))

    def test_create_competitor_task_from_url_rejects_invalid_scheme(self):
        response = self.client.post(
            "/api/competitor/url",
            headers=self._auth_headers("writer_user"),
            json={"url": "ftp://docs.example.com/manual.html"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("http/https", response.json()["detail"])

    def test_create_competitor_task_from_url_rejects_loopback(self):
        """SSRF 防护：禁止访问环回地址。"""
        response = self.client.post(
            "/api/competitor/url",
            headers=self._auth_headers("writer_user"),
            json={"url": "http://127.0.0.1/api/docs"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("公网", response.json()["detail"])

    def test_create_competitor_task_from_url_rejects_private_network(self):
        """SSRF 防护：禁止访问私网地址。"""
        response = self.client.post(
            "/api/competitor/url",
            headers=self._auth_headers("writer_user"),
            json={"url": "http://192.168.1.10/manual.html"},
        )
        self.assertEqual(response.status_code, 400)

    def test_create_competitor_task_from_url_rejects_uncommon_port(self):
        """仅允许 80/443 端口。"""
        response = self.client.post(
            "/api/competitor/url",
            headers=self._auth_headers("writer_user"),
            json={"url": "https://docs.example.com:8443/manual.html"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("端口", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
