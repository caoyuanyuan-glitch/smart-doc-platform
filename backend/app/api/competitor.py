from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import FileResponse
from typing import Optional
from sqlalchemy.orm import Session
import os
import json
import uuid
from datetime import datetime

from app.database import get_db
from app.models.competitor import Competitor, CompetitorDocument, CompetitorCompareTask, WechatAccount, WechatArticle
from app.schemas.competitor import (
    CompetitorCreate, CompetitorUpdate, CompetitorResponse, CompetitorListResponse,
    CompetitorDocumentResponse, CompetitorDocumentListResponse,
    CompetitorCompareCreate, CompetitorCompareTaskResponse, CompetitorCompareTaskListResponse,
    SuggestionsResponse,
    WechatAccountCreate, WechatAccountUpdate, WechatAccountResponse, WechatAccountListResponse,
    WechatArticleCreate, WechatArticleUpdate, WechatArticleResponse, WechatArticleListResponse
)
from app.crud.competitor import (
    get_competitors, get_competitor, create_competitor, update_competitor, delete_competitor,
    get_competitor_documents, get_competitor_document, create_competitor_document, delete_competitor_document,
    get_compare_tasks, get_all_compare_tasks, get_compare_task, create_compare_task, update_compare_task,
    get_wechat_accounts, get_wechat_account, create_wechat_account, update_wechat_account, delete_wechat_account,
    get_wechat_articles, get_wechat_article, create_wechat_article, update_wechat_article, delete_wechat_article
)
from app.utils.doc_parser import compare_documents_by_format

router = APIRouter()

# 文档存储目录
COMPETITOR_DIR = "./static/competitor"


def _ensure_competitor_dir():
    """确保存储目录存在"""
    if not os.path.exists(COMPETITOR_DIR):
        os.makedirs(COMPETITOR_DIR, exist_ok=True)


# ========== 竞品管理 ==========

@router.get("", response_model=CompetitorListResponse)
async def list_competitors(
    keyword: Optional[str] = None,
    tag: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db)
):
    """获取竞品列表"""
    skip = (page - 1) * page_size
    total, items = get_competitors(db, keyword=keyword, tag=tag, skip=skip, limit=page_size)
    return CompetitorListResponse(total=total, items=items)


@router.get("/{competitor_id}", response_model=CompetitorResponse)
async def get_competitor_detail(
    competitor_id: int,
    db: Session = Depends(get_db)
):
    """获取竞品详情"""
    competitor = get_competitor(db, competitor_id)
    if not competitor:
        raise HTTPException(status_code=404, detail="竞品不存在")
    return competitor


@router.post("", response_model=CompetitorResponse)
async def create_competitor_item(
    competitor: CompetitorCreate,
    db: Session = Depends(get_db)
):
    """创建竞品"""
    # 暂时使用默认用户ID=1
    return create_competitor(db, competitor, user_id=1)


@router.put("/{competitor_id}", response_model=CompetitorResponse)
async def update_competitor_item(
    competitor_id: int,
    competitor: CompetitorUpdate,
    db: Session = Depends(get_db)
):
    """更新竞品"""
    result = update_competitor(db, competitor_id, competitor)
    if not result:
        raise HTTPException(status_code=404, detail="竞品不存在")
    return result


@router.delete("/{competitor_id}")
async def delete_competitor_item(
    competitor_id: int,
    db: Session = Depends(get_db)
):
    """删除竞品"""
    # 先删除关联的文档文件
    competitor_docs, our_docs = get_competitor_documents(db, competitor_id)
    for doc in competitor_docs + our_docs:
        if doc.file_path and os.path.exists(doc.file_path):
            os.remove(doc.file_path)
    
    result = delete_competitor(db, competitor_id)
    if not result:
        raise HTTPException(status_code=404, detail="竞品不存在")
    return {"message": "删除成功"}


# ========== 文档管理 ==========

@router.get("/{competitor_id}/documents", response_model=CompetitorDocumentListResponse)
async def list_documents(
    competitor_id: int,
    db: Session = Depends(get_db)
):
    """获取竞品的文档列表"""
    competitor_docs, our_docs = get_competitor_documents(db, competitor_id)
    return CompetitorDocumentListResponse(
        competitor_docs=competitor_docs,
        our_docs=our_docs
    )


