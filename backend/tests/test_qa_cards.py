import os
import tempfile
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import qa
from app.api.auth import get_current_user
from app.crud.knowledge import delete_folder
from app.database import Base, get_db
from app.models.knowledge import Folder, KnowledgeFile, UserKnowledgeGrant
from app.models.qa_card import QaCard, QaCardFolder, QaCardSeedState
from app.models.user import User
from app.utils.knowledge_access import resolve_qa_scope
from app.utils.qa_cards import expand_folder_ids
from app.utils.qa_knowledge_scope import AGENT_KB_ROOT_NAME
from app.utils.qa_scenes import QA_SCENES, build_scene_inventory, seed_default_qa_cards


class CardTestBase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        Base.metadata.create_all(bind=self.engine)

    def tearDown(self):
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def add_folder(self, db, name, parent_id=None):
        folder = Folder(name=name, parent_id=parent_id)
        db.add(folder)
        db.flush()
        return folder

    def add_file(self, db, folder_id, name, path=None, file_type="md"):
        item = KnowledgeFile(
            folder_id=folder_id,
            name=name,
            filename=name,
            file_path=path or f"/tmp/{name}",
            file_type=file_type,
            updated_at=datetime(2026, 11, 20, 10, 0, 0),
        )
        db.add(item)
        db.flush()
        return item

    def add_user(self, db, username, role="user"):
        user = User(
            username=username,
            password_hash="x",
            display_name=username,
            role=role,
            status="active",
        )
        db.add(user)
        db.flush()
        return user

    def build_catalog(self, db):
        writing = self.add_folder(db, "写作规范")
        style = self.add_folder(db, "写作风格指南", writing.id)
        phrase = self.add_folder(db, "句式清单", writing.id)
        resources = self.add_folder(db, "资源库")
        term = self.add_folder(db, "术语库", resources.id)
        memory = self.add_folder(db, "记忆库", resources.id)
        files = self.add_folder(db, "文件资料", resources.id)
        return {
            "writing": writing,
            "style": style,
            "phrase": phrase,
            "resources": resources,
            "term": term,
            "memory": memory,
            "files": files,
        }


class SeedTest(CardTestBase):
    def test_seed_is_idempotent_and_not_restored_after_delete(self):
        db = self.SessionLocal()
        try:
            folders = self.build_catalog(db)
            db.commit()

            self.assertEqual(seed_default_qa_cards(db), 4)
            self.assertEqual(seed_default_qa_cards(db), 0)
            self.assertEqual(db.query(QaCard).count(), 4)

            style_card = db.query(QaCard).filter(QaCard.key == "style").first()
            style_folder_ids = {row.folder_id for row in style_card.folders}
            self.assertIn(folders["style"].id, style_folder_ids)

            files_card = db.query(QaCard).filter(QaCard.key == "files").first()
            self.assertFalse(files_card.home_visible)

            db.query(QaCard).delete()
            db.commit()
            self.assertEqual(seed_default_qa_cards(db), 0)
            self.assertEqual(db.query(QaCard).count(), 0)
            self.assertIsNotNone(db.query(QaCardSeedState).first())
        finally:
            db.close()

    def test_seed_skips_agent_kb_paths(self):
        db = self.SessionLocal()
        try:
            agent = self.add_folder(db, AGENT_KB_ROOT_NAME)
            agent_style = self.add_folder(db, "写作风格指南", agent.id)
            db.commit()

            seed_default_qa_cards(db)
            style_card = db.query(QaCard).filter(QaCard.key == "style").first()
            linked = {row.folder_id for row in style_card.folders}
            self.assertNotIn(agent.id, linked)
            self.assertNotIn(agent_style.id, linked)
        finally:
            db.close()


