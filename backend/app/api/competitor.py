from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Query
from typing import List, Optional
from sqlalchemy.orm import Session
import os
import re
import uuid
from datetime import datetime

from app.api.auth import get_current_active_user
from app.schemas.user import UserOut
from app.database import get_db
from app.schemas.competitor import CompetitorTask as CompetitorTaskOut
from app.schemas.competitor import CompetitorTaskSummary, CompetitorReport

router = APIRouter(dependencies=[Depends(get_current_active_user)])

UPLOAD_DIR = "./static/uploads/competitor"
# 注：仅支持可解析格式；旧版 .doc（二进制）无平台解析器，不列入白名单，避免"通过校验但解析失败"
ALLOWED_EXTS = {".pdf", ".docx", ".md", ".markdown", ".txt"}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB

_SAFE_NAME_RE = re.compile(r"[^\w.\-\u4e00-\u9fff]+")


def _require_competitor_task_access(db: Session, task_id: int, current_user: UserOut):
    from app.crud.competitor import get_competitor_task
    try:
        task = get_competitor_task(db, task_id=task_id)
    except Exception:
        task = None
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if current_user.role != "admin" and getattr(task, "user_id", None) != current_user.id:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


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
    }


def _run_analysis(file_path: str, filename: str, full_text: str, pages_text: list) -> dict:
    """执行竞品分析：编辑工具识别 + 可读性分析 + 报告渲染。"""
    from app.utils.competitor_analysis import analyze_tool_usage, analyze_readability
    from app.utils.competitor_report import render_competitor_report

    tool_analysis = analyze_tool_usage(file_path, full_text, pages_text)
    readability = analyze_readability(full_text, pages_text)
    try:
        report_md = render_competitor_report(filename, tool_analysis, readability)
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
        "readability": readability,
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

    from app.crud.competitor import create_competitor_task as db_create
    task = db_create(db, file_name=safe_name, file_size=len(data), user_id=current_user.id)

    stored_name = f"{task.id}_{uuid.uuid4().hex[:8]}_{safe_name}"
    stored_path = os.path.join(UPLOAD_DIR, stored_name)
    try:
        with open(stored_path, "wb") as f:
            f.write(data)
    except Exception as exc:
        _safe_remove(stored_path)  # 写盘可能留下部分文件，必须清理
        from app.crud.competitor import update_competitor_task
        update_competitor_task(db, task.id, status="failed", error=f"文件保存失败: {exc}")
        raise HTTPException(status_code=500, detail=f"文件保存失败: {exc}")

    try:
        parsed = _parse_document(stored_path, safe_name)
        result = _run_analysis(stored_path, safe_name, parsed["full_text"], parsed["pages_text"])
        from app.crud.competitor import update_competitor_task
        update_competitor_task(
            db, task.id,
            status="completed",
            tool_analysis=result["tool_analysis"],
            readability=result["readability"],
            report_md=result["report_md"],
            completed_at=datetime.utcnow(),
        )
    except HTTPException:
        _safe_remove(stored_path)
        raise
    except Exception as exc:
        _safe_remove(stored_path)
        from app.crud.competitor import update_competitor_task
        update_competitor_task(db, task.id, status="failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"分析失败: {exc}")

    # 分析完成（成功路径）：结果已全量入库，原文件不再需要，及时清理避免磁盘膨胀
    _safe_remove(stored_path)
    from app.crud.competitor import get_competitor_task
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
    return get_competitor_tasks(db, user_id=user_id, skip=skip, limit=limit)


@router.get("/{task_id}", response_model=CompetitorTaskOut)
async def read_competitor_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: UserOut = Depends(get_current_active_user),
):
    """任务详情（含工具识别 / 可读性 JSON 与 Markdown 报告全文）。"""
    return _require_competitor_task_access(db, task_id, current_user)


@router.get("/{task_id}/report", response_model=CompetitorReport)
async def read_competitor_report(
    task_id: int,
    format: str = Query("md", pattern="^(md|text)$"),
    db: Session = Depends(get_db),
    current_user: UserOut = Depends(get_current_active_user),
):
    """报告全文（JSON {content, format}，与 compare 报告接口对齐）。"""
    task = _require_competitor_task_access(db, task_id, current_user)
    if task.status != "completed" or not task.report_md:
        detail = task.error or "分析尚未完成"
        raise HTTPException(status_code=404, detail=detail)
    content = task.report_md
    if format == "text":
        # text 参数需返回纯文本（去 Markdown 标记），避免"标着 text 返回 md"的误导
        from app.utils.competitor_report import markdown_to_text
        content = markdown_to_text(task.report_md)
    return {"content": content, "format": format}


@router.delete("/{task_id}")
async def delete_competitor_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: UserOut = Depends(get_current_active_user),
):
    """删除任务记录与对应上传文件。"""
    task = _require_competitor_task_access(db, task_id, current_user)
    from app.crud.competitor import delete_competitor_task as db_delete
    db_delete(db, task_id)
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
