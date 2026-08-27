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
from app.schemas.competitor import CompetitorUrlAnalyzeRequest
from app.schemas.competitor import (
    CompetitorComparison as CompetitorComparisonOut,
    CompetitorComparisonSummary,
    CompetitorComparisonCreate,
)

router = APIRouter(dependencies=[Depends(get_current_active_user)])

UPLOAD_DIR = "./static/uploads/competitor"
# 注：仅支持可解析格式；旧版 .doc（二进制）无平台解析器，不列入白名单，避免"通过校验但解析失败"
# 本地 HTML 上传（需求 V1.2 §4.1 P1）：用于 JS 渲染/受限站点人工保存页面后上传分析
ALLOWED_EXTS = {".pdf", ".docx", ".md", ".markdown", ".txt", ".html", ".htm"}
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


def _normalize_url(input_url: str) -> str:
    """URL 校验（含 SSRF 防护）由 utils.competitor_html.assert_public_http_url 承担。"""
    from app.utils.competitor_html import UrlNotAllowedError, assert_public_http_url
    try:
        return assert_public_http_url(input_url)
    except UrlNotAllowedError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def _build_remote_display_name(page_title: str, final_url: str) -> str:
    from urllib import parse
    title = _sanitize_filename(page_title)
    if title:
        return title[:120]
    parsed = parse.urlparse(final_url)
    path_name = os.path.basename(parsed.path.rstrip("/"))
    if path_name:
        return _sanitize_filename(path_name)
    host = parsed.netloc or "web_document"
    return _sanitize_filename(host)


def _parse_web_document(source_url: str) -> dict:
    """递归抓取网页站点（全站子页面/topic）并完成正文汇总与抽取。

    用户裁定（2026-08-24）：所有子页面、子 topic 都需要爬取，不只是入口页面。
    返回 pages_html（各页完整 HTML，供体验三维度页级聚合），不落库。
    """
    from app.utils import competitor_crawl, competitor_html

    _normalize_url(source_url)  # 预校验，给出明确的 400 文案
    try:
        crawl = competitor_crawl.crawl_site(source_url)
    except competitor_html.UrlNotAllowedError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if not crawl["combined_text"].strip():
        # 全站均无可提取正文（纯 JS 渲染/空骨架）：与单页口径一致，明确报错
        raise HTTPException(status_code=422, detail="未能从网页中提取到正文内容（可能为纯 JS 渲染页面）")

    final_url = crawl["final_url"]
    full_text = crawl["combined_text"]
    pages_text = [p["full_text"] for p in crawl["pages"] if p["full_text"]]
    # 入口页（pages[0]）重新抽取完整资产特征（脚本/样式/生成器），供工具识别证据链
    entry_html = crawl["pages"][0]["html"]
    entry_extraction = competitor_html.extract_main_text(entry_html)
    title = entry_extraction.get("title", "") or crawl["pages"][0].get("title", "")
    display_name = _build_remote_display_name(title, final_url)
    from urllib import parse
    # 入口页/封面页识别（外部评审 P1 采纳项）：命中时并入 warnings，报告显著提示
    entry_hints = competitor_html.entry_page_hints(final_url, full_text)
    warnings = list(entry_extraction.get("notes", [])) + entry_hints
    # 结构统计用全站累加（替换单页计数）
    struct = crawl["structure"]
    html_context = {
        "final_url": final_url,
        "html": entry_html[:200000],  # 证据检测仅需要头部与资产引用，截断防止超量存储
        "extraction": {
            "script_srcs": entry_extraction.get("script_srcs"),
            "css_hrefs": entry_extraction.get("css_hrefs"),
            "attrs_sample": entry_extraction.get("attrs_sample"),
            "generator": entry_extraction.get("generator"),
            "low_content": entry_extraction.get("low_content"),
            "notes": entry_extraction.get("notes"),
            "page_count": crawl["ok"],
            "img_count": struct["img_count"],
            "table_count": struct["table_count"],
            "heading_count": struct["heading_count"],
            "warning_symbol_count": struct["warning_symbol_count"],
            "warning_count": struct["warning_count"],
        },
        "crawl": {
            "ok": crawl["ok"],
            "failed": crawl["failed"],
            "total": crawl["total"],
            "skipped": crawl["skipped"],
            "dedup": crawl["dedup"],
            "max_depth": crawl["pages"][-1]["depth"] if crawl["pages"] else 1,
        },
    }
    return {
        "filename": f"{display_name}.html",
        "file_size": sum(len(p["html"]) for p in crawl["pages"]),
        "full_text": full_text,
        "pages_text": pages_text,
        "pages_html": [p["html"] for p in crawl["pages"]],  # 内存字段，不落库
        "source_meta": {
            "format": "HTML",
            "title": title,
            "source_url": final_url,
            "producer": "Web page",
            "creator": parse.urlparse(final_url).netloc,
            "generator": entry_extraction.get("generator", ""),
            "pages": crawl["ok"],
        },
        "html_context": html_context,
        "warnings": warnings,
    }


