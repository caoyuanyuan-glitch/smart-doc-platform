from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session
from typing import Optional
import os
import mimetypes
import docx2txt
from app.database import get_db
from app.crud.knowledge import (
    get_folder, get_folder_tree, get_folder_files, get_subfolders, create_folder, update_folder, delete_folder,
    create_file, get_file, delete_file
)
from app.schemas.knowledge import FolderCreate, FolderUpdate
from app.api.auth import get_current_user, get_default_user

router = APIRouter()

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "knowledge")

@router.get("/tree")
async def get_knowledge_tree(db: Session = Depends(get_db)):
    tree = get_folder_tree(db, None)
    return tree

@router.get("/folders/{folder_id}")
async def get_folder_content(folder_id: int, db: Session = Depends(get_db)):
    folder = get_folder(db, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="文件夹不存在")
    
    files = get_folder_files(db, folder_id)
    subfolders = get_subfolders(db, folder_id)
    return {
        "folder": {
            "id": folder.id,
            "name": folder.name,
            "parent_id": folder.parent_id,
            "created_at": folder.created_at.isoformat() if folder.created_at else None
        },
        "subfolders": subfolders,
        "files": files
    }

@router.post("/folders", response_model=dict)
async def create_new_folder(
    folder: FolderCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    user = get_default_user(db)
    db_folder = create_folder(db, folder, user.id)
    return {"message": "文件夹创建成功", "id": db_folder.id}

@router.put("/folders/{folder_id}")
async def update_folder_name(
    folder_id: int,
    folder_update: FolderUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    if not folder_update.name:
        raise HTTPException(status_code=400, detail="文件夹名称不能为空")
    
    folder = update_folder(db, folder_id, folder_update.name)
    if not folder:
        raise HTTPException(status_code=404, detail="文件夹不存在")
    
    return {"message": "文件夹重命名成功"}

@router.delete("/folders/{folder_id}")
async def delete_folder_by_id(
    folder_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    user = get_default_user(db)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可删除文件夹和文件")
    
    folder = get_folder(db, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="文件夹不存在")
    
    for file in folder.files:
        if os.path.exists(file.file_path):
            os.remove(file.file_path)
    
    delete_folder(db, folder_id)
    return {"message": "文件夹删除成功"}

@router.post("/folders/{folder_id}/files/upload")
async def upload_file_to_folder(
    folder_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    user = get_default_user(db)
    if not os.path.exists(UPLOAD_DIR):
        os.makedirs(UPLOAD_DIR)
    
    folder = get_folder(db, folder_id) if folder_id else None
    if folder_id and not folder:
        raise HTTPException(status_code=404, detail="文件夹不存在")
    
    file_extension = os.path.splitext(file.filename)[1] if file.filename else ""
    import uuid
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)
    
    content = await file.read()
    with open(file_path, "wb") as buffer:
        buffer.write(content)
    
    file_size = os.path.getsize(file_path)
    file_type = file_extension[1:] if file_extension else "unknown"
    
    from app.schemas.knowledge import FileCreate
    file_data = FileCreate(
        name=file.filename or "unknown",
        folder_id=folder_id if folder_id else None
    )
    
    db_file = create_file(
        db=db,
        file=file_data,
        file_path=file_path,
        filename=file.filename or "unknown",
        file_size=file_size,
        file_type=file_type,
        created_by=user.id
    )
    
    return {"message": "文件上传成功", "id": db_file.id}

@router.get("/files/{file_id}")
async def get_file_info(file_id: int, db: Session = Depends(get_db)):
    file = get_file(db, file_id)
    if not file:
        raise HTTPException(status_code=404, detail="文件不存在")
    
    return {
        "id": file.id,
        "name": file.name,
        "filename": file.filename,
        "file_path": file.file_path,
        "file_size": file.file_size,
        "file_type": file.file_type,
        "folder_id": file.folder_id,
        "created_at": file.created_at.isoformat() if file.created_at else None
    }

@router.get("/files/{file_id}/download")
async def download_file(file_id: int, db: Session = Depends(get_db)):
    file = get_file(db, file_id)
    if not file:
        raise HTTPException(status_code=404, detail="文件不存在")
    
    if not os.path.exists(file.file_path):
        raise HTTPException(status_code=404, detail="服务器文件不存在")
    
    return FileResponse(
        path=file.file_path,
        filename=file.filename,
        media_type="application/octet-stream"
    )

@router.get("/files/{file_id}/preview")
async def preview_file(file_id: int, db: Session = Depends(get_db)):
    file = get_file(db, file_id)
    if not file:
        raise HTTPException(status_code=404, detail="文件不存在")
    
    if not os.path.exists(file.file_path):
        raise HTTPException(status_code=404, detail="服务器文件不存在")
    
    file_type = file.file_type.lower()
    
    # Text-based files - return raw content for syntax highlighting
    if file_type in ["txt", "md", "markdown", "json", "xml", "html", "css", "js", "py", "java", "c", "cpp", "h", "go", "rs"]:
        with open(file.file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"content": content, "type": "text", "file_name": file.filename}
    
    # Images - return direct URL
    elif file_type in ["jpg", "jpeg", "png", "gif", "bmp", "svg", "webp"]:
        return {"file_path": f"/api/knowledge/files/{file_id}/raw", "type": "image", "file_name": file.filename}
    
    # PDF - extract text and return as plain text
    elif file_type == "pdf":
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(file.file_path)
            content = "\n".join([page.extract_text() or "" for page in reader.pages])
            if not content.strip():
                content = "(PDF 文件内容为空或无法提取文字)"
            return {"content": content, "type": "text", "file_name": file.filename}
        except Exception as e:
            return {"content": f"PDF 解析失败: {str(e)}", "type": "error", "file_name": file.filename}
    
    # DOCX - extract text and return as plain text
    elif file_type == "docx":
        try:
            content = docx2txt.process(file.file_path)
            if not content or not content.strip():
                content = "(DOCX 文件内容为空或无法提取文字)"
            return {"content": content, "type": "text", "file_name": file.filename}
        except Exception as e:
            return {"content": f"DOCX 解析失败: {str(e)}", "type": "error", "file_name": file.filename}
    
    else:
        return {"content": "此文件类型不支持在线预览，请下载后查看", "type": "unsupported", "file_name": file.filename}

@router.get("/files/{file_id}/raw")
async def get_raw_file(file_id: int, db: Session = Depends(get_db)):
    """Return raw file for direct browser preview"""
    file = get_file(db, file_id)
    if not file:
        raise HTTPException(status_code=404, detail="文件不存在")
    
    if not os.path.exists(file.file_path):
        raise HTTPException(status_code=404, detail="服务器文件不存在")
    
    media_type = mimetypes.guess_type(file.file_path)[0] or "application/octet-stream"
    
    return FileResponse(
        path=file.file_path,
        filename=file.filename,
        media_type=media_type
    )

@router.delete("/files/{file_id}")
async def delete_file_by_id(
    file_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    user = get_default_user(db)
    file = get_file(db, file_id)
    if not file:
        raise HTTPException(status_code=404, detail="文件不存在")
    
    if user.role != "admin" and file.created_by != user.id:
        raise HTTPException(status_code=403, detail="仅管理员或创建者可删除文件")
    
    if os.path.exists(file.file_path):
        os.remove(file.file_path)
    
    delete_file(db, file_id)
    return {"message": "文件删除成功"}


@router.post("/export-seed")
async def export_knowledge_to_seed(
    current_user = Depends(get_current_user)
):
    """将知识库导出到种子目录，用于 Git 提交后团队共享"""
    from seed.knowledge_seed import export_kb_to_seed
    try:
        export_kb_to_seed()
        return {"message": "知识库已导出到 seed/knowledge/ 目录，请执行 git add/commit/push 分享给团队"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出失败: {str(e)}")
