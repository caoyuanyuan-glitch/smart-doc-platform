from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from sqlalchemy.orm import Session
import os
import json
import time
import zipfile
from app.database import get_db

router = APIRouter()

UPLOAD_DIR = "./static/uploads"

_CONVERT_HISTORY = []


def _ensure_upload_dir():
    if not os.path.exists(UPLOAD_DIR):
        os.makedirs(UPLOAD_DIR, exist_ok=True)


def _markdown_to_dita(content: str) -> str:
    import re

    lines = content.split("\n") if content else []
    body_lines = []
    in_list = False

    def close_list():
        nonlocal in_list, body_lines
        if in_list:
            body_lines.append("    </ul>")
            in_list = False

    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            close_list()
            continue
        if line.startswith("### "):
            close_list()
            body_lines.append(f'    <section><title>{line[4:]}</title></section>')
        elif line.startswith("## "):
            close_list()
            body_lines.append(f'    <section><title>{line[3:]}</title></section>')
        elif line.startswith("# "):
            close_list()
            body_lines.append(f'    <section><title>{line[2:]}</title></section>')
        elif re.match(r"^\s*[-*+]\s+", line):
            if not in_list:
                body_lines.append("    <ul>")
                in_list = True
            item = re.sub(r"^\s*[-*+]\s+", "", line)
            body_lines.append(f"      <li>{item}</li>")
        elif re.match(r"^\s*\d+\.\s+", line):
            if not in_list:
                body_lines.append("    <ol>")
                in_list = True
            item = re.sub(r"^\s*\d+\.\s+", "", line)
            body_lines.append(f"      <li>{item}</li>")
        else:
            close_list()
            body_lines.append(f"    <p>{line}</p>")
    close_list()

    body = "\n".join(body_lines)
    dita = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">
<topic id="generated-topic">
  <title>Generated Document</title>
  <body>
{body}
  </body>
</topic>
"""
    return dita


def _docx_to_text_fallback(path: str) -> str:
    try:
        with open(path, "rb") as f:
            data = f.read()
        try:
            text = data.decode("utf-8", errors="ignore")
        except Exception:
            text = ""
        return text.strip() or "（无法解析该 DOCX 内容，已作为文本保存）"
    except Exception:
        return ""


def _safe_read_upload(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return ""


def _record_history(source: str, filename: str, download_url: str):
    _CONVERT_HISTORY.insert(0, {
        "id": int(time.time() * 1000) + len(_CONVERT_HISTORY),
        "source": source,
        "filename": filename,
        "download_url": download_url,
        "status": "completed",
        "created_at": int(time.time()),
    })
    if len(_CONVERT_HISTORY) > 200:
        _CONVERT_HISTORY[:] = _CONVERT_HISTORY[:200]


@router.post("/md2dita")
async def convert_md_to_dita(file: UploadFile = File(...), db: Session = Depends(get_db)):
    _ensure_upload_dir()
    file_path = os.path.join(UPLOAD_DIR, f"{int(time.time() * 1000)}_{file.filename}")
    output_path = os.path.join(UPLOAD_DIR, f"md2dita_{int(time.time() * 1000)}.zip")

    try:
        with open(file_path, "wb") as buffer:
            buffer.write(await file.read())
    except Exception:
        if os.path.exists(file_path):
            try: os.remove(file_path)
            except Exception: pass
        raise HTTPException(status_code=500, detail="Upload failed")

    try:
        content = _safe_read_upload(file_path)
        try:
            from app.utils.document_parser import parse_markdown
            parsed = parse_markdown(file_path)
            if parsed:
                content = parsed
        except Exception:
            pass
        if not content:
            content = "# 空文档\n\n未识别到有效内容。"

        dita = _markdown_to_dita(content)

        try:
            with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("output.dita", dita)
        except Exception:
            with zipfile.ZipFile(output_path, "w") as zf:
                zf.writestr("output.dita", dita)

        download_url = f"/static/uploads/{os.path.basename(output_path)}"
        try: os.remove(file_path)
        except Exception: pass
        _record_history("md2dita", file.filename, download_url)

        return {
            "message": "Conversion completed",
            "download_url": download_url,
            "source": "md2dita",
            "filename": file.filename,
        }
    except Exception as exc:
        if os.path.exists(file_path):
            try: os.remove(file_path)
            except Exception: pass
        if os.path.exists(output_path):
            try: os.remove(output_path)
            except Exception: pass
        dita = _markdown_to_dita(f"# 转换失败（备用）\n\n{str(exc)}")
        try:
            with zipfile.ZipFile(output_path, "w") as zf:
                zf.writestr("output.dita", dita)
            download_url = f"/static/uploads/{os.path.basename(output_path)}"
            _record_history("md2dita", file.filename, download_url)
            return {
                "message": "Conversion completed (fallback)",
                "download_url": download_url,
                "source": "md2dita",
                "filename": file.filename,
                "error": str(exc),
            }
        except Exception:
            raise HTTPException(status_code=500, detail=str(exc))


@router.post("/docx2dita")
async def convert_docx_to_dita(file: UploadFile = File(...), db: Session = Depends(get_db)):
    _ensure_upload_dir()
    file_path = os.path.join(UPLOAD_DIR, f"{int(time.time() * 1000)}_{file.filename}")
    output_path = os.path.join(UPLOAD_DIR, f"docx2dita_{int(time.time() * 1000)}.zip")

    try:
        with open(file_path, "wb") as buffer:
            buffer.write(await file.read())
    except Exception:
        if os.path.exists(file_path):
            try: os.remove(file_path)
            except Exception: pass
        raise HTTPException(status_code=500, detail="Upload failed")

    try:
        content = ""
        try:
            from app.utils.document_parser import parse_docx
            content = parse_docx(file_path) or ""
        except Exception:
            content = _docx_to_text_fallback(file_path)
        if not content:
            content = "# 文档\n\n（未识别到可读内容）"

        dita = _markdown_to_dita(content)

        try:
            with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("output.dita", dita)
        except Exception:
            with zipfile.ZipFile(output_path, "w") as zf:
                zf.writestr("output.dita", dita)

        download_url = f"/static/uploads/{os.path.basename(output_path)}"
        try: os.remove(file_path)
        except Exception: pass
        _record_history("docx2dita", file.filename, download_url)

        return {
            "message": "Conversion completed",
            "download_url": download_url,
            "source": "docx2dita",
            "filename": file.filename,
        }
    except Exception as exc:
        if os.path.exists(file_path):
            try: os.remove(file_path)
            except Exception: pass
        if os.path.exists(output_path):
            try: os.remove(output_path)
            except Exception: pass
        dita = _markdown_to_dita(f"# 转换失败（备用）\n\n{str(exc)}")
        try:
            with zipfile.ZipFile(output_path, "w") as zf:
                zf.writestr("output.dita", dita)
            download_url = f"/static/uploads/{os.path.basename(output_path)}"
            _record_history("docx2dita", file.filename, download_url)
            return {
                "message": "Conversion completed (fallback)",
                "download_url": download_url,
                "source": "docx2dita",
                "filename": file.filename,
                "error": str(exc),
            }
        except Exception:
            raise HTTPException(status_code=500, detail=str(exc))


@router.get("/history")
async def get_history(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    db_items = []
    try:
        from app.crud.compare import get_compare_tasks as _noop
        _ = _noop
    except Exception:
        pass
    items = list(_CONVERT_HISTORY)
    return items[skip: skip + limit]
