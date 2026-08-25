from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Query
from typing import List, Optional
from sqlalchemy.orm import Session
import os
import re
import json
import time
import uuid
from datetime import datetime
from html.parser import HTMLParser
from urllib import parse, request

from app.api.auth import get_current_active_user
from app.schemas.user import UserOut
from app.database import get_db
from app.schemas.competitor import CompetitorTask as CompetitorTaskOut
from app.schemas.competitor import CompetitorTaskSummary, CompetitorReport
from app.schemas.competitor import CompetitorUrlAnalyzeRequest

router = APIRouter(dependencies=[Depends(get_current_active_user)])

UPLOAD_DIR = "./static/uploads/competitor"
# 注：仅支持可解析格式；旧版 .doc（二进制）无平台解析器，不列入白名单，避免"通过校验但解析失败"
ALLOWED_EXTS = {".pdf", ".docx", ".md", ".markdown", ".txt", ".html", ".htm"}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB
MAX_REMOTE_HTML_BYTES = 5 * 1024 * 1024  # 5 MB

_MEMORY_TASKS = {}
_MEMORY_NEXT_ID = [1000]

_SAFE_NAME_RE = re.compile(r"[^\w.\-\u4e00-\u9fff]+")


class _HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._chunks = []
        self._title_chunks = []
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        name = tag.lower()
        if name in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return
        if name == "title":
            self._in_title = True
        if name in {"p", "div", "section", "article", "header", "footer", "nav", "main", "aside", "br", "li", "tr", "table", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._chunks.append("\n")

    def handle_endtag(self, tag):
        name = tag.lower()
        if name in {"script", "style", "noscript"} and self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if name == "title":
            self._in_title = False
        if name in {"p", "div", "section", "article", "header", "footer", "nav", "main", "aside", "li", "tr", "table", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._chunks.append("\n")

    def handle_data(self, data):
        if self._skip_depth > 0:
            return
        text = re.sub(r"\s+", " ", data or "").strip()
        if not text:
            return
        self._chunks.append(text)
        self._chunks.append(" ")
        if self._in_title:
            self._title_chunks.append(text)

    def get_text(self) -> str:
        text = "".join(self._chunks)
        text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def get_title(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self._title_chunks)).strip()


def _require_competitor_task_access(db: Session, task_id: int, current_user: UserOut):
    memory_task = _MEMORY_TASKS.get(task_id)
    if memory_task is not None:
        if current_user.role != "admin" and memory_task.get("user_id") != current_user.id:
            raise HTTPException(status_code=404, detail="Task not found")
        return "memory", memory_task

    from app.crud.competitor import get_competitor_task
    try:
        task = get_competitor_task(db, task_id=task_id)
    except Exception:
        task = None
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if current_user.role != "admin" and getattr(task, "user_id", None) != current_user.id:
        raise HTTPException(status_code=404, detail="Task not found")
    return "db", task


def _memory_task_to_response(task: dict) -> dict:
    return {
        "id": task["id"],
        "source_type": task.get("source_type", "file"),
        "file_name": task.get("file_name", ""),
        "file_size": task.get("file_size", 0),
        "status": task.get("status", "pending"),
        "tool_analysis": task.get("tool_analysis"),
        "readability": task.get("readability"),
        "overall_score": task.get("overall_score"),
        "report_md": task.get("report_md"),
        "error": task.get("error"),
        "user_id": task.get("user_id"),
        "created_at": task.get("created_at"),
        "completed_at": task.get("completed_at"),
    }


def _task_value(task, key: str, default=None):
    if isinstance(task, dict):
        return task.get(key, default)
    return getattr(task, key, default)


def _create_memory_task(*, file_name: str, file_size: int, user_id: int, source_type: str) -> dict:
    task_id = _MEMORY_NEXT_ID[0]
    _MEMORY_NEXT_ID[0] += 1
    task = {
        "id": task_id,
        "source_type": source_type,
        "file_name": file_name,
        "file_size": file_size,
        "status": "processing",
        "tool_analysis": None,
        "readability": None,
        "overall_score": None,
        "report_md": None,
        "error": None,
        "user_id": user_id,
        "created_at": datetime.utcnow(),
        "completed_at": None,
        "created_ts": int(time.time()),
    }
    _MEMORY_TASKS[task_id] = task
    return task


def _store_task_result(db: Session, task_ref, *, status: str, tool_analysis=None, readability=None,
                       overall_score=None, report_md=None, error=None, completed_at=None):
    from app.crud.competitor import update_competitor_task

    if isinstance(task_ref, dict):
        task_ref["status"] = status
        if tool_analysis is not None:
            task_ref["tool_analysis"] = json.dumps(tool_analysis, ensure_ascii=False)
        if readability is not None:
            task_ref["readability"] = json.dumps(readability, ensure_ascii=False)
        if overall_score is not None:
            task_ref["overall_score"] = overall_score
        if report_md is not None:
            task_ref["report_md"] = report_md
        if error is not None:
            task_ref["error"] = error
        if completed_at is not None:
            task_ref["completed_at"] = completed_at
        return task_ref

    return update_competitor_task(
        db,
        task_ref.id,
        status=status,
        tool_analysis=tool_analysis,
        readability=readability,
        overall_score=overall_score,
        report_md=report_md,
        error=error,
        completed_at=completed_at,
    )


def _ensure_upload_dir():
    if not os.path.exists(UPLOAD_DIR):
        os.makedirs(UPLOAD_DIR, exist_ok=True)


def _safe_remove(path: str):
    """删除文件，忽略 OSError（清理路径不允许抛出）。"""
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def _sanitize_filename(filename: str) -> str:
    """消毒文件名：仅保留安全字符，限制长度，防止路径穿越。"""
    name = os.path.basename(filename or "").strip()
    name = _SAFE_NAME_RE.sub("_", name)
    name = name.strip("._")
    if not name:
        name = "document"
    return name[:120]


def _normalize_url(input_url: str) -> str:
    raw = (input_url or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="网页链接不能为空")
    parsed = parse.urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="仅支持 http/https 网页链接")
    return raw