@router.post("/{competitor_id}/documents", response_model=CompetitorDocumentResponse)
async def upload_document(
    competitor_id: int,
    file: UploadFile = File(...),
    doc_type: str = Form(...),
    version: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """上传文档"""
    # 验证竞品存在
    competitor = get_competitor(db, competitor_id)
    if not competitor:
        raise HTTPException(status_code=404, detail="竞品不存在")
    
    # 验证文档类型
    if doc_type not in ["competitor", "ours"]:
        raise HTTPException(status_code=400, detail="文档类型必须是 competitor 或 ours")
    
    # 确保存储目录存在
    _ensure_competitor_dir()
    
    # 生成文件名和路径
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in [".pdf", ".docx", ".doc", ".dita", ".md", ".txt"]:
        raise HTTPException(status_code=400, detail="不支持的文件格式")
    
    unique_id = uuid.uuid4().hex[:8]
    safe_filename = f"{competitor_id}_{doc_type}_{unique_id}{file_ext}"
    file_path = os.path.join(COMPETITOR_DIR, safe_filename)
    
    # 保存文件
    content = await file.read()
    file_size = len(content)
    with open(file_path, "wb") as f:
        f.write(content)
    
    # 判断文件类型
    file_type = file_ext.replace(".", "")
    if file_type == "doc":
        file_type = "docx"
    
    # 创建文档记录
    db_doc = create_competitor_document(
        db=db,
        competitor_id=competitor_id,
        doc_type=doc_type,
        file_name=file.filename,
        file_path=file_path,
        file_type=file_type,
        file_size=file_size,
        version=version,
        notes=notes
    )
    
    return db_doc


@router.delete("/{competitor_id}/documents/{doc_id}")
async def delete_document(
    competitor_id: int,
    doc_id: int,
    db: Session = Depends(get_db)
):
    """删除文档"""
    doc = get_competitor_document(db, doc_id)
    if not doc or doc.competitor_id != competitor_id:
        raise HTTPException(status_code=404, detail="文档不存在")
    
    # 删除文件
    if doc.file_path and os.path.exists(doc.file_path):
        os.remove(doc.file_path)
    
    delete_competitor_document(db, doc_id)
    return {"message": "删除成功"}


# ========== 对比分析 ==========

@router.post("/{competitor_id}/compare", response_model=CompetitorCompareTaskResponse)
async def create_compare(
    competitor_id: int,
    compare_data: CompetitorCompareCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """创建对比任务"""
    # 验证竞品存在
    competitor = get_competitor(db, competitor_id)
    if not competitor:
        raise HTTPException(status_code=404, detail="竞品不存在")
    
    # 验证文档存在
    competitor_doc = get_competitor_document(db, compare_data.competitor_doc_id)
    our_doc = get_competitor_document(db, compare_data.our_doc_id)
    
    if not competitor_doc or competitor_doc.competitor_id != competitor_id:
        raise HTTPException(status_code=404, detail="竞品文档不存在")
    if not our_doc or our_doc.competitor_id != competitor_id:
        raise HTTPException(status_code=404, detail="我方文档不存在")
    
    if competitor_doc.doc_type != "competitor":
        raise HTTPException(status_code=400, detail="选择的竞品文档类型不正确")
    if our_doc.doc_type != "ours":
        raise HTTPException(status_code=400, detail="选择的我方文档类型不正确")
    
    # 创建对比任务
    task = create_compare_task(
        db=db,
        competitor_id=competitor_id,
        competitor_doc_id=compare_data.competitor_doc_id,
        our_doc_id=compare_data.our_doc_id
    )
    
    # 异步执行对比
    background_tasks.add_task(
        _run_compare_task,
        db, task.id, competitor_doc.file_path, our_doc.file_path
    )
    
    # 添加文档名称
    task.competitor_doc_name = competitor_doc.file_name
    task.our_doc_name = our_doc.file_name
    
    return task


def _run_compare_task(
    db: Session,
    task_id: int,
    file_a_path: str,
    file_b_path: str
):
    """执行对比任务（后台任务）"""
    try:
        # 更新状态为处理中
        update_compare_task(db, task_id, status="processing")
        
        # 调用对比引擎
        result = compare_documents_by_format(
            file_a_path=file_a_path,
            file_b_path=file_b_path
        )
        
        # 计算总体相似度
        similarity = result.get("overall_similarity", 0) * 100
        
        # 处理对比结果
        result_data = {
            "structure_diff": _process_structure_diff(result),
            "content_diff": _process_content_diff(result),
            "chapter_similarity": _process_chapter_similarity(result)
        }
        
        # 更新任务状态为完成
        update_compare_task(
            db, task_id,
            status="completed",
            similarity=round(similarity, 2),
            result_data=json.dumps(result_data, ensure_ascii=False)
        )
        
    except Exception as e:
        # 更新任务状态为失败
        update_compare_task(
            db, task_id,
            status="failed",
            error_message=str(e)
        )


def _process_structure_diff(result: dict) -> list:
    """处理章节结构差异"""
    structure_diff = []
    
    chapters_a = result.get("chapters_a", [])
    chapters_b = result.get("chapters_b", [])
    
    # 简化处理：比较章节标题
    titles_a = {c.get("title", "").strip() for c in chapters_a if c.get("title")}
    titles_b = {c.get("title", "").strip() for c in chapters_b if c.get("title")}
    
    # 共有的章节
    matched = titles_a & titles_b
    for title in matched:
        structure_diff.append({
            "section": title,
            "status": "match"
        })
    
    # 竞品独有的章节
    competitor_only = titles_a - titles_b
    for title in competitor_only:
        structure_diff.append({
            "section": title,
            "status": "competitor_only"
        })
    
    # 我方独有的章节
    ours_only = titles_b - titles_a
    for title in ours_only:
        structure_diff.append({
            "section": title,
            "status": "ours_only"
        })
    
    return structure_diff


def _process_content_diff(result: dict) -> list:
    """处理内容差异"""
    content_diff = []
    
    diffs = result.get("diffs", [])
    for diff in diffs:
        if diff.get("type") == "missing_a":
            content_diff.append({
                "section": diff.get("section", ""),
                "type": "ours_only",
                "content": diff.get("text_b", "")
            })
        elif diff.get("type") == "missing_b":
            content_diff.append({
                "section": diff.get("section", ""),
                "type": "competitor_only",
                "content": diff.get("text_a", "")
            })
        elif diff.get("type") == "modified":
            content_diff.append({
                "section": diff.get("section", ""),
                "type": "content_diff",
                "detail": f"相似度: {diff.get('similarity', 0)*100:.1f}%"
            })
    
    return content_diff


def _process_chapter_similarity(result: dict) -> list:
    """处理章节相似度"""
    chapter_similarity = []
    
    chapter_stats = result.get("chapter_stats", {})
    for chapter, stats in chapter_stats.items():
        chapter_similarity.append({
            "chapter": chapter,
            "similarity": round(stats.get("similarity", 0) * 100, 2)
        })
    
    return chapter_similarity


@router.get("/compare/tasks", response_model=CompetitorCompareTaskListResponse)
async def list_all_compare_tasks(
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db)
):
    """获取所有对比任务列表（全局）"""
    skip = (page - 1) * page_size
    total, items = get_all_compare_tasks(db, skip=skip, limit=page_size)
    return CompetitorCompareTaskListResponse(total=total, items=items)


@router.get("/{competitor_id}/compare/tasks", response_model=CompetitorCompareTaskListResponse)
async def list_compare_tasks(
    competitor_id: int,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db)
):
    """获取对比任务列表（指定竞品）"""
    skip = (page - 1) * page_size
    total, items = get_compare_tasks(db, competitor_id, skip=skip, limit=page_size)
    return CompetitorCompareTaskListResponse(total=total, items=items)