class InventoryTest(CardTestBase):
    def test_inventory_uses_database_cards_and_nested_folders(self):
        db = self.SessionLocal()
        try:
            folders = self.build_catalog(db)
            nested = self.add_folder(db, "中文", folders["style"].id)
            direct_file = self.add_file(db, folders["style"].id, "风格指南.md")
            nested_file = self.add_file(db, nested.id, "补充说明.md")

            agent = self.add_folder(db, AGENT_KB_ROOT_NAME)
            agent_child = self.add_folder(db, "写作风格指南", agent.id)
            self.add_file(db, agent_child.id, "agent-secret.md")
            db.commit()

            seed_default_qa_cards(db)
            scenes = {item["key"]: item for item in build_scene_inventory(db)}
            style_scene = scenes["style"]
            self.assertEqual(style_scene["folder_count"], 2)
            self.assertEqual(style_scene["file_count"], 2)
            names = {row["name"] for row in style_scene["files"]}
            self.assertEqual(names, {direct_file.name, nested_file.name})

            self.add_file(db, nested.id, "新增资料.md")
            db.commit()
            scenes = {item["key"]: item for item in build_scene_inventory(db)}
            self.assertEqual(scenes["style"]["file_count"], 3)
        finally:
            db.close()

    def test_inventory_reflects_card_create_update_delete(self):
        db = self.SessionLocal()
        try:
            folders = self.build_catalog(db)
            self.add_file(db, folders["term"].id, "术语表.md")
            db.commit()

            card = QaCard(
                key="custom",
                kicker="自定义",
                title="查术语",
                description="",
                accent="#123456",
                suggestions_json="[]",
                home_visible=True,
                sort_order=10,
            )
            db.add(card)
            db.flush()
            db.add(QaCardFolder(card_id=card.id, folder_id=folders["term"].id))
            db.commit()

            scenes = {item["key"]: item for item in build_scene_inventory(db)}
            self.assertEqual(scenes["custom"]["file_count"], 1)

            db.query(QaCardFolder).filter(QaCardFolder.card_id == card.id).delete()
            db.add(QaCardFolder(card_id=card.id, folder_id=folders["files"].id))
            db.commit()
            scenes = {item["key"]: item for item in build_scene_inventory(db)}
            self.assertEqual(scenes["custom"]["file_count"], 0)

            db.delete(card)
            db.commit()
            scenes = {item["key"]: item for item in build_scene_inventory(db)}
            self.assertNotIn("custom", scenes)
        finally:
            db.close()

    def test_deleting_folder_removes_card_association(self):
        db = self.SessionLocal()
        try:
            folders = self.build_catalog(db)
            card = QaCard(
                key="custom",
                kicker="自定义",
                title="临时卡片",
                description="",
                accent="#123456",
                suggestions_json="[]",
                home_visible=True,
                sort_order=10,
            )
            db.add(card)
            db.flush()
            db.add(QaCardFolder(card_id=card.id, folder_id=folders["term"].id))
            db.commit()
            card_id = card.id

            delete_folder(db, folders["term"].id)
            self.assertEqual(db.query(QaCardFolder).filter(QaCardFolder.card_id == card_id).count(), 0)
            self.assertIsNotNone(db.query(QaCard).filter(QaCard.id == card_id).first())
        finally:
            db.close()


class ScopeTest(CardTestBase):
    def test_scope_does_not_include_ungranted_siblings(self):
        db = self.SessionLocal()
        try:
            private = self.add_folder(db, "私密库")
            granted = self.add_folder(db, "可读目录", private.id)
            blocked = self.add_folder(db, "不可读目录", private.id)
            user = self.add_user(db, "reader")
            db.add(UserKnowledgeGrant(
                user_id=user.id,
                folder_id=granted.id,
                actions="read,preview",
                granted_by=1,
            ))
            db.commit()

            scope = resolve_qa_scope(db, user, [private.id])
            self.assertEqual(scope, [granted.id])
            self.assertNotIn(blocked.id, scope)
            self.assertNotIn(private.id, scope)
        finally:
            db.close()

    def test_expand_scope_skips_agent_kb(self):
        db = self.SessionLocal()
        try:
            root = self.add_folder(db, "写作规范")
            child = self.add_folder(db, "子目录", root.id)
            agent = self.add_folder(db, AGENT_KB_ROOT_NAME)
            agent_child = self.add_folder(db, "隐藏", agent.id)
            db.commit()

            ids = expand_folder_ids(db, [root.id, agent.id])
            self.assertIn(root.id, ids)
            self.assertIn(child.id, ids)
            self.assertNotIn(agent.id, ids)
            self.assertNotIn(agent_child.id, ids)
        finally:
            db.close()

    def test_load_qa_documents_only_reads_given_folders(self):
        db = self.SessionLocal()
        temp_dir = tempfile.TemporaryDirectory()
        try:
            root = self.add_folder(db, "私密库")
            allowed = self.add_folder(db, "可读目录", root.id)
            blocked = self.add_folder(db, "不可读目录", root.id)
            allowed_path = os.path.join(temp_dir.name, "allowed.md")
            blocked_path = os.path.join(temp_dir.name, "blocked.md")
            with open(allowed_path, "w", encoding="utf-8") as handle:
                handle.write("允许读取的内容")
            with open(blocked_path, "w", encoding="utf-8") as handle:
                handle.write("不允许读取的内容")
            self.add_file(db, allowed.id, "allowed.md", allowed_path)
            self.add_file(db, blocked.id, "blocked.md", blocked_path)
            db.commit()

            with patch.object(qa, "record_knowledge_file_call", lambda *args, **kwargs: None):
                documents = qa._load_qa_documents(db, [allowed.id])
            self.assertEqual([item["title"] for item in documents], ["allowed.md"])
        finally:
            temp_dir.cleanup()
            db.close()