def _build_remote_display_name(page_title: str, final_url: str) -> str:
    title = _sanitize_filename(page_title)
    if title:
        return title[:120]
    parsed = parse.urlparse(final_url)
    path_name = os.path.basename(parsed.path.rstrip("/"))
    if path_name:
        return _sanitize_filename(path_name)
    host = parsed.netloc or "web_document"
    return _sanitize_filename(host)


def _extract_html_document(html: str, *, payload_size: int, display_name_hint: str, final_url: str = "") -> dict:
    parser = _HTMLTextExtractor()
    parser.feed(html)
    parser.close()

    full_text = parser.get_text()
    if not full_text:
        raise HTTPException(status_code=422, detail="未能从 HTML 中提取到正文内容")

    title = parser.get_title()
    filename = f"{_build_remote_display_name(title, final_url or display_name_hint)}.html"
    html_hints = {
        "img_count": len(re.findall(r"<img\b", html, flags=re.IGNORECASE)),
        "table_count": len(re.findall(r"<table\b", html, flags=re.IGNORECASE)),
        "madcap_runtime": bool(re.search(r"MadCap(?:All|[:._/-]|\s)", html, flags=re.IGNORECASE)),
        "content_path": "/Content/" in (final_url or display_name_hint),
        "topic_htm": bool(re.search(r"/[^/]+\.htm(?:$|[?#])", final_url or display_name_hint, flags=re.IGNORECASE)),
    }
    source_meta = {
        "format": "HTML",
        "title": title,
        "pages": 1,
        "html_hints": html_hints,
    }
    if final_url:
        source_meta["source_url"] = final_url
        source_meta["producer"] = "Web page"
        source_meta["creator"] = parse.urlparse(final_url).netloc
    else:
        source_meta["producer"] = "Local HTML file"
        source_meta["creator"] = "Uploaded file"

    return {
        "filename": filename,
        "file_size": payload_size,
        "full_text": full_text,
        "pages_text": [full_text],
        "source_meta": source_meta,
    }