@router.get("/{competitor_id}/compare/tasks/{task_id}", response_model=CompetitorCompareTaskResponse)
async def get_compare_task_detail(
    competitor_id: int,
    task_id: int,
    db: Session = Depends(get_db)
):
    """获取对比任务详情"""
    task = get_compare_task(db, task_id)
    if not task or task.competitor_id != competitor_id:
        raise HTTPException(status_code=404, detail="对比任务不存在")
    return task


# ========== AI改进建议 ==========

@router.post("/{competitor_id}/compare/tasks/{task_id}/suggest", response_model=SuggestionsResponse)
async def generate_suggestions(
    competitor_id: int,
    task_id: int,
    db: Session = Depends(get_db)
):
    """生成AI改进建议"""
    task = get_compare_task(db, task_id)
    if not task or task.competitor_id != competitor_id:
        raise HTTPException(status_code=404, detail="对比任务不存在")
    
    if task.status != "completed":
        raise HTTPException(status_code=400, detail="对比任务尚未完成，无法生成建议")
    
    # 解析对比结果
    result_data = json.loads(task.result_data) if task.result_data else {}
    
    # 获取文档内容（用于参考原文）
    competitor_doc = get_competitor_document(db, task.competitor_doc_id)
    our_doc = get_competitor_document(db, task.our_doc_id)
    
    # 构建Prompt
    prompt = f"""你是一位专业的技术文档专家。请分析以下竞品说明书与我方说明书的对比结果，给出具体的改进建议。

对比结果：
- 总体相似度：{task.similarity}%
- 章节结构差异：{json.dumps(result_data.get('structure_diff', []), ensure_ascii=False)}
- 内容差异点：{json.dumps(result_data.get('content_diff', []), ensure_ascii=False)}

请从以下维度给出建议：
1. 内容补充建议：竞品有但我方缺失的重要内容
2. 结构优化建议：竞品信息架构的优势点
3. 参数对标建议：技术参数的差异说明
4. 文案优化建议：竞品的优秀表述方式

每条建议请包含：
- category: 类别（内容补充/结构优化/参数对标/文案优化）
- content: 建议内容
- reason: 原因说明
- reference: 参考竞品原文（如有）
- priority: 优先级（高/中/低）

请以JSON数组格式输出建议，格式如下：
[
  {{
    "category": "内容补充",
    "content": "建议添加故障排除章节",
    "reason": "竞品说明书包含详细的故障排除指南",
    "reference": "竞品故障排除章节包含10个常见问题",
    "priority": "高"
  }}
]

只输出JSON数组，不要有其他内容。"""

    # 调用AI生成建议
    try:
        from app.utils.ai_client import AIClient
        ai_client = AIClient()
        ai_response = ai_client.chat(prompt)
        
        # 解析AI响应
        suggestions_raw = ai_response.strip()
        # 移除可能的markdown代码块标记
        if suggestions_raw.startswith("```json"):
            suggestions_raw = suggestions_raw[7:]
        if suggestions_raw.startswith("```"):
            suggestions_raw = suggestions_raw[3:]
        if suggestions_raw.endswith("```"):
            suggestions_raw = suggestions_raw[:-3]
        
        suggestions = json.loads(suggestions_raw.strip())
        
    except Exception as e:
        # 如果AI解析失败，生成默认建议
        suggestions = [
            {
                "category": "内容补充",
                "content": "建议补充竞品独有的章节内容",
                "reason": f"对比结果显示竞品有{len([d for d in result_data.get('structure_diff', []) if d.get('status') == 'competitor_only'])}个独有章节",
                "reference": None,
                "priority": "高"
            }
        ]
    
    # 保存建议
    update_compare_task(
        db, task_id,
        suggestions=json.dumps(suggestions, ensure_ascii=False)
    )
    
    return SuggestionsResponse(
        suggestions=suggestions,
        generated_at=datetime.utcnow()
    )


