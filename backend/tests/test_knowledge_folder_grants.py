import os
import tempfile
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import knowledge
from app.api.auth import create_access_token
from app.database import Base, get_db
from app.models.knowledge import Folder, KnowledgeFile
from app.models.user import User
from app.utils.knowledge_access import normalize_actions, serialize_actions


class KnowledgeFolderGrantTestCase(unittest.TestCase):
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
        app.include_router(knowledge.router, prefix="/api/knowledge")

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

    def _seed_trees(self):
        db = self.SessionLocal()
        try:
            writing = Folder(name="写作规范", created_by=self.admin_id)
            agent = Folder(name="AI agent知识库", created_by=self.admin_id)
            db.add_all([writing, agent])
            db.flush()
            nested = Folder(name="内部文档", parent_id=agent.id, created_by=self.admin_id)
            db.add(nested)
            db.flush()
            writing_file = KnowledgeFile(
                name="guide.md",
                filename="guide.md",
                file_path=self._create_temp_file(".md", b"hello knowledge"),
                file_size=16,
                file_type="md",
                folder_id=writing.id,
                created_by=self.admin_id,
            )
            nested_file = KnowledgeFile(
                name="secret.md",
                filename="secret.md",
                file_path=self._create_temp_file(".md", b"secret"),
                file_size=6,
                file_type="md",
                folder_id=nested.id,
                created_by=self.admin_id,
            )
            agent_file = KnowledgeFile(
                name="skill.md",
                filename="skill.md",
                file_path=self._create_temp_file(".md", b"agent only"),
                file_size=10,
                file_type="md",
                folder_id=agent.id,
                created_by=self.admin_id,
            )
            db.add_all([writing_file, nested_file, agent_file])
            db.commit()
            return {
                "writing_id": writing.id,
                "agent_id": agent.id,
                "nested_id": nested.id,
                "writing_file_id": writing_file.id,
                "nested_file_id": nested_file.id,
                "agent_file_id": agent_file.id,
            }
        finally:
            db.close()

    def test_action_stacking(self):
        self.assertEqual(normalize_actions(["preview"]), {"read", "preview"})
        self.assertEqual(serialize_actions(["delete"]), "read,preview,download,edit,delete")

    def test_user_cannot_manage_grants(self):
        ids = self._seed_trees()
        response = self.client.get(
            f"/api/knowledge/folders/{ids['agent_id']}/grants",
            headers=self._auth_headers("normal_user"),
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_can_grant_preview_on_hidden_folder(self):
        ids = self._seed_trees()
        admin = self._auth_headers("admin_user")
        user = self._auth_headers("normal_user")

        listed = self.client.get(f"/api/knowledge/folders/{ids['nested_id']}/grants", headers=admin)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["items"][0]["user_id"], self.user_id)

        saved = self.client.put(
            f"/api/knowledge/folders/{ids['nested_id']}/grants",
            json={"grants": [{"user_id": self.user_id, "actions": ["preview"]}]},
            headers=admin,
        )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["items"][0]["actions"], ["preview", "read"])

        tree = self.client.get("/api/knowledge/tree", headers=user)
        self.assertEqual(tree.status_code, 200)
        names = {node["name"] for node in tree.json()}
        self.assertIn("AI agent知识库", names)
        agent_node = next(node for node in tree.json() if node["name"] == "AI agent知识库")
        self.assertEqual(agent_node["files"], [])
        self.assertEqual(agent_node["children"][0]["name"], "内部文档")
        self.assertIn("preview", agent_node["children"][0]["actions"])

        parent = self.client.get(f"/api/knowledge/folders/{ids['agent_id']}", headers=user)
        self.assertEqual(parent.status_code, 200)
        self.assertEqual(parent.json()["files"], [])

        preview = self.client.get(f"/api/knowledge/files/{ids['nested_file_id']}/preview", headers=user)
        self.assertEqual(preview.status_code, 200)

        download = self.client.get(f"/api/knowledge/files/{ids['nested_file_id']}/download", headers=user)
        self.assertEqual(download.status_code, 403)

        hidden = self.client.get(f"/api/knowledge/files/{ids['agent_file_id']}/preview", headers=user)
        self.assertEqual(hidden.status_code, 404)

    def test_nearest_grant_overrides_baseline(self):
        ids = self._seed_trees()
        admin = self._auth_headers("admin_user")
        user = self._auth_headers("normal_user")

        saved = self.client.put(
            f"/api/knowledge/folders/{ids['writing_id']}/grants",
            json={"grants": [{"user_id": self.user_id, "actions": ["read"]}]},
            headers=admin,
        )
        self.assertEqual(saved.status_code, 200)

        edit = self.client.put(
            f"/api/knowledge/files/{ids['writing_file_id']}/content",
            json={"content": "changed"},
            headers=user,
        )
        self.assertEqual(edit.status_code, 403)

        preview = self.client.get(f"/api/knowledge/files/{ids['writing_file_id']}/preview", headers=user)
        self.assertEqual(preview.status_code, 403)

        info = self.client.get(f"/api/knowledge/files/{ids['writing_file_id']}", headers=user)
        self.assertEqual(info.status_code, 200)

    def test_delete_requires_delete_grant(self):
        ids = self._seed_trees()
        admin = self._auth_headers("admin_user")
        user = self._auth_headers("normal_user")

        denied = self.client.delete(f"/api/knowledge/files/{ids['writing_file_id']}", headers=user)
        self.assertEqual(denied.status_code, 403)

        saved = self.client.put(
            f"/api/knowledge/folders/{ids['writing_id']}/grants",
            json={"grants": [{"user_id": self.user_id, "actions": ["delete"]}]},
            headers=admin,
        )
        self.assertEqual(saved.status_code, 200)

        allowed = self.client.delete(f"/api/knowledge/files/{ids['writing_file_id']}", headers=user)
        self.assertEqual(allowed.status_code, 200)

    def test_admin_sets_grants_from_user_management(self):
        ids = self._seed_trees()
        admin = self._auth_headers("admin_user")
        user = self._auth_headers("normal_user")

        tree = self.client.get("/api/knowledge/grant-tree", headers=admin)
        self.assertEqual(tree.status_code, 200)
        names = {node["name"] for node in tree.json()["folders"]}
        self.assertIn("AI agent知识库", names)

        saved = self.client.put(
            f"/api/knowledge/users/{self.user_id}/grants",
            json={"grants": [{"folder_id": ids["nested_id"], "actions": ["download"]}]},
            headers=admin,
        )
        self.assertEqual(saved.status_code, 200)
        nested = next(
            child
            for node in saved.json()["folders"]
            if node["name"] == "AI agent知识库"
            for child in node["children"]
            if child["id"] == ids["nested_id"]
        )
        self.assertEqual(nested["actions"], ["download", "preview", "read"])

        preview = self.client.get(f"/api/knowledge/files/{ids['nested_file_id']}/preview", headers=user)
        self.assertEqual(preview.status_code, 200)
        download = self.client.get(f"/api/knowledge/files/{ids['nested_file_id']}/download", headers=user)
        self.assertEqual(download.status_code, 200)
        edit = self.client.put(
            f"/api/knowledge/files/{ids['nested_file_id']}/content",
            json={"content": "nope"},
            headers=user,
        )
        self.assertEqual(edit.status_code, 403)