def _parse_web_document(source_url: str) -> dict:
    normalized_url = _normalize_url(source_url)
    req = request.Request(
        normalized_url,
        headers={
            "User-Agent": "SmartDocPlatformCompetitorBot/1.0",
            "Accept": "text/html,application/xhtml+xml;q=0.9,text/plain;q=0.5,*/*;q=0.1",
        },
    )
    try:
        with request.urlopen(req, timeout=20) as resp:
            headers = resp.headers
            content_type = (headers.get_content_type() or "").lower()
            if content_type not in {"text/html", "application/xhtml+xml", "text/plain"}:
                raise HTTPException(status_code=400, detail=f"链接内容类型不支持: {content_type or 'unknown'}")
            payload = resp.read(MAX_REMOTE_HTML_BYTES + 1)
            if len(payload) > MAX_REMOTE_HTML_BYTES:
                raise HTTPException(status_code=413, detail="网页内容过大，请换用更短的手册页面")
            charset = headers.get_content_charset() or "utf-8"
            html = payload.decode(charset, errors="replace")
            final_url = resp.geturl() or normalized_url
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"网页抓取失败: {exc}")

    return _extract_html_document(
        html,
        payload_size=len(payload),
        display_name_hint=final_url,
        final_url=final_url,
    )


def _parse_document(file_path: str, filename: str) -> dict:
    """按扩展名分发解析，统一返回 {full_text, pages_text}。"""
    from app.utils import doc_parser
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".pdf":
        result = doc_parser.parse_pdf(file_path)
    elif ext == ".docx":
        result = doc_parser.parse_docx(file_path)
    elif ext in (".md", ".markdown", ".txt"):
        result = doc_parser.parse_markdown(file_path)
    elif ext in (".html", ".htm"):
        with open(file_path, "rb") as f:
            payload = f.read()
        html = payload.decode("utf-8", errors="replace")
        return _extract_html_document(
            html,
            payload_size=len(payload),
            display_name_hint=filename,
        )
    else:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {ext}")
    if not result or not result.get("full_text", "").strip():
        # 透传 doc_parser 的 error 字段（若存在），否则用统一文案
        detail = (result or {}).get("error") or "未能从文档中提取到文本内容，可能为扫描件或文件已损坏"
        raise HTTPException(status_code=422, detail=detail)
    pages_text = result.get("pages_text") or []
    if not pages_text:
        # DOCX/MD/TXT 无"页"概念：以全文作为单页兜底，保证报告页码定位可用
        pages_text = [result["full_text"]]
    return {
        "full_text": result.get("full_text", ""),
        "pages_text": pages_text,
        "source_meta": result.get("source_meta"),
    }


def _source_type_of_filename(filename: str) -> str:
    ext = os.path.splitext(filename or "")[1].lower()
    if ext in {".html", ".htm"}:
        return "html"
    return "file"


def _run_analysis(file_path: str, filename: str, full_text: str, pages_text: list, source_meta: Optional[dict] = None) -> dict:
    """执行竞品分析：编辑工具识别 + 可读性分析 + 报告渲染。"""
    from app.utils.competitor_analysis import (
        analyze_experience,
        analyze_readability,
        analyze_structure_stats,
        analyze_tool_usage,
        enrich_tool_usage,
    )
    from app.utils.competitor_report import render_competitor_report

    tool_analysis = analyze_tool_usage(file_path, full_text, pages_text)
    if source_meta:
        tool_analysis = enrich_tool_usage(tool_analysis, source_meta)
    readability = analyze_readability(full_text, pages_text)
    experience = analyze_experience(file_path, full_text, tool_analysis, pages_text)
    structure_stats = analyze_structure_stats(full_text, source_meta=tool_analysis.get("meta"), readability=readability)
    readability_payload = {
        **readability,
        "structure_stats": structure_stats,
        "access": experience.get("access"),
        "findability": experience.get("findability"),
        "usability": experience.get("usability"),
    }
    try:
        report_md = render_competitor_report(
            filename,
            tool_analysis,
            readability_payload,
            access=experience.get("access"),
            findability=experience.get("findability"),
            usability=experience.get("usability"),
        )
    except Exception as exc:
        # 兜底降级：报告渲染自身异常时用最小模板，保证 status=completed 且报告可下载
        print(f"[competitor] 报告渲染失败，使用兜底模板: {exc}")
        from datetime import datetime
        report_md = (
            "# 竞品文档分析报告\n\n"
            f"- **文档**：{filename}\n"
            f"- **生成时间**：{datetime.now():%Y-%m-%d %H:%M}\n\n"
            "> 分析已完成，但报告渲染过程中出现异常，以下为最小化结果。\n\n"
            f"**编辑工具结论**：{tool_analysis.get('summary', '未知')}\n\n"
            f"**可读性综合评分**：{readability.get('overall_score', 0)} 分"
            f"（{readability.get('level', '未知')}）\n"
        )
    return {
        "tool_analysis": tool_analysis,
        "readability": readability_payload,
        "structure_stats": structure_stats,
        **experience,
        "report_md": report_md,
    }


