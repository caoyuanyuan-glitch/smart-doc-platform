"""知识库种子脚本：从 seed/knowledge/ 目录增量同步到数据库和文件系统"""
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
    """增量同步：种子目录中的文件夹/文件如在 DB 中不存在则创建，已存在则跳过。"""
    db = SessionLocal()
    try:
        created = _sync_from_seed(db, SEED_DIR, parent_id=None, parent_path="")
        if created:
            db.commit()
            print(f"[seed] 增量同步完成，新增 {created} 个条目")
        else:
            print("[seed] 知识库已是最新，无新增条目")
    except Exception as e:
        db.rollback()
        print(f"[seed] 种子同步失败: {e}")
        raise
    finally:
        db.close()


def _sync_from_seed(db: Session, current_dir: Path, parent_id: int | None, parent_path: str) -> int:
    """递归遍历种子目录，创建 DB 中不存在的条目。返回新增数量。"""
    created = 0
    os.makedirs(TARGET_DIR, exist_ok=True)

    for entry in sorted(current_dir.iterdir()):
        if entry.name.startswith("."):
            continue

        if entry.is_dir():
            # 查找同名文件夹
            existing_folder = db.query(Folder).filter(
                Folder.name == entry.name,
                Folder.parent_id == parent_id
            ).first()

            if existing_folder:
                folder_id = existing_folder.id
            else:
                folder = Folder(
                    name=entry.name,
                    parent_id=parent_id,
                    created_by=1
                )
                db.add(folder)
                db.flush()
                folder_id = folder.id
                created += 1

            # 递归子目录
            child_path = f"{parent_path}/{entry.name}" if parent_path else entry.name
            created += _sync_from_seed(db, entry, parent_id=folder_id, parent_path=child_path)

        elif entry.is_file():
            if entry.suffix == ".md":
                # 查找同名文件（同一父文件夹下）
                existing_file = db.query(KnowledgeFile).filter(
                    KnowledgeFile.name == entry.name,
                    KnowledgeFile.folder_id == parent_id
                ).first()

                if not existing_file:
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
                    created += 1
            # .gitkeep 等非 .md 文件跳过

    return created


def export_kb_to_seed():
    """将数据库中的知识库导出到种子目录，用于团队共享。
    
    此函数会：
    1. 清空 seed/knowledge 下的旧内容（保留 .gitkeep）
    2. 根据 DB 中的文件夹/文件重建种子目录结构
    3. 复制所有 .md 文件内容到种子目录
    """
    db = SessionLocal()
    try:
        # 清空种子目录（保留 .gitkeep 和 .git 目录）
        for root, dirs, files in os.walk(str(SEED_DIR), topdown=False):
            for name in files:
                if name == ".gitkeep":
                    continue
                os.remove(os.path.join(root, name))
        
        # 重建种子目录：复制 DB 文件夹结构
        root_folders = db.query(Folder).filter(Folder.parent_id == None).all()
        all_folder_ids = {f.id for f in db.query(Folder).all()}
        
        for folder in root_folders:
            _export_folder(db, folder, SEED_DIR)
        
        # 处理孤儿文件夹（parent_id 指向不存在的文件夹）
        orphans = db.query(Folder).filter(
            Folder.parent_id != None,
            ~Folder.parent_id.in_(all_folder_ids)
        ).all()
        if orphans:
            orphan_dir = SEED_DIR / "_orphaned"
            orphan_dir.mkdir(parents=True, exist_ok=True)
            for folder in orphans:
                _export_folder(db, folder, orphan_dir)
                # 修正孤儿的 parent_id 为 None
                folder.parent_id = None
            print(f"[seed] 已处理 {len(orphans)} 个孤儿文件夹")
        
        db.commit()
        print(f"[seed] 知识库已导出到种子目录 {SEED_DIR}")
    except Exception as e:
        db.rollback()
        print(f"[seed] 导出失败: {e}")
        raise
    finally:
        db.close()


def _export_folder(db: Session, folder, parent_seed_dir: Path):
    """递归导出单个文件夹及其下文件到种子目录"""
    folder_dir = parent_seed_dir / folder.name
    folder_dir.mkdir(parents=True, exist_ok=True)
    
    # 导出该文件夹下的文件
    files = db.query(KnowledgeFile).filter(KnowledgeFile.folder_id == folder.id).all()
    has_content = False
    for kf in files:
        if os.path.exists(kf.file_path):
            shutil.copy2(kf.file_path, folder_dir / kf.name)
            has_content = True
    
    # 递归子文件夹
    subfolders = db.query(Folder).filter(Folder.parent_id == folder.id).all()
    for sub in subfolders:
        _export_folder(db, sub, folder_dir)
        has_content = True
    
    # 空文件夹加 .gitkeep 确保 Git 追踪
    if not has_content:
        (folder_dir / ".gitkeep").touch()