@router.get("/{competitor_id}/compare/tasks/{task_id}/suggest", response_model=SuggestionsResponse)
async def get_suggestions(
    competitor_id: int,
    task_id: int,
    db: Session = Depends(get_db)
):
    """获取已生成的AI改进建议"""
    task = get_compare_task(db, task_id)
    if not task or task.competitor_id != competitor_id:
        raise HTTPException(status_code=404, detail="对比任务不存在")
    
    if not task.suggestions:
        raise HTTPException(status_code=404, detail="尚未生成改进建议")
    
    suggestions = json.loads(task.suggestions)
    
    return SuggestionsResponse(
        suggestions=suggestions,
        generated_at=task.completed_at or datetime.utcnow()
    )


# ========== 报告导出 ==========

@router.get("/{competitor_id}/compare/tasks/{task_id}/export")
async def export_compare_report(
    competitor_id: int,
    task_id: int,
    format: str = "html",
    db: Session = Depends(get_db)
):
    """导出对比报告"""
    task = get_compare_task(db, task_id)
    if not task or task.competitor_id != competitor_id:
        raise HTTPException(status_code=404, detail="对比任务不存在")
    
    if task.status != "completed":
        raise HTTPException(status_code=400, detail="对比任务尚未完成")
    
    # 获取竞品和文档信息
    competitor = get_competitor(db, competitor_id)
    competitor_doc = get_competitor_document(db, task.competitor_doc_id)
    our_doc = get_competitor_document(db, task.our_doc_id)
    
    # 解析对比结果和建议
    result_data = json.loads(task.result_data) if task.result_data else {}
    suggestions = json.loads(task.suggestions) if task.suggestions else []
    
    # 生成HTML报告
    report_html = _generate_html_report(
        competitor=competitor,
        competitor_doc=competitor_doc,
        our_doc=our_doc,
        task=task,
        result_data=result_data,
        suggestions=suggestions
    )
    
    # 保存报告文件
    _ensure_competitor_dir()
    report_filename = f"compare_report_{competitor_id}_{task_id}.html"
    report_path = os.path.join(COMPETITOR_DIR, report_filename)
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_html)
    
    return FileResponse(
        report_path,
        media_type="text/html",
        filename=f"竞品对比报告_{competitor.name}_{datetime.now().strftime('%Y%m%d')}.html"
    )