@router.post("/", response_model=CompetitorTaskOut)
async def create_competitor_task(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: UserOut = Depends(get_current_active_user),
):
    """上传竞品文档并执行分析（同步执行，分析完成后返回完整结果）。"""
    filename = file.filename or ""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"仅支持 {'/'.join(sorted(ALLOWED_EXTS))} 格式",
        )
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="文件内容为空")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"文件大小超过上限（{MAX_UPLOAD_BYTES // (1024 * 1024)} MB）",
        )

    safe_name = _sanitize_filename(filename)
    _ensure_upload_dir()

    source_type = _source_type_of_filename(safe_name)
    from app.crud.competitor import create_competitor_task as db_create
    try:
        task = db_create(
            db,
            file_name=safe_name,
            file_size=len(data),
            user_id=current_user.id,
            source_type=source_type,
        )
    except Exception:
        task = _create_memory_task(
            file_name=safe_name,
            file_size=len(data),
            user_id=current_user.id,
            source_type=source_type,
        )

    task_id = task["id"] if isinstance(task, dict) else task.id
    stored_name = f"{task_id}_{uuid.uuid4().hex[:8]}_{safe_name}"
    stored_path = os.path.join(UPLOAD_DIR, stored_name)
    try:
        with open(stored_path, "wb") as f:
            f.write(data)
    except Exception as exc:
        _safe_remove(stored_path)  # 写盘可能留下部分文件，必须清理
        _store_task_result(db, task, status="failed", error=f"文件保存失败: {exc}")
        raise HTTPException(status_code=500, detail=f"文件保存失败: {exc}")

    try:
        parsed = _parse_document(stored_path, safe_name)
        result = _run_analysis(
            stored_path,
            safe_name,
            parsed["full_text"],
            parsed["pages_text"],
            source_meta=parsed.get("source_meta"),
        )
        _store_task_result(
            db,
            task,
            status="completed",
            tool_analysis=result["tool_analysis"],
            readability=result["readability"],
            overall_score=result["readability"].get("overall_score"),
            report_md=result["report_md"],
            completed_at=datetime.utcnow(),
        )
    except HTTPException:
        _safe_remove(stored_path)
        raise
    except Exception as exc:
        _safe_remove(stored_path)
        _store_task_result(db, task, status="failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"分析失败: {exc}")

    # 分析完成（成功路径）：结果已全量入库，原文件不再需要，及时清理避免磁盘膨胀
    _safe_remove(stored_path)
    if isinstance(task, dict):
        return _memory_task_to_response(task)
    from app.crud.competitor import get_competitor_task
    return get_competitor_task(db, task.id)


@router.post("/url", response_model=CompetitorTaskOut)
async def create_competitor_task_from_url(
    payload: CompetitorUrlAnalyzeRequest,
    db: Session = Depends(get_db),
    current_user: UserOut = Depends(get_current_active_user),
):
    parsed = _parse_web_document(payload.url)

    from app.crud.competitor import create_competitor_task as db_create
    from app.crud.competitor import get_competitor_task
    from app.crud.competitor import update_competitor_task

    try:
        task = db_create(
            db,
            file_name=parsed["filename"],
            file_size=parsed["file_size"],
            user_id=current_user.id,
            source_type="html",
        )
    except Exception:
        task = _create_memory_task(
            file_name=parsed["filename"],
            file_size=parsed["file_size"],
            user_id=current_user.id,
            source_type="html",
        )
    try:
        result = _run_analysis(
            parsed["filename"],
            parsed["filename"],
            parsed["full_text"],
            parsed["pages_text"],
            source_meta=parsed["source_meta"],
        )
        _store_task_result(
            db,
            task,
            status="completed",
            tool_analysis=result["tool_analysis"],
            readability=result["readability"],
            overall_score=result["readability"].get("overall_score"),
            report_md=result["report_md"],
            completed_at=datetime.utcnow(),
        )
    except HTTPException as exc:
        _store_task_result(db, task, status="failed", error=exc.detail)
        raise
    except Exception as exc:
        _store_task_result(db, task, status="failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"分析失败: {exc}")

    if isinstance(task, dict):
        return _memory_task_to_response(task)
    return get_competitor_task(db, task.id)


@router.get("/", response_model=List[CompetitorTaskSummary])
async def read_competitor_tasks(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: UserOut = Depends(get_current_active_user),
): 
    """任务列表：管理员可见全部，普通用户仅可见自己的。"""
    from app.crud.competitor import get_competitor_tasks
    user_id = None if current_user.role == "admin" else current_user.id

    items = []
    try:
        db_tasks = get_competitor_tasks(db, user_id=user_id, skip=0, limit=1000) or []
    except Exception:
        db_tasks = []

    for task in db_tasks:
        items.append(task)

    mem_list = sorted(_MEMORY_TASKS.values(), key=lambda x: x["id"], reverse=True)
    for task in mem_list:
        if current_user.role != "admin" and task.get("user_id") != current_user.id:
            continue
        if any(getattr(item, "id", None) == task["id"] for item in items):
            continue
        items.append(_memory_task_to_response(task))

    items.sort(key=lambda x: x["id"] if isinstance(x, dict) else getattr(x, "id", 0), reverse=True)
    return items[skip: skip + limit]


@router.get("/{task_id}", response_model=CompetitorTaskOut)
async def read_competitor_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: UserOut = Depends(get_current_active_user),
): 
    """任务详情（含工具识别 / 可读性 JSON 与 Markdown 报告全文）。"""
    source, task = _require_competitor_task_access(db, task_id, current_user)
    if source == "memory":
        return _memory_task_to_response(task)
    return task


@router.get("/{task_id}/report", response_model=CompetitorReport)
async def read_competitor_report(
    task_id: int,
    format: str = Query("md", pattern="^(md|text|json)$"),
    db: Session = Depends(get_db),
    current_user: UserOut = Depends(get_current_active_user),
):
    """报告全文（JSON {content, format}，与 compare 报告接口对齐）。"""
    source, task = _require_competitor_task_access(db, task_id, current_user)
    if _task_value(task, "status") != "completed" or not _task_value(task, "report_md"):
        detail = _task_value(task, "error") or "分析尚未完成"
        raise HTTPException(status_code=404, detail=detail)
    if format == "json":
        return {
            "content": {
                "report_md": _task_value(task, "report_md"),
                "tool_analysis": json.loads(_task_value(task, "tool_analysis") or "{}"),
                "readability": json.loads(_task_value(task, "readability") or "{}"),
                "overall_score": _task_value(task, "overall_score"),
                "source_type": _task_value(task, "source_type", "file"),
                "file_name": _task_value(task, "file_name", ""),
            },
            "format": format,
        }
    content = _task_value(task, "report_md", "")
    if format == "text":
        # text 参数需返回纯文本（去 Markdown 标记），避免"标着 text 返回 md"的误导
        from app.utils.competitor_report import markdown_to_text
        content = markdown_to_text(_task_value(task, "report_md", ""))
    return {"content": content, "format": format}


@router.delete("/{task_id}")
async def delete_competitor_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: UserOut = Depends(get_current_active_user),
):
    """删除任务记录与对应上传文件。"""
    source, task = _require_competitor_task_access(db, task_id, current_user)
    if source == "db":
        from app.crud.competitor import delete_competitor_task as db_delete
        db_delete(db, task_id)
    else:
        _MEMORY_TASKS.pop(task_id, None)
    # 清理上传文件（按任务前缀匹配，避免遍历整个上传目录）
    try:
        for name in os.listdir(UPLOAD_DIR):
            if name.startswith(f"{task_id}_"):
                try:
                    os.remove(os.path.join(UPLOAD_DIR, name))
                except OSError:
                    pass
    except OSError:
        pass
    # 对齐 compare 模块删除接口的返回体结构
    return {"message": "Task deleted successfully", "task_id": task_id}
