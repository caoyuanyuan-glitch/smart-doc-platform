"""已润色文档种子脚本：从 seed/polished/ 目录增量同步到数据库和文件系统"""
import os
import shutil
import uuid
from pathlib import Path
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.polished_document import PolishedDocument

SEED_DIR = Path(__file__).parent / "polished"
TARGET_DIR = Path(__file__).parent.parent / "app" / "static" / "polished"


def cleanup_orphan_polished_documents():
    """清理磁盘文件已不存在的已润色文档 DB 记录。"""
    db = SessionLocal()
    try:
        docs = db.query(PolishedDocument).all()
        orphan_ids = []
        for doc in docs:
            if not doc.file_path or not os.path.exists(doc.file_path):
                orphan_ids.append(doc.id)

        if orphan_ids:
            for oid in orphan_ids:
                db.query(PolishedDocument).filter(PolishedDocument.id == oid).delete()
            db.commit()
            print(f"[seed] 已清理 {len(orphan_ids)} 条无磁盘文件的已润色文档记录")
        else:
            print("[seed] 已润色文档记录完好，无需清理")
    except Exception as e:
        db.rollback()
        print(f"[seed] 已润色文档清理失败: {e}")
        raise
    finally:
        db.close()


def seed_polished_documents():
    """增量同步：种子目录中的已润色文档如在 DB 中不存在则创建，已存在则跳过。"""
    db = SessionLocal()
    try:
        created = _sync_from_seed(db)
        if created:
            db.commit()
            print(f"[seed] 已润色文档增量同步完成，新增 {created} 个条目")
        else:
            print("[seed] 已润色文档已是最新，无新增条目")
    except Exception as e:
        db.rollback()
        print(f"[seed] 已润色文档同步失败: {e}")
        raise
    finally:
        db.close()


def _sync_from_seed(db: Session) -> int:
    """遍历种子目录，创建 DB 中不存在的已润色文档。返回新增数量。"""
    created = 0
    os.makedirs(TARGET_DIR, exist_ok=True)

    if not SEED_DIR.exists():
        return 0

    for date_dir in sorted(SEED_DIR.iterdir()):
        if not date_dir.is_dir() or date_dir.name.startswith("."):
            continue

        for entry in sorted(date_dir.iterdir()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue

            # 子目录名格式: {name}  (去掉了 index 前缀)
            doc_name = entry.name

            # 如果目录下没有 polished 文件，跳过
            polished_files = [f for f in entry.iterdir() if f.is_file() and not f.name.startswith(".") and "_report" not in f.stem]
            if not polished_files:
                continue

            polished_file = polished_files[0]

            # 查找同名文档（已存在则跳过）
            existing = db.query(PolishedDocument).filter(
                PolishedDocument.name == doc_name
            ).first()
            if existing:
                continue

            # 复制到文件系统
            target_dir = TARGET_DIR / date_dir.name
            target_dir.mkdir(parents=True, exist_ok=True)
            target_path = target_dir / f"{uuid.uuid4()}{polished_file.suffix}"
            shutil.copy2(polished_file, target_path)

            # 检查是否有对应的报告文件
            report_file = None
            report_path = None
            for f in entry.iterdir():
                if f.is_file() and "_report" in f.stem:
                    report_file = f
                    report_path = target_dir / f"{uuid.uuid4()}{f.suffix}"
                    shutil.copy2(f, report_path)
                    break

            doc = PolishedDocument(
                name=doc_name,
                filename=target_path.name,
                file_path=str(target_path),
                file_size=os.path.getsize(target_path),
                file_type=polished_file.suffix.lstrip("."),
                report_filename=report_file.name if report_file else None,
                report_file_path=str(report_path) if report_path else None,
                created_by=1,
            )
            db.add(doc)
            created += 1

    return created


def export_polished_to_seed():
    """将数据库中的已润色文档导出到种子目录，用于团队共享。

    目录结构:
      seed/polished/{YYYYMMDD}/{文档名}/
          └── polished.{ext}       # 润色后的文件
          └── report.{ext}         # 润色报告（可选）
    """
    db = SessionLocal()
    try:
        _clean_seed_dir()

        docs = db.query(PolishedDocument).order_by(PolishedDocument.created_at).all()
        exported = 0
        for doc in docs:
            # 跳过文件不存在的文档（文本润色类无物理文件）
            if not doc.file_path or not os.path.exists(doc.file_path):
                continue

            date_str = doc.created_at.strftime("%Y%m%d") if doc.created_at else "unknown"
            doc_dir = SEED_DIR / date_str / doc.name
            doc_dir.mkdir(parents=True, exist_ok=True)

            # 复制润色文件
            ext = os.path.splitext(doc.file_path)[1] or ".docx"
            shutil.copy2(doc.file_path, doc_dir / f"polished{ext}")

            # 复制报告文件（如果有）
            if doc.report_file_path and os.path.exists(doc.report_file_path):
                ext = os.path.splitext(doc.report_file_path)[1] or ".docx"
                shutil.copy2(doc.report_file_path, doc_dir / f"report{ext}")

            exported += 1

        db.commit()
        print(f"[seed] 已润色文档已导出到 {SEED_DIR}，共 {exported} 条")
    except Exception as e:
        db.rollback()
        print(f"[seed] 已润色文档导出失败: {e}")
        raise
    finally:
        db.close()


def _clean_seed_dir():
    """清空种子目录（保留 .gitkeep）"""
    if not SEED_DIR.exists():
        SEED_DIR.mkdir(parents=True, exist_ok=True)
        return

    for root, dirs, files in os.walk(str(SEED_DIR), topdown=False):
        for name in files:
            if name == ".gitkeep":
                continue
            os.remove(os.path.join(root, name))
        if root != str(SEED_DIR):
            try:
                os.rmdir(root)
            except OSError:
                pass
