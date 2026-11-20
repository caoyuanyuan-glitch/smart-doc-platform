"""对比接口异步化单测：默认同步不变 + async_mode 后台执行 + 进度归属。

用 mock 替换 _do_single_compare 避免真实文件解析；仅验证状态机与鉴权。
"""
import unittest
from datetime import datetime
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import compare
from app.api.auth import get_current_active_user
from app.database import get_db
from app.schemas.user import UserOut


class _FakeDB:
    """后台任务自建 SessionLocal 的替身。"""
    def close(self):
        pass


def _fake_user(user_id, role="writer"):
    return UserOut(
        id=user_id, username=f"u{user_id}", display_name=f"u{user_id}",
        role=role, status="active", created_at=datetime.utcnow(),
    )


def _fake_compare(*args, **kwargs):
    return {
        "task_id": 1, "similarity": 0.9, "verdict": "自动通过（>=80%）",
        "total_diffs": 3,
        "file_a_name": args[2] if len(args) > 2 else kwargs.get("file_a_name", ""),
        "file_b_name": args[3] if len(args) > 3 else kwargs.get("file_b_name", ""),
    }


class CompareAsyncProgressTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = FastAPI()
        cls.app.include_router(compare.router, prefix="/api/compare")

        def override_get_db():
            yield object()  # 同步路径不真正用到 db（_do_single_compare 已 mock）

        cls.app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(cls.app)

    def setUp(self):
        compare._COMPARE_PROGRESS.clear()
        self.app.dependency_overrides[get_current_active_user] = lambda: _fake_user(1)

    def tearDown(self):
        compare._COMPARE_PROGRESS.clear()
        self.app.dependency_overrides.pop(get_current_active_user, None)

    @staticmethod
    def _two_files():
        return [
            ("files", ("a.md", b"# doc a\nline one", "text/markdown")),
            ("files", ("b.md", b"# doc b\nline two", "text/markdown")),
        ]

    @patch.object(compare, "_do_single_compare", side_effect=_fake_compare)
    def test_default_sync_unchanged(self, mock_cmp):
        r = self.client.post("/api/compare/", files=self._two_files())
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        self.assertIn("results", data)
        self.assertEqual(data["file_count"], 2)
        self.assertEqual(len(data["results"]), 1)
        self.assertNotIn("status", data)  # 同步响应结构未变

    @patch.object(compare, "_do_single_compare", side_effect=_fake_compare)
    @patch("app.database.SessionLocal", side_effect=lambda: _FakeDB())
    def test_async_mode_returns_running_then_completes(self, mock_session, mock_cmp):
        r = self.client.post("/api/compare/?async_mode=true", files=self._two_files())
        self.assertEqual(r.status_code, 200, r.text)
        created = r.json()
        self.assertEqual(created.get("status"), "running")
        gid = created["group_id"]
        self.assertIsInstance(gid, int)
        self.assertNotIn("results", created)

        # TestClient 在响应完成后执行完 BackgroundTasks，直接查进度应已 completed
        p = self.client.get(f"/api/compare/progress/{gid}")
        self.assertEqual(p.status_code, 200, p.text)
        prog = p.json()
        self.assertEqual(prog["status"], "completed")
        self.assertEqual(prog["progress"], 100)
        self.assertEqual(len(prog["results"]), 1)
        self.assertEqual(prog["results"][0]["verdict"], "自动通过（>=80%）")

    @patch.object(compare, "_do_single_compare", side_effect=_fake_compare)
    @patch("app.database.SessionLocal", side_effect=lambda: _FakeDB())
    def test_progress_owner_scoping(self, mock_session, mock_cmp):
        created = self.client.post("/api/compare/?async_mode=true", files=self._two_files()).json()
        gid = created["group_id"]
        # 切到另一个用户
        self.app.dependency_overrides[get_current_active_user] = lambda: _fake_user(2)
        r = self.client.get(f"/api/compare/progress/{gid}")
        self.assertEqual(r.status_code, 404)

    @patch.object(compare, "_do_single_compare", side_effect=_fake_compare)
    @patch("app.database.SessionLocal", side_effect=lambda: _FakeDB())
    def test_progress_unknown_group(self, mock_session, mock_cmp):
        r = self.client.get("/api/compare/progress/999999")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
