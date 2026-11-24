import shutil
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.knowledge import Folder, KnowledgeFile
from seed import knowledge_seed


class KnowledgeSeedTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.seed_dir = self.tmp / "seed"
        self.target_dir = self.tmp / "runtime"
        self.seed_dir.mkdir()
        self.target_dir.mkdir()

        self._orig_seed = knowledge_seed.SEED_DIR
        self._orig_target = knowledge_seed.TARGET_DIR
        self._orig_session = knowledge_seed.SessionLocal
        knowledge_seed.SEED_DIR = self.seed_dir
        knowledge_seed.TARGET_DIR = self.target_dir

        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        knowledge_seed.SessionLocal = self.SessionLocal

    def tearDown(self):
        knowledge_seed.SEED_DIR = self._orig_seed
        knowledge_seed.TARGET_DIR = self._orig_target
        knowledge_seed.SessionLocal = self._orig_session
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_sync_creates_then_overwrites_changed_file(self):
        folder = self.seed_dir / "资料"
        folder.mkdir()
        (folder / "a.md").write_text("第一版", encoding="utf-8")

        db = self.SessionLocal()
        try:
            stats = {"created": 0, "updated": 0}
            knowledge_seed._sync_from_seed(db, self.seed_dir, None, "", stats)
            db.commit()
            self.assertEqual((stats["created"], stats["updated"]), (2, 0))

            stored = db.query(KnowledgeFile).filter(KnowledgeFile.name == "a.md").one()
            self.assertEqual(Path(stored.file_path).read_text(encoding="utf-8"), "第一版")

            (folder / "a.md").write_text("第二版内容更长一些", encoding="utf-8")
            stats = {"created": 0, "updated": 0}
            knowledge_seed._sync_from_seed(db, self.seed_dir, None, "", stats)
            db.commit()

            self.assertEqual((stats["created"], stats["updated"]), (0, 1))
            db.refresh(stored)
            self.assertEqual(Path(stored.file_path).read_text(encoding="utf-8"), "第二版内容更长一些")
            self.assertEqual(db.query(KnowledgeFile).count(), 1)
        finally:
            db.close()

    def test_export_writes_tree_and_skips_missing_file(self):
        db = self.SessionLocal()
        try:
            root = Folder(name="资源库", parent_id=None)
            db.add(root)
            db.flush()
            content = self.tmp / "upload.md"
            content.write_text("内容", encoding="utf-8")
            db.add(KnowledgeFile(
                name="说明.md",
                folder_id=root.id,
                filename="uuid.md",
                file_path=str(content),
                file_size=content.stat().st_size,
                file_type="md",
            ))
            db.add(KnowledgeFile(
                name="丢失.md",
                folder_id=root.id,
                filename="gone.md",
                file_path=str(self.tmp / "not-exists.md"),
                file_size=0,
                file_type="md",
            ))
            db.commit()

            stats = knowledge_seed.export_kb_to_seed()

            self.assertEqual(stats["copied"], 1)
            self.assertEqual(stats["missing"], 1)
            exported = self.seed_dir / "资源库" / "说明.md"
            self.assertEqual(exported.read_text(encoding="utf-8"), "内容")
            self.assertFalse((self.seed_dir / "资源库" / "丢失.md").exists())
        finally:
            db.close()

    def test_export_refuses_to_wipe_seed_when_db_empty(self):
        sentinel = self.seed_dir / "keep.md"
        sentinel.write_text("保留", encoding="utf-8")

        with self.assertRaises(RuntimeError):
            knowledge_seed.export_kb_to_seed()

        self.assertTrue(sentinel.exists())

    def test_export_preserves_manually_maintained_non_seed_files(self):
        manual = self.seed_dir / "参考" / "baseline.json"
        manual.parent.mkdir(parents=True)
        manual.write_text("{\"keep\": true}", encoding="utf-8")
        (self.seed_dir / "参考" / "stale.md").write_text("旧内容", encoding="utf-8")

        db = self.SessionLocal()
        try:
            db.add(Folder(name="资源库", parent_id=None))
            db.commit()
        finally:
            db.close()

        knowledge_seed.export_kb_to_seed()

        self.assertTrue(manual.exists())
        self.assertFalse((self.seed_dir / "参考" / "stale.md").exists())
        self.assertTrue((self.seed_dir / "资源库").is_dir())


if __name__ == "__main__":
    unittest.main()