def _parse_document(file_path: str, filename: str) -> dict:
    """按扩展名分发解析，统一返回 {full_text, pages_text, html_context?}。"""
    from app.utils import doc_parser
    ext = os.path.splitext(filename)[1].lower()
    html_context = None
    warnings = []
    if ext == ".pdf":
        result = doc_parser.parse_pdf(file_path)
    elif ext == ".docx":
        result = doc_parser.parse_docx(file_path)
    elif ext in (".md", ".markdown", ".txt"):
        result = doc_parser.parse_markdown(file_path)
    elif ext in (".html", ".htm"):
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                html = f.read()
        except OSError as exc:
            raise HTTPException(status_code=422, detail=f"HTML 文件读取失败: {exc}")
        from app.utils import competitor_html
        extraction = competitor_html.extract_main_text(html)
        result = {"full_text": extraction.get("full_text", ""), "pages_text": []}
        if not result["full_text"]:
            raise HTTPException(
                status_code=422,
                detail="未能从 HTML 中提取到正文内容（可能为纯 JS 渲染页面）",
            )
        html_context = {
            "final_url": "",
            "html": html[:200000],
            "extraction": {
                k: extraction.get(k)
                for k in ("script_srcs", "css_hrefs", "attrs_sample", "generator", "low_content", "notes",
                          "img_count", "table_count", "heading_count", "warning_symbol_count")
            },
        }
        # 本地 HTML 也可能为入口页（无 URL 路径特征时按全文长度判定）
        warnings = list(extraction.get("notes", [])) + competitor_html.entry_page_hints("", result["full_text"])
    else:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {ext}")
    if not result or not result.get("full_text", "").strip():
        # 透传 doc_parser 的 error 字段（若存在），否则用统一文案
        detail = (result or {}).get("error") or "未能从文档中提取到文本内容，可能为扫描件或文件已损坏"
        raise HTTPException(status_code=422, detail=detail)
    pages_text = result.get("pages_text") or []
    if not pages_text:
        # DOCX/MD/TXT/HTML 无"页"概念：以全文作为单页兜底，保证报告页码定位可用
        pages_text = [result["full_text"]]
    return {
        "full_text": result.get("full_text", ""),
        "pages_text": pages_text,
        "html_context": html_context,
        "warnings": warnings,
    }


def _merge_html_tool_analysis(tool_analysis: dict, html_context: Optional[dict]) -> None:
    """将 HTML 工具识别证据链（MadCap Flare 等）并入 tool_analysis。"""
    if not html_context:
        return
    from app.utils import competitor_html
    detection = competitor_html.detect_html_tool(
        html_context.get("final_url", ""),
        html_context.get("extraction") or {},
        html_context.get("html", ""),
    )
    tools = detection.get("tools", [])
    if tools:
        tool_analysis["tools"] = tools
        tool_analysis["summary"] = detection["summary"]
    tool_analysis["html_evidence"] = detection.get("evidence", [])


