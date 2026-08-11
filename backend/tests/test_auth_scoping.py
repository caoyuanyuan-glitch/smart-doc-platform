import unittest
import os
import tempfile

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import compare, convert, knowledge, manual_search, rules, translation
from app.api.auth import create_access_token
from app.database import Base, get_db
from app.models.compare_task import CompareTask
from app.models.convert_task import ConvertTask
from app.models.knowledge import KnowledgeFile
from app.models.translation_doc import TranslationDoc
from app.models.user import User


class AuthScopingTestCase(unittest.TestCase):
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
        app.include_router(rules.router, prefix="/api/rules")
        app.include_router(translation.router, prefix="/api/translation")
        app.include_router(convert.router, prefix="/api/convert")
        app.include_router(compare.router, prefix="/api/compare")
        app.include_router(knowledge.router, prefix="/api/knowledge")
        app.include_router(manual_search.router, prefix="/api/manual")

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
        compare._MEMORY_TASKS.clear()
        compare._MEMORY_DIFFS.clear()
        compare._MEMORY_FILES.clear()
        self.admin_id = self._create_user("admin_user", "admin")
        self.writer_id = self._create_user("writer_user", "writer")
        self.other_id = self._create_user("other_user", "writer")
        self.temp_paths = []

    def tearDown(self):
        compare._MEMORY_TASKS.clear()
        compare._MEMORY_DIFFS.clear()
        compare._MEMORY_FILES.clear()
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
        return {"Authorization": f"Bearer {token}"}

    def _create_temp_file(self, suffix: str, content: bytes) -> str:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.write(content)
        tmp.close()
        self.temp_paths.append(tmp.name)
        return tmp.name

    def test_rules_router_requires_admin(self):
        response = self.client.get("/api/rules/")
        self.assertEqual(response.status_code, 401)

        response = self.client.get("/api/rules/", headers=self._auth_headers("writer_user"))
        self.assertEqual(response.status_code, 403)

        response = self.client.get("/api/rules/", headers=self._auth_headers("admin_user"))
        self.assertEqual(response.status_code, 200)

    def test_translation_docs_are_scoped_to_owner(self):
        db = self.SessionLocal()
        try:
            db.add_all([
                TranslationDoc(
                    filename="mine.docx",
                    file_type="docx",
                    source_lang="zh",
                    target_lang="en",
                    engine="hybrid",
                    model="kimi",
                    original_content="a",
                    translated_content="b",
                    original_preview="a",
                    translated_preview="b",
                    user_id=self.writer_id,
                ),
                TranslationDoc(
                    filename="other.docx",
                    file_type="docx",
                    source_lang="zh",
                    target_lang="en",
                    engine="hybrid",
                    model="kimi",
                    original_content="x",
                    translated_content="y",
                    original_preview="x",
                    translated_preview="y",
                    user_id=self.other_id,
                ),
            ])
            db.commit()
            other_doc_id = db.query(TranslationDoc).filter(TranslationDoc.user_id == self.other_id).first().id
        finally:
            db.close()

        response = self.client.get("/api/translation/docs", headers=self._auth_headers("writer_user"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]["filename"], "mine.docx")

        response = self.client.get(f"/api/translation/docs/{other_doc_id}", headers=self._auth_headers("writer_user"))
        self.assertEqual(response.status_code, 404)

        response = self.client.get("/api/translation/stats", headers=self._auth_headers("writer_user"))
        self.assertEqual(response.status_code, 403)

    def test_convert_tasks_are_scoped_to_owner(self):
        db = self.SessionLocal()
        try:
            db.add_all([
                ConvertTask(
                    task_id="conv_owner",
                    source_filename="mine.md",
                    source_format="md",
                    target_format="dita",
                    status="completed",
                    progress=100,
                    user_id=self.writer_id,
                ),
                ConvertTask(
                    task_id="conv_other",
                    source_filename="other.md",
                    source_format="md",
                    target_format="dita",
                    status="completed",
                    progress=100,
                    user_id=self.other_id,
                ),
            ])
            db.commit()
        finally:
            db.close()

        response = self.client.get("/api/convert", headers=self._auth_headers("writer_user"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]["task_id"], "conv_owner")

        response = self.client.get("/api/convert/conv_other/detail", headers=self._auth_headers("writer_user"))
        self.assertEqual(response.status_code, 404)

        response = self.client.get("/api/convert/rules", headers=self._auth_headers("writer_user"))
        self.assertEqual(response.status_code, 403)

    def test_compare_tasks_are_scoped_to_owner(self):
        db = self.SessionLocal()
        try:
            owner_task = CompareTask(
                file_a_name="mine-a.txt",
                file_b_name="mine-b.txt",
                similarity=0.9,
                verdict="ok",
                total_diffs=1,
                diff_stats="{}",
                status="completed",
                user_id=self.writer_id,
            )
            other_task = CompareTask(
                file_a_name="other-a.txt",
                file_b_name="other-b.txt",
                similarity=0.7,
                verdict="review",
                total_diffs=2,
                diff_stats="{}",
                status="completed",
                user_id=self.other_id,
            )
            db.add_all([owner_task, other_task])
            db.commit()
            db.refresh(owner_task)
            db.refresh(other_task)

            compare._MEMORY_TASKS[9001] = {
                "id": 9001,
                "file_a_name": "memory-owner-a.txt",
                "file_b_name": "memory-owner-b.txt",
                "similarity": 1.0,
                "verdict": "ok",
                "total_diffs": 0,
                "diff_stats": "{}",
                "status": "completed",
                "user_id": self.writer_id,
                "created_at": 0,
                "matched_pairs": "[]",
                "only_a": "[]",
                "only_b": "[]",
                "dita_full": "",
            }
            compare._MEMORY_TASKS[9002] = {
                "id": 9002,
                "file_a_name": "memory-other-a.txt",
                "file_b_name": "memory-other-b.txt",
                "similarity": 1.0,
                "verdict": "ok",
                "total_diffs": 0,
                "diff_stats": "{}",
                "status": "completed",
                "user_id": self.other_id,
                "created_at": 0,
                "matched_pairs": "[]",
                "only_a": "[]",
                "only_b": "[]",
                "dita_full": "",
            }
        finally:
            db.close()

        response = self.client.get("/api/compare/", headers=self._auth_headers("writer_user"))
        self.assertEqual(response.status_code, 200)
        ids = {item["id"] for item in response.json()}
        self.assertIn(owner_task.id, ids)
        self.assertIn(9001, ids)
        self.assertNotIn(other_task.id, ids)
        self.assertNotIn(9002, ids)

        response = self.client.get(f"/api/compare/{other_task.id}", headers=self._auth_headers("writer_user"))
        self.assertEqual(response.status_code, 404)

        response = self.client.get("/api/compare/9002", headers=self._auth_headers("writer_user"))
        self.assertEqual(response.status_code, 404)

    def test_knowledge_routes_require_login_and_use_current_user(self):
        file_path = self._create_temp_file(".md", b"hello knowledge")

        db = self.SessionLocal()
        try:
            knowledge_file = KnowledgeFile(
                name="guide.md",
                filename="guide.md",
                file_path=file_path,
                file_size=os.path.getsize(file_path),
                file_type="md",
                permission="edit",
                edit_scope="owner",
                created_by=self.writer_id,
            )
            db.add(knowledge_file)
            db.commit()
            db.refresh(knowledge_file)
            knowledge_file_id = knowledge_file.id
        finally:
            db.close()

        response = self.client.get("/api/knowledge/tree")
        self.assertEqual(response.status_code, 401)

        response = self.client.get(f"/api/knowledge/files/{knowledge_file_id}/download")
        self.assertEqual(response.status_code, 401)

        response = self.client.get(f"/api/knowledge/files/{knowledge_file_id}/preview", headers=self._auth_headers("writer_user"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["type"], "text")

        response = self.client.get(f"/api/knowledge/files/{knowledge_file_id}/raw", headers=self._auth_headers("writer_user"))
        self.assertEqual(response.status_code, 200)

        response = self.client.get(f"/api/knowledge/files/{knowledge_file_id}/content", headers=self._auth_headers("writer_user"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["content"], "hello knowledge")

        response = self.client.delete(f"/api/knowledge/files/{knowledge_file_id}", headers=self._auth_headers("other_user"))
        self.assertEqual(response.status_code, 403)

    def test_manual_uploads_require_login(self):
        response = self.client.get("/api/manual/uploads")
        self.assertEqual(response.status_code, 401)

        response = self.client.get("/api/manual/uploads", headers=self._auth_headers("writer_user"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])


if __name__ == "__main__":
    unittest.main()
