from sqlalchemy.orm import Session
from app.models.knowledge import Folder, KnowledgeFile
from app.models.user import User
from app.schemas.knowledge import FolderCreate, FileCreate

def get_folder(db: Session, folder_id: int):
    return db.query(Folder).filter(Folder.id == folder_id).first()

def get_folder_tree(db: Session, parent_id: int = None):
    folders = db.query(Folder).filter(Folder.parent_id == parent_id).all()
    result = []
    for folder in folders:
        folder_dict = {
            "id": folder.id,
            "name": folder.name,
            "parent_id": folder.parent_id,
            "created_by": folder.created_by,
            "created_at": folder.created_at,
            "updated_at": folder.updated_at,
            "children": get_folder_tree(db, folder.id),
            "files": [
                {
                    "id": f.id,
                    "name": f.name,
                    "filename": f.filename,
                    "file_path": f.file_path,
                    "file_size": f.file_size,
                    "file_type": f.file_type,
                    "folder_id": f.folder_id,
                    "created_by": f.created_by,
                    "created_at": f.created_at,
                    "updated_at": f.updated_at
                }
                for f in folder.files
            ]
        }
        result.append(folder_dict)
    return result

def get_folder_files(db: Session, folder_id: int):
    files = db.query(KnowledgeFile).filter(KnowledgeFile.folder_id == folder_id).all()
    # 批量获取用户名映射
    user_ids = {f.created_by for f in files if f.created_by}
    user_map = {}
    if user_ids:
        users = db.query(User).filter(User.id.in_(user_ids)).all()
        user_map = {u.id: u.username for u in users}
    return [
        {
            "id": f.id,
            "name": f.name,
            "filename": f.filename,
            "file_path": f.file_path,
            "file_size": f.file_size,
            "file_type": f.file_type,
            "folder_id": f.folder_id,
            "created_by": f.created_by,
            "created_by_name": user_map.get(f.created_by, "未知用户") if f.created_by else "未知用户",
            "created_at": f.created_at,
            "updated_at": f.updated_at
        }
        for f in files
    ]


def get_subfolders(db: Session, folder_id: int):
    """获取指定文件夹下的所有子文件夹"""
    folders = db.query(Folder).filter(Folder.parent_id == folder_id).all()
    return [
        {
            "id": f.id,
            "name": f.name,
            "parent_id": f.parent_id,
            "created_by": f.created_by,
            "created_at": f.created_at,
            "updated_at": f.updated_at
        }
        for f in folders
    ]

def create_folder(db: Session, folder: FolderCreate, created_by: int):
    db_folder = Folder(
        name=folder.name,
        parent_id=folder.parent_id,
        created_by=created_by
    )
    db.add(db_folder)
    db.commit()
    db.refresh(db_folder)
    return db_folder

def update_folder(db: Session, folder_id: int, name: str):
    folder = get_folder(db, folder_id)
    if folder:
        folder.name = name
        db.commit()
        db.refresh(folder)
    return folder

def move_folder(db: Session, folder_id: int, parent_id: int | None):
    folder = get_folder(db, folder_id)
    if folder:
        folder.parent_id = parent_id
        db.commit()
        db.refresh(folder)
    return folder

def delete_folder(db: Session, folder_id: int):
    folder = get_folder(db, folder_id)
    if folder:
        # 递归删除所有子文件夹
        for child in folder.children:
            delete_folder(db, child.id)
        db.delete(folder)
        db.commit()
    return folder

def create_file(db: Session, file: FileCreate, file_path: str, filename: str, file_size: float, file_type: str, created_by: int):
    db_file = KnowledgeFile(
        name=file.name,
        folder_id=file.folder_id,
        filename=filename,
        file_path=file_path,
        file_size=file_size,
        file_type=file_type,
        created_by=created_by
    )
    db.add(db_file)
    db.commit()
    db.refresh(db_file)
    return db_file

def get_file(db: Session, file_id: int):
    return db.query(KnowledgeFile).filter(KnowledgeFile.id == file_id).first()

def move_file(db: Session, file_id: int, folder_id: int):
    file = get_file(db, file_id)
    if file:
        file.folder_id = folder_id
        db.commit()
        db.refresh(file)
    return file

def delete_file(db: Session, file_id: int):
    file = get_file(db, file_id)
    if file:
        db.delete(file)
        db.commit()
    return file