def _run_analysis(file_path: str, filename: str, full_text: str, pages_text: list,
                  source_meta: Optional[dict] = None,
                  html_context: Optional[dict] = None,
                  warnings: Optional[list] = None,
                  pages_html: Optional[list] = None) -> dict:
    """执行竞品分析：编辑工具识别 + 可读性分析 + 体验三维度 + 结构统计 + 报告渲染。

    pages_html（全站递归爬取场景）：各页完整 HTML，供体验三维度页级聚合（不落库）。
    """
    from app.utils.competitor_analysis import analyze_tool_usage, analyze_readability, analyze_structure
    from app.utils.competitor_experience import analyze_experience
    from app.utils.competitor_report import render_competitor_report

    tool_analysis = analyze_tool_usage(file_path, full_text, pages_text)
    if source_meta:
        merged_meta = dict(tool_analysis.get("meta") or {})
        merged_meta.update({k: v for k, v in (source_meta or {}).items() if v not in (None, "")})
        tool_analysis["meta"] = merged_meta
    _merge_html_tool_analysis(tool_analysis, html_context)
    # 结构统计（客观指标）：失败不影响主流程，降级为空统计并在 notes 说明
    try:
        tool_analysis["structure_stats"] = analyze_structure(
            file_path, full_text, pages_text,
            html_extraction=(html_context or {}).get("extraction"),
        )
    except Exception as exc:
        print(f"[competitor] 结构统计失败（降级为空）: {exc}")
        tool_analysis["structure_stats"] = {"notes": [f"结构统计失败: {exc}"]}
    readability = analyze_readability(full_text, pages_text)
    # 体验三维度（需求说明书 V1.2 §3.3-3.5）：可获得性/易查找性/可用性（DQTI 理论）
    # 失败不影响主流程：降级为空结果，报告缺三章节
    try:
        experience = analyze_experience(
            file_path, full_text, pages_text,
            html=(html_context or {}).get("html"),
            final_url=(html_context or {}).get("final_url", ""),
            pages_html=pages_html,
        )
    except Exception as exc:
        print(f"[competitor] 体验维度分析失败（降级为空）: {exc}")
        experience = {"error": f"体验维度分析失败: {exc}"}
    # 合并抽取阶段警告（正文过少/JS 渲染受限）到可读性结果，统一由报告渲染输出
    merged_warnings = list(readability.get("warnings") or [])
    for w in warnings or []:
        if w not in merged_warnings:
            merged_warnings.append(w)
    if merged_warnings:
        readability["warnings"] = merged_warnings
    # 洞察引擎（需求缺口1）：分数 → 对本司的可执行启示；规则层保底，AI 层可选降级
    from app.utils.competitor_insight import generate_insights
    try:
        readability["insights"] = generate_insights(tool_analysis, readability, experience)
    except Exception as exc:
        # 洞察失败不能影响分析主流程：降级为空洞察，报告仅缺"启示"章节
        print(f"[competitor] 洞察生成失败（降级为空）: {exc}")
        readability["insights"] = {"insights": [], "ai_available": False}
    try:
        report_md = render_competitor_report(filename, tool_analysis, readability, experience)
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
        "experience": experience,
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
        result = _run_analysis(
            stored_path, safe_name,
            parsed["full_text"], parsed["pages_text"],
            html_context=parsed.get("html_context"),
            warnings=parsed.get("warnings"),
        )
        from app.crud.competitor import update_competitor_task
        update_competitor_task(
            db, task.id,
            status="completed",
            tool_analysis=result["tool_analysis"],
            readability=result["readability"],
            experience=result["experience"],
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

    task = db_create(
        db,
        file_name=parsed["filename"],
        file_size=parsed["file_size"],
        user_id=current_user.id,
    )
    try:
        result = _run_analysis(
            parsed["filename"],
            parsed["filename"],
            parsed["full_text"],
            parsed["pages_text"],
            source_meta=parsed["source_meta"],
            html_context=parsed.get("html_context"),
            warnings=parsed.get("warnings"),
            pages_html=parsed.get("pages_html"),
        )
        update_competitor_task(
            db,
            task.id,
            status="completed",
            tool_analysis=result["tool_analysis"],
            readability=result["readability"],
            experience=result["experience"],
            report_md=result["report_md"],
            completed_at=datetime.utcnow(),
        )
    except HTTPException as exc:
        update_competitor_task(db, task.id, status="failed", error=exc.detail)
        raise
    except Exception as exc:
        update_competitor_task(db, task.id, status="failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"分析失败: {exc}")

    return get_competitor_task(db, task.id)


@router.post("/compare", response_model=CompetitorComparisonOut)
async def create_competitor_comparison(
    payload: CompetitorComparisonCreate,
    db: Session = Depends(get_db),
    current_user: UserOut = Depends(get_current_active_user),
):
    """创建多文档对比（2-5 个已完成分析任务，可选其一为我方基线）。

    路由声明在 GET /{task_id} 之前，避免路径参数吞掉 /compare。
    """
    task_ids = payload.task_ids or []
    if len(task_ids) < 2 or len(task_ids) > 5:
        raise HTTPException(status_code=400, detail="参与对比的任务数须为 2-5 个")
    # 元素必须是整数 ID（Pydantic list 未约束元素类型，防止 dict 等不可哈希类型打穿 set()）
    if any(not isinstance(t, int) or isinstance(t, bool) for t in task_ids):
        raise HTTPException(status_code=400, detail="task_ids 必须为整数任务 ID 列表")
    if len(set(task_ids)) != len(task_ids):
        raise HTTPException(status_code=400, detail="参与对比的任务存在重复")

    from app.crud.competitor import get_competitor_task
    tasks = []
    for tid in task_ids:
        task = get_competitor_task(db, task_id=tid)
        if not task or (current_user.role != "admin" and task.user_id != current_user.id):
            raise HTTPException(status_code=404, detail=f"任务不存在: {tid}")
        if task.status != "completed" or not task.readability:
            raise HTTPException(status_code=400, detail=f"任务 {tid} 未完成分析，无法参与对比")
        tasks.append(task)

    from app.utils.competitor_comparison import (
        load_task_payloads, build_comparison, render_comparison_report,
    )
    payloads = load_task_payloads(tasks)
    # 先剔除损坏 JSON 再校验数量：若此时剩 <2 条，根因是"结果损坏"而非"任务数不足"，
    # 用 422 + 明确文案，避免误导排障
    if len(payloads) < 2:
        broken = len(tasks) - len(payloads)
        raise HTTPException(
            status_code=422,
            detail=f"{broken} 个任务的分析结果损坏（JSON 解析失败），无法对比",
        )
    try:
        result, insights = build_comparison(payloads, payload.baseline_task_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    warnings = []
    for p in payloads:
        for w in p.get("warnings") or []:
            item = f"「{p['name']}」{w}"
            if item not in warnings:
                warnings.append(item)

    title = ((payload.title or "").strip() or "竞品文档对比")[:120]
    try:
        report_md = render_comparison_report(title, result, insights, warnings)
    except Exception as exc:
        print(f"[competitor] 对比报告渲染失败: {exc}")
        raise HTTPException(status_code=500, detail=f"对比报告生成失败: {exc}")

    from app.crud.competitor import create_competitor_comparison as db_create
    return db_create(
        db,
        title=title[:120],
        task_ids=task_ids,
        baseline_task_id=payload.baseline_task_id,
        result={**result, "insights": insights},
        report_md=report_md,
        user_id=current_user.id,
    )


def _require_comparison_access(db: Session, comparison_id: int, current_user: UserOut):
    from app.crud.competitor import get_competitor_comparison
    item = get_competitor_comparison(db, comparison_id)
    if not item or (current_user.role != "admin" and item.user_id != current_user.id):
        raise HTTPException(status_code=404, detail="Comparison not found")
    return item


@router.get("/compare", response_model=List[CompetitorComparisonSummary])
async def read_competitor_comparisons(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: UserOut = Depends(get_current_active_user),
):
    """对比列表：管理员可见全部，普通用户仅可见自己的。"""
    from app.crud.competitor import get_competitor_comparisons
    user_id = None if current_user.role == "admin" else current_user.id
    return get_competitor_comparisons(db, user_id=user_id, skip=skip, limit=limit)


@router.get("/compare/{comparison_id}", response_model=CompetitorComparisonOut)
async def read_competitor_comparison(
    comparison_id: int,
    db: Session = Depends(get_db),
    current_user: UserOut = Depends(get_current_active_user),
):
    """对比详情（含结构化结果与 Markdown 报告全文）。"""
    return _require_comparison_access(db, comparison_id, current_user)


@router.delete("/compare/{comparison_id}")
async def delete_competitor_comparison(
    comparison_id: int,
    db: Session = Depends(get_db),
    current_user: UserOut = Depends(get_current_active_user),
):
    """删除对比记录（不影响参与任务本身）。"""
    _require_comparison_access(db, comparison_id, current_user)
    from app.crud.competitor import delete_competitor_comparison as db_delete
    db_delete(db, comparison_id)
    return {"message": "Comparison deleted successfully", "comparison_id": comparison_id}


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