class CardApiTest(CardTestBase):
    def setUp(self):
        super().setUp()
        self.current_user = SimpleNamespace(id=1, role="admin", username="admin", status="active")
        app = FastAPI()
        app.include_router(qa.router, prefix="/api/qa")

        def override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        def override_user():
            return self.current_user

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_user
        self.client = TestClient(app)

        db = self.SessionLocal()
        try:
            self.folders = self.build_catalog(db)
            self.private_root = self.add_folder(db, "私密库")
            self.private_child = self.add_folder(db, "私有目录", self.private_root.id)
            self.admin = self.add_user(db, "admin", role="admin")
            self.reader = self.add_user(db, "reader", role="user")
            db.commit()
            self.term_id = self.folders["term"].id
            self.memory_id = self.folders["memory"].id
            self.private_root_id = self.private_root.id
            self.private_child_id = self.private_child.id
            self.admin_id = self.admin.id
            self.reader_id = self.reader.id
        finally:
            db.close()

    def payload(self, folder_ids=None, title="自定义卡片"):
        return {
            "title": title,
            "kicker": "自定义",
            "description": "测试说明",
            "accent": "#123456",
            "suggestions": ["问题一", "问题二"],
            "folder_ids": folder_ids or [self.term_id],
            "home_visible": True,
        }

    def test_admin_crud_and_reorder(self):
        create = self.client.post("/api/qa/cards", json=self.payload())
        self.assertEqual(create.status_code, 200, create.text)
        card = create.json()
        self.assertEqual(card["title"], "自定义卡片")
        self.assertEqual(card["folder_ids"], [self.term_id])

        update_payload = self.payload(
            folder_ids=[self.memory_id],
            title="更新后的卡片",
        )
        update_payload["home_visible"] = False
        updated = self.client.put(f"/api/qa/cards/{card['id']}", json=update_payload)
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["title"], "更新后的卡片")
        self.assertFalse(updated.json()["home_visible"])

        cards = self.client.get("/api/qa/cards").json()["cards"]
        self.assertNotIn(card["id"], [item["id"] for item in cards])
        cards = self.client.get("/api/qa/cards", params={"include_hidden": True}).json()["cards"]
        self.assertIn(card["id"], [item["id"] for item in cards])

        deleted = self.client.delete(f"/api/qa/cards/{card['id']}")
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertEqual(self.client.delete(f"/api/qa/cards/{card['id']}").status_code, 404)

    def test_reorder_requires_complete_card_set(self):
        first = self.client.post("/api/qa/cards", json=self.payload(title="第一张")).json()
        second = self.client.post("/api/qa/cards", json=self.payload(title="第二张")).json()

        response = self.client.put("/api/qa/cards/order", json={"card_ids": [second["id"], first["id"]]})
        self.assertEqual(response.status_code, 200, response.text)
        cards = self.client.get("/api/qa/cards", params={"include_hidden": True}).json()["cards"]
        self.assertEqual([item["id"] for item in cards], [second["id"], first["id"]])

        invalid = self.client.put("/api/qa/cards/order", json={"card_ids": [first["id"]]})
        self.assertEqual(invalid.status_code, 400)

    def test_rejects_invalid_payload(self):
        invalid_cases = [
            {**self.payload(), "title": ""},
            {**self.payload(), "folder_ids": []},
            {**self.payload(), "accent": "red"},
            {**self.payload(), "folder_ids": [999999]},
        ]
        for payload in invalid_cases:
            response = self.client.post("/api/qa/cards", json=payload)
            self.assertEqual(response.status_code, 400, payload)

    def test_rejects_agent_kb_folder(self):
        db = self.SessionLocal()
        try:
            agent = self.add_folder(db, AGENT_KB_ROOT_NAME)
            db.commit()
            agent_id = agent.id
        finally:
            db.close()
        response = self.client.post("/api/qa/cards", json=self.payload(folder_ids=[agent_id]))
        self.assertEqual(response.status_code, 400)
        self.assertIn("AI agent知识库", response.json()["detail"])

    def test_normal_user_only_sees_visible_folders(self):
        db = self.SessionLocal()
        try:
            db.add(UserKnowledgeGrant(
                user_id=self.reader_id,
                folder_id=self.private_child_id,
                actions="read,preview",
                granted_by=self.admin_id,
            ))
            card = QaCard(
                key="private",
                kicker="私密",
                title="私密卡片",
                description="",
                accent="#123456",
                suggestions_json="[]",
                home_visible=True,
                sort_order=100,
            )
            db.add(card)
            db.flush()
            db.add(QaCardFolder(card_id=card.id, folder_id=self.private_root_id))
            db.commit()
        finally:
            db.close()

        self.current_user = SimpleNamespace(id=self.reader_id, role="user", username="reader", status="active")
        cards = self.client.get("/api/qa/cards").json()["cards"]
        private = next(item for item in cards if item["key"] == "private")
        self.assertEqual(private["folder_ids"], [self.private_root_id])

        self.assertEqual(self.client.post("/api/qa/cards", json=self.payload()).status_code, 403)
        self.assertEqual(
            self.client.get("/api/qa/cards", params={"include_hidden": True}).status_code,
            403,
        )

    def test_hidden_cards_are_not_returned_to_normal_user(self):
        hidden = self.client.post("/api/qa/cards", json={**self.payload(), "home_visible": False})
        self.assertEqual(hidden.status_code, 200)

        self.current_user = SimpleNamespace(id=self.reader_id, role="user", username="reader", status="active")
        cards = self.client.get("/api/qa/cards").json()["cards"]
        self.assertNotIn(hidden.json()["id"], [item["id"] for item in cards])
