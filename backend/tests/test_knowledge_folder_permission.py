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


class KnowledgeFolderPermissionTestCase(unittest.TestCase):
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
        self.writer_id = self._create_user("writer_user", "writer")
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
        return {"Authorization": f"Bearer {token}"}

    def _create_temp_file(self, suffix: str, content: bytes) -> str:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.write(content)
        tmp.close()
        self.temp_paths.append(tmp.name)
        return tmp.name

    def _create_file(self, db, folder_id: int, name: str) -> KnowledgeFile:
        knowledge_file = KnowledgeFile(
            name=name,
            filename=name,
            file_path=self._create_temp_file(".md", b"demo"),
            file_size=4,
            file_type="md",
            permission="edit",
            edit_scope="all",
            folder_id=folder_id,
            created_by=self.writer_id,
        )
        db.add(knowledge_file)
        db.flush()
        return knowledge_file

    def test_folder_permission_requires_admin_and_updates_nested_files(self):
        db = self.SessionLocal()
        try:
            root = Folder(name="root", created_by=self.writer_id)
            db.add(root)
            db.flush()
            child = Folder(name="child", parent_id=root.id, created_by=self.writer_id)
            db.add(child)
            db.flush()
            root_file = self._create_file(db, root.id, "root.md")
            child_file = self._create_file(db, child.id, "child.md")
            db.commit()
            root_id = root.id
            root_file_id = root_file.id
            child_file_id = child_file.id
        finally:
            db.close()

        response = self.client.put(f"/api/knowledge/folders/{root_id}/permission", json={"permission": "read"})
        self.assertEqual(response.status_code, 401)

        response = self.client.put(
            f"/api/knowledge/folders/{root_id}/permission",
            json={"permission": "read"},
            headers=self._auth_headers("writer_user"),
        )
        self.assertEqual(response.status_code, 403)

        response = self.client.put(
            f"/api/knowledge/folders/{root_id}/permission",
            json={"permission": "download", "edit_scope": "owner"},
            headers=self._auth_headers("admin_user"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["updated_count"], 2)
        self.assertEqual(response.json()["permission"], "download")

        db = self.SessionLocal()
        try:
            root_file = db.query(KnowledgeFile).filter(KnowledgeFile.id == root_file_id).one()
            child_file = db.query(KnowledgeFile).filter(KnowledgeFile.id == child_file_id).one()
            self.assertEqual(root_file.permission, "download")
            self.assertEqual(child_file.permission, "download")
            self.assertEqual(root_file.edit_scope, "owner")
            self.assertEqual(child_file.edit_scope, "owner")
        finally:
            db.close()

    def test_folder_permission_rejects_invalid_values(self):
        db = self.SessionLocal()
        try:
            folder = Folder(name="docs", created_by=self.admin_id)
            db.add(folder)
            db.commit()
            folder_id = folder.id
        finally:
            db.close()

        response = self.client.put(
            f"/api/knowledge/folders/{folder_id}/permission",
            json={"permission": "write"},
            headers=self._auth_headers("admin_user"),
        )
        self.assertEqual(response.status_code, 400)
