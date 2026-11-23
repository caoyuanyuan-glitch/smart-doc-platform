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


class KnowledgeRolePermissionTestCase(unittest.TestCase):
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
            resources = Folder(name="资源库", created_by=self.admin_id)
            agent = Folder(name="AI agent知识库", created_by=self.admin_id)
            db.add_all([writing, resources, agent])
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
            agent_file = KnowledgeFile(
                name="skill.md",
                filename="skill.md",
                file_path=self._create_temp_file(".md", b"agent only"),
                file_size=10,
                file_type="md",
                folder_id=agent.id,
                created_by=self.admin_id,
            )
            db.add_all([writing_file, agent_file])
            db.commit()
            return {
                "writing_id": writing.id,
                "resources_id": resources.id,
                "agent_id": agent.id,
                "writing_file_id": writing_file.id,
                "agent_file_id": agent_file.id,
            }
        finally:
            db.close()

    def test_user_only_sees_writing_and_resource_trees(self):
        ids = self._seed_trees()

        tree = self.client.get("/api/knowledge/tree", headers=self._auth_headers("normal_user"))
        self.assertEqual(tree.status_code, 200)
        names = {node["name"] for node in tree.json()}
        self.assertEqual(names, {"写作规范", "资源库"})

        writing = self.client.get(
            f"/api/knowledge/folders/{ids['writing_id']}",
            headers=self._auth_headers("normal_user"),
        )
        self.assertEqual(writing.status_code, 200)
        self.assertEqual(writing.json()["files"][0]["id"], ids["writing_file_id"])

        agent = self.client.get(
            f"/api/knowledge/folders/{ids['agent_id']}",
            headers=self._auth_headers("normal_user"),
        )
        self.assertEqual(agent.status_code, 404)

        preview = self.client.get(
            f"/api/knowledge/files/{ids['writing_file_id']}/preview",
            headers=self._auth_headers("normal_user"),
        )
        self.assertEqual(preview.status_code, 200)

        hidden = self.client.get(
            f"/api/knowledge/files/{ids['agent_file_id']}/preview",
            headers=self._auth_headers("normal_user"),
        )
        self.assertEqual(hidden.status_code, 404)

    def test_admin_sees_agent_knowledge_tree(self):
        ids = self._seed_trees()
        tree = self.client.get("/api/knowledge/tree", headers=self._auth_headers("admin_user"))
        self.assertEqual(tree.status_code, 200)
        names = {node["name"] for node in tree.json()}
        self.assertEqual(names, {"写作规范", "资源库", "AI agent知识库"})

        preview = self.client.get(
            f"/api/knowledge/files/{ids['agent_file_id']}/preview",
            headers=self._auth_headers("admin_user"),
        )
        self.assertEqual(preview.status_code, 200)

    def test_user_cannot_create_root_folder_but_can_edit_visible_files(self):
        ids = self._seed_trees()
        headers = self._auth_headers("normal_user")

        create_root = self.client.post("/api/knowledge/folders", json={"name": "extra"}, headers=headers)
        self.assertEqual(create_root.status_code, 403)

        create_sub = self.client.post(
            "/api/knowledge/folders",
            json={"name": "风格", "parent_id": ids["writing_id"]},
            headers=headers,
        )
        self.assertEqual(create_sub.status_code, 200)

        edit = self.client.put(
            f"/api/knowledge/files/{ids['writing_file_id']}/content",
            json={"content": "changed"},
            headers=headers,
        )
        self.assertEqual(edit.status_code, 200)

        download = self.client.get(
            f"/api/knowledge/files/{ids['writing_file_id']}/download",
            headers=headers,
        )
        self.assertEqual(download.status_code, 200)

        hidden_edit = self.client.put(
            f"/api/knowledge/files/{ids['agent_file_id']}/content",
            json={"content": "nope"},
            headers=headers,
        )
        self.assertEqual(hidden_edit.status_code, 404)