def _generate_html_report(
    competitor, competitor_doc, our_doc, task, result_data, suggestions
) -> str:
    """生成HTML报告"""
    
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>竞品说明书对比报告 - {competitor.name}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .container {{
            background: #fff;
            border-radius: 8px;
            padding: 30px;
            box-shadow: 0 2px 12px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #34495e;
            margin-top: 30px;
        }}
        .summary {{
            background: #e8f4fd;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
        }}
        .similarity {{
            font-size: 48px;
            color: { '#27ae60' if task.similarity >= 80 else '#f39c12' if task.similarity >= 60 else '#e74c3c' };
            font-weight: bold;
        }}
        .meta {{
            color: #7f8c8d;
            font-size: 14px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background: #3498db;
            color: #fff;
        }}
        tr:nth-child(even) {{
            background: #f9f9f9;
        }}
        .match {{
            color: #27ae60;
        }}
        .competitor-only {{
            color: #e74c3c;
        }}
        .ours-only {{
            color: #3498db;
        }}
        .similar {{
            color: #f39c12;
        }}
        .suggestion {{
            background: #fef9e7;
            border-left: 4px solid #f39c12;
            padding: 15px;
            margin: 10px 0;
            border-radius: 4px;
        }}
        .suggestion.high {{
            border-left-color: #e74c3c;
            background: #fdedec;
        }}
        .suggestion.medium {{
            border-left-color: #f39c12;
        }}
        .suggestion.low {{
            border-left-color: #27ae60;
            background: #e8f8f5;
        }}
        .priority {{
            font-weight: bold;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 12px;
        }}
        .priority.high {{
            background: #e74c3c;
            color: #fff;
        }}
        .priority.medium {{
            background: #f39c12;
            color: #fff;
        }}
        .priority.low {{
            background: #27ae60;
            color: #fff;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>竞品说明书对比报告</h1>
        
        <div class="summary">
            <p><strong>竞品：</strong>{competitor.name} ({competitor.brand or ''})</p>
            <p><strong>竞品文档：</strong>{competitor_doc.file_name}</p>
            <p><strong>我方文档：</strong>{our_doc.file_name}</p>
            <p><strong>对比时间：</strong>{task.created_at.strftime('%Y-%m-%d %H:%M')}</p>
            <p class="similarity">{task.similarity}%</p>
            <p>总体相似度</p>
        </div>
        
        <h2>章节结构对比</h2>
        <table>
            <tr>
                <th>章节</th>
                <th>匹配状态</th>
                <th>说明</th>
            </tr>
"""

    # 章节结构差异
    for item in result_data.get("structure_diff", []):
        status_class = item.get("status", "match")
        status_text = {
            "match": "✓ 匹配",
            "competitor_only": "竞品独有",
            "ours_only": "我方独有",
            "similar": "⚠ 相似"
        }.get(status_class, item.get("status"))
        
        html += f"""
            <tr>
                <td>{item.get('section', '')}</td>
                <td class="{status_class}">{status_text}</td>
                <td>{item.get('competitor_name', '') or item.get('our_name', '') or '-'}</td>
            </tr>
"""

    html += """
        </table>
        
        <h2>内容差异详情</h2>
        <table>
            <tr>
                <th>章节</th>
                <th>差异类型</th>
                <th>详细说明</th>
            </tr>
"""

    # 内容差异
    for item in result_data.get("content_diff", []):
        type_class = item.get("type", "content_diff")
        type_text = {
            "competitor_only": "竞品独有",
            "ours_only": "我方独有",
            "content_diff": "内容差异"
        }.get(type_class, item.get("type"))
        
        html += f"""
            <tr>
                <td>{item.get('section', '')}</td>
                <td class="{type_class}">{type_text}</td>
                <td>{item.get('content', '') or item.get('detail', '')}</td>
            </tr>
"""

    html += """
        </table>
"""

    # AI改进建议
    if suggestions:
        html += """
        <h2>AI改进建议</h2>
"""
        for sug in suggestions:
            priority_class = sug.get("priority", "中").lower()
            html += f"""
        <div class="suggestion {priority_class}">
            <p><strong>类别：</strong>{sug.get('category', '')} <span class="priority {priority_class}">{sug.get('priority', '')}</span></p>
            <p><strong>建议：</strong>{sug.get('content', '')}</p>
            <p><strong>原因：</strong>{sug.get('reason', '')}</p>
            {f'<p><strong>参考：</strong>{sug.get("reference", "")}</p>' if sug.get('reference') else ''}
        </div>
"""

    html += """
        <div class="meta">
            <p>报告生成时间：""" + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + """</p>
            <p>智能技术文档平台 - 竞品说明书分析模块</p>
        </div>
    </div>
</body>
</html>
"""

    return html


# ========== 公众号管理 ==========

@router.get("/{competitor_id}/wechat/accounts", response_model=WechatAccountListResponse)
async def list_wechat_accounts(
    competitor_id: int,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db)
):
    """获取竞品的公众号列表"""
    competitor = get_competitor(db, competitor_id)
    if not competitor:
        raise HTTPException(status_code=404, detail="竞品不存在")
    
    skip = (page - 1) * page_size
    total, items = get_wechat_accounts(db, competitor_id, skip=skip, limit=page_size)
    return WechatAccountListResponse(total=total, items=items)


@router.post("/{competitor_id}/wechat/accounts", response_model=WechatAccountResponse)
async def create_wechat_account_item(
    competitor_id: int,
    account: WechatAccountCreate,
    db: Session = Depends(get_db)
):
    """创建公众号配置"""
    competitor = get_competitor(db, competitor_id)
    if not competitor:
        raise HTTPException(status_code=404, detail="竞品不存在")
    
    return create_wechat_account(
        db=db,
        competitor_id=competitor_id,
        account_name=account.account_name,
        account_id=account.account_id,
        description=account.description
    )


@router.put("/{competitor_id}/wechat/accounts/{account_id}", response_model=WechatAccountResponse)
async def update_wechat_account_item(
    competitor_id: int,
    account_id: int,
    account: WechatAccountUpdate,
    db: Session = Depends(get_db)
):
    """更新公众号配置"""
    db_account = get_wechat_account(db, account_id)
    if not db_account or db_account.competitor_id != competitor_id:
        raise HTTPException(status_code=404, detail="公众号不存在")
    
    return update_wechat_account(
        db=db,
        account_id=account_id,
        account_name=account.account_name,
        account_id_str=account.account_id,
        description=account.description,
        is_active=account.is_active
    )


@router.delete("/{competitor_id}/wechat/accounts/{account_id}")
async def delete_wechat_account_item(
    competitor_id: int,
    account_id: int,
    db: Session = Depends(get_db)
):
    """删除公众号配置"""
    db_account = get_wechat_account(db, account_id)
    if not db_account or db_account.competitor_id != competitor_id:
        raise HTTPException(status_code=404, detail="公众号不存在")
    
    delete_wechat_account(db, account_id)
    return {"message": "删除成功"}


# ========== 公众号文章管理 ==========

@router.get("/wechat/articles", response_model=WechatArticleListResponse)
async def list_all_wechat_articles(
    competitor_id: Optional[int] = None,
    wechat_account_id: Optional[int] = None,
    category: Optional[str] = None,
    keyword: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db)
):
    """获取所有公众号文章列表（全局）"""
    skip = (page - 1) * page_size
    total, items = get_wechat_articles(
        db,
        competitor_id=competitor_id,
        wechat_account_id=wechat_account_id,
        category=category,
        keyword=keyword,
        skip=skip,
        limit=page_size
    )
    return WechatArticleListResponse(total=total, items=items)


@router.get("/{competitor_id}/wechat/articles", response_model=WechatArticleListResponse)
async def list_competitor_wechat_articles(
    competitor_id: int,
    wechat_account_id: Optional[int] = None,
    category: Optional[str] = None,
    keyword: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db)
):
    """获取竞品的公众号文章列表"""
    competitor = get_competitor(db, competitor_id)
    if not competitor:
        raise HTTPException(status_code=404, detail="竞品不存在")
    
    skip = (page - 1) * page_size
    total, items = get_wechat_articles(
        db,
        competitor_id=competitor_id,
        wechat_account_id=wechat_account_id,
        category=category,
        keyword=keyword,
        skip=skip,
        limit=page_size
    )
    return WechatArticleListResponse(total=total, items=items)


@router.post("/{competitor_id}/wechat/articles", response_model=WechatArticleResponse)
async def create_wechat_article_item(
    competitor_id: int,
    article: WechatArticleCreate,
    db: Session = Depends(get_db)
):
    """添加公众号文章（手动添加）"""
    competitor = get_competitor(db, competitor_id)
    if not competitor:
        raise HTTPException(status_code=404, detail="竞品不存在")
    
    # 验证公众号存在且属于该竞品
    account = get_wechat_account(db, article.wechat_account_id)
    if not account or account.competitor_id != competitor_id:
        raise HTTPException(status_code=404, detail="公众号不存在或不属于该竞品")
    
    return create_wechat_article(
        db=db,
        wechat_account_id=article.wechat_account_id,
        competitor_id=competitor_id,
        title=article.title,
        url=article.url,
        author=article.author,
        publish_date=article.publish_date,
        content=article.content,
        keywords=article.keywords,
        category=article.category
    )


@router.get("/{competitor_id}/wechat/articles/{article_id}", response_model=WechatArticleResponse)
async def get_wechat_article_detail(
    competitor_id: int,
    article_id: int,
    db: Session = Depends(get_db)
):
    """获取公众号文章详情"""
    article = get_wechat_article(db, article_id)
    if not article or article.competitor_id != competitor_id:
        raise HTTPException(status_code=404, detail="文章不存在")
    return article


@router.put("/{competitor_id}/wechat/articles/{article_id}", response_model=WechatArticleResponse)
async def update_wechat_article_item(
    competitor_id: int,
    article_id: int,
    article: WechatArticleUpdate,
    db: Session = Depends(get_db)
):
    """更新公众号文章（打标签、分类等）"""
    db_article = get_wechat_article(db, article_id)
    if not db_article or db_article.competitor_id != competitor_id:
        raise HTTPException(status_code=404, detail="文章不存在")
    
    return update_wechat_article(
        db=db,
        article_id=article_id,
        tags=article.tags,
        category=article.category,
        notes=article.notes
    )


@router.delete("/{competitor_id}/wechat/articles/{article_id}")
async def delete_wechat_article_item(
    competitor_id: int,
    article_id: int,
    db: Session = Depends(get_db)
):
    """删除公众号文章"""
    article = get_wechat_article(db, article_id)
    if not article or article.competitor_id != competitor_id:
        raise HTTPException(status_code=404, detail="文章不存在")
    
    delete_wechat_article(db, article_id)
    return {"message": "删除成功"}


@router.post("/{competitor_id}/wechat/articles/{article_id}/summary")
async def generate_article_summary(
    competitor_id: int,
    article_id: int,
    db: Session = Depends(get_db)
):
    """生成AI摘要"""
    article = get_wechat_article(db, article_id)
    if not article or article.competitor_id != competitor_id:
        raise HTTPException(status_code=404, detail="文章不存在")
    
    if not article.content:
        raise HTTPException(status_code=400, detail="文章内容为空，无法生成摘要")
    
    # 调用AI生成摘要
    try:
        from app.utils.ai_client import AIClient
        ai_client = AIClient()
        
        prompt = f"""请为以下文章生成一段简洁的摘要（不超过200字），突出文章的核心内容和关键信息。

文章标题：{article.title}
文章内容：
{article.content[:3000]}

请直接输出摘要内容，不需要其他格式。"""
        
        summary = ai_client.chat(prompt)
        
        # 更新文章摘要
        updated_article = update_wechat_article(db, article_id, summary=summary.strip())
        
        return {"summary": summary.strip(), "article_id": article_id}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成摘要失败: {str(e)}")