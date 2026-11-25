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
from app.models.knowledge import Folder, KnowledgeFile
from app.models.user import User
from app.utils.qa_knowledge_scope import AGENT_KB_ROOT_NAME
from app.utils.qa_scenes import QA_SCENES, build_scene_inventory


class QaScenesCatalogTest(unittest.TestCase):
    def test_scene_keys_and_paths_match_qa_cards(self):
        mapping = {scene["key"]: [tuple(path) for path in scene["paths"]] for scene in QA_SCENES}
        self.assertEqual(mapping["style"], [
            ("写作规范", "写作风格指南"),
            ("写作规范", "常见错误清单"),
            ("写作规范", "技术文档审核规则库"),
            ("写作规范", "说明书自检checklist"),
            ("写作规范", "审核依据汇总"),
        ])
        self.assertEqual(mapping["phrase"], [
            ("写作规范", "句式清单"),
            ("资源库", "记忆库"),
        ])
        self.assertEqual(mapping["term"], [("资源库", "术语库")])
        self.assertEqual(mapping["files"], [("资源库", "文件资料")])


class QaScenesInventoryTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        Base.metadata.create_all(bind=self.engine)

    def _add_folder(self, db, name, parent_id=None):
        folder = Folder(name=name, parent_id=parent_id)
        db.add(folder)
        db.flush()
        return folder

    def _add_file(self, db, folder_id, name, file_type="md"):
        item = KnowledgeFile(
            folder_id=folder_id,
            name=name,
            filename=name,
            file_path=f"/tmp/{name}",
            file_type=file_type,
            updated_at=datetime(2026, 11, 20, 10, 0, 0),
        )
        db.add(item)
        db.flush()
        return item

    def test_lists_nested_files_and_skips_agent_kb(self):
        db = self.SessionLocal()
        try:
            writing = self._add_folder(db, "写作规范")
            style = self._add_folder(db, "写作风格指南", writing.id)
            nested = self._add_folder(db, "中文", style.id)
            self._add_file(db, style.id, "中文技术文档写作风格指南.md")
            nested_file = self._add_file(db, nested.id, "补充说明.md")

            agent = self._add_folder(db, AGENT_KB_ROOT_NAME)
            agent_child = self._add_folder(db, "写作风格指南", agent.id)
            self._add_file(db, agent_child.id, "agent-secret.md")
            db.commit()

            scenes = {item["key"]: item for item in build_scene_inventory(db)}
            style_scene = scenes["style"]
            names = [row["name"] for row in style_scene["files"]]
            self.assertEqual(style_scene["folder_count"], 2)
            self.assertEqual(style_scene["file_count"], 2)
            self.assertIn("中文技术文档写作风格指南.md", names)
            self.assertIn("补充说明.md", names)
            self.assertNotIn("agent-secret.md", names)
            nested_row = next(row for row in style_scene["files"] if row["id"] == nested_file.id)
            self.assertEqual(nested_row["folder_path"], "写作规范/写作风格指南/中文")
            self.assertEqual(scenes["phrase"]["file_count"], 0)
            self.assertIn("写作规范/句式清单", scenes["phrase"]["missing_paths"])
            self.assertIn("资源库/记忆库", scenes["phrase"]["missing_paths"])
        finally:
            db.close()

    def test_missing_paths_when_catalog_absent(self):
        db = self.SessionLocal()
        try:
            scenes = build_scene_inventory(db)
            self.assertEqual(len(scenes), 4)
            self.assertTrue(all(item["folder_count"] == 0 for item in scenes))
            self.assertTrue(all(item["file_count"] == 0 for item in scenes))
            self.assertEqual(scenes[0]["missing_paths"][0], "写作规范/写作风格指南")
        finally:
            db.close()

    def test_reflects_file_changes_between_calls(self):
        db = self.SessionLocal()
        try:
            writing = self._add_folder(db, "写作规范")
            style = self._add_folder(db, "写作风格指南", writing.id)
            db.commit()

            scenes = {item["key"]: item for item in build_scene_inventory(db)}
            self.assertEqual(scenes["style"]["folder_count"], 1)
            self.assertEqual(scenes["style"]["file_count"], 0)

            self._add_file(db, style.id, "新增指南.md")
            db.commit()

            scenes = {item["key"]: item for item in build_scene_inventory(db)}
            self.assertEqual(scenes["style"]["file_count"], 1)
            self.assertEqual(scenes["style"]["files"][0]["name"], "新增指南.md")
        finally:
            db.close()


class QaScenesApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=cls.engine)
        Base.metadata.create_all(bind=cls.engine)
        cls.current_user = SimpleNamespace(id=1, role="admin", username="admin", status="active")

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
        self.__class__.current_user = SimpleNamespace(id=1, role="admin", username="admin", status="active")
        db = self.SessionLocal()
        try:
            db.add(User(username="admin", password_hash="x", display_name="管理员", role="admin", status="active"))
            db.add(User(username="rolecheck_user", password_hash="x", display_name="普通用户", role="user", status="active"))
            writing = Folder(name="写作规范")
            db.add(writing)
            db.flush()
            style = Folder(name="写作风格指南", parent_id=writing.id)
            db.add(style)
            db.flush()
            db.add(KnowledgeFile(
                folder_id=style.id,
                name="风格指南.md",
                filename="风格指南.md",
                file_path="/tmp/风格指南.md",
                file_type="md",
                updated_at=datetime(2026, 11, 20, 10, 0, 0),
            ))
            db.commit()
        finally:
            db.close()

    def test_admin_reads_scene_sources(self):
        data = self.client.get("/api/qa/scenes/sources").json()
        scenes = {item["key"]: item for item in data["scenes"]}
        self.assertEqual(scenes["style"]["folder_count"], 1)
        self.assertEqual(scenes["style"]["file_count"], 1)
        self.assertEqual(scenes["style"]["files"][0]["name"], "风格指南.md")
        self.assertEqual(scenes["style"]["files"][0]["folder_path"], "写作规范/写作风格指南")
        self.assertEqual(scenes["style"]["files"][0]["file_type"], "md")
        self.assertTrue(scenes["style"]["files"][0]["updated_at"])

    def test_non_admin_is_forbidden(self):
        self.__class__.current_user = SimpleNamespace(id=2, role="user", username="rolecheck_user", status="active")
        response = self.client.get("/api/qa/scenes/sources")
        self.assertEqual(response.status_code, 403)
