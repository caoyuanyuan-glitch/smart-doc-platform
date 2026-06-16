"""知识库种子脚本：从 seed/knowledge/ 目录初始化数据库文件夹和文件"""
import os
import shutil
import uuid
from pathlib import Path
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.knowledge import Folder, KnowledgeFile

SEED_DIR = Path(__file__).parent / "knowledge"
TARGET_DIR = Path(__file__).parent.parent / "app" / "static" / "knowledge"


def seed_knowledge_base():
    """如果数据库中没有知识库文件夹，则从 seed 目录初始化"""
    db = SessionLocal()
    try:
        existing = db.query(Folder).first()
        if existing:
            print("[seed] 知识库已有数据，跳过种子初始化")
            return

        print("[seed] 开始初始化知识库...")
        os.makedirs(TARGET_DIR, exist_ok=True)
        _walk_and_create(db, SEED_DIR, parent_id=None)
        db.commit()
        print("[seed] 知识库种子初始化完成")
    except Exception as e:
        db.rollback()
        print(f"[seed] 种子初始化失败: {e}")
        raise
    finally:
        db.close()


def _walk_and_create(db: Session, current_dir: Path, parent_id: int | None) -> None:
    """递归遍历 seed 目录，创建文件夹和文件"""
    for entry in sorted(current_dir.iterdir()):
        if entry.name.startswith("."):
            continue

        if entry.is_dir():
            # 创建文件夹
            folder = Folder(
                name=entry.name,
                parent_id=parent_id,
                created_by=1  # admin user
            )
            db.add(folder)
            db.flush()  # 获取 folder.id
            _walk_and_create(db, entry, parent_id=folder.id)

        elif entry.is_file() and entry.suffix == ".md":
            # 创建文件：复制到 target 目录并创建数据库记录
            unique_name = f"{uuid.uuid4()}.md"
            target_path = TARGET_DIR / unique_name
            shutil.copy2(entry, target_path)

            file_record = KnowledgeFile(
                name=entry.name,
                folder_id=parent_id,
                filename=unique_name,
                file_path=str(target_path),
                file_size=os.path.getsize(target_path),
                file_type="md",
                created_by=1
            )
            db.add(file_record)
