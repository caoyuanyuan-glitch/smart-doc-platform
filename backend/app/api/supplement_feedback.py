"""人工审核意见样本池 API。

- POST  /api/review/supplements/import     批量导入人工审核意见（md/json/csv）
- GET   /api/review/supplements/cluster    按类别聚合统计（人工标尺分布）
- POST  /api/review/supplements/{id}/convert-rule   把意见转为规则候选（open -> rule_draft）
- POST  /api/review/supplements/{id}/dismiss       否决该意见（dismissed）

注：GET /api/review/supplements 列表查询由 review.py 的 list_manual_supplements
提供（补录快照 + 批量导入共用同一张表，此处不再重复注册）。
"""
from __future__ import annotations

import logging
from collections import defaultdict

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.supplement_feedback import SupplementFeedback

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/review/supplements", tags=["人工意见样本池"])


def _fmt_row(row: SupplementFeedback) -> dict:
    return {
        "id": row.id,
        "doc_name": row.doc_name,
        "page": row.page,
        "annotation_type": row.annotation_type,
        "author": row.author,
        "comment": row.comment,
        "original_text": row.original_text,
        "context": row.context,
        "category": row.category,
        "suggestion": row.suggestion,
        "layer": row.layer,
        "expected_rule": row.expected_rule,
        "source": row.source,
        "batch_name": row.batch_name,
        "rule_candidate_status": row.rule_candidate_status,
        "review_id": row.review_id,
        "issue_id": row.issue_id,
        "document_id": row.document_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.post("/import")
async def import_supplements(
    file: UploadFile = File(...),
    batch_name: str = Form(""),
    db: Session = Depends(get_db),
):
    """导入人工审核意见文件（.md / .json / .csv）。

    - md：review_comment_extractor 汇总格式 或 人工整理汇总
    - json：gold_v0 评测集格式（list of {file,page,comment,selected_text,...}）
    - csv：标注集 v0 格式（batch,doc,page,comment,selected,context,auto_category,...）
    """
    from app.services.manual_feedback_import import parse_upload

    filename = file.filename or "upload"
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="上传文件为空")
    try:
        rows = parse_upload(filename, raw)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"解析失败: {exc}") from exc

    if not rows:
        raise HTTPException(status_code=400, detail="未从文件中解析出任何人工意见（每条至少需要 comment 字段）")

    batch = batch_name.strip() or (filename.rsplit("/", 1)[-1].rsplit(".", 1)[0])
    inserted = 0
    skipped = 0
    for r in rows:
        # 同批次内按 (doc_name, page, comment) 去重
        exists = (
            db.query(SupplementFeedback.id)
            .filter(
                SupplementFeedback.batch_name == batch,
                SupplementFeedback.doc_name == (r.get("doc_name") or ""),
                SupplementFeedback.page == (r.get("page") or ""),
                SupplementFeedback.comment == r.get("comment"),
            )
            .first()
        )
        if exists:
            skipped += 1
            continue
        db.add(
            SupplementFeedback(
                doc_name=r.get("doc_name") or "",
                page=r.get("page") or "",
                annotation_type=r.get("annotation_type") or "",
                author=r.get("author") or "",
                comment=r.get("comment") or "",
                original_text=r.get("original_text") or "",
                context=r.get("context") or "",
                category=(r.get("category") or "未分类")[:128],
                suggestion=r.get("suggestion") or "",
                layer=r.get("layer") or "ai_assisted",
                expected_rule=r.get("expected_rule") or "",
                source="batch_import",
                batch_name=batch,
                rule_candidate_status="open",
            )
        )
        inserted += 1
    db.commit()

    # 类别分布统计
    cat_rows = (
        db.query(SupplementFeedback.category, func.count(SupplementFeedback.id))
        .filter(SupplementFeedback.batch_name == batch)
        .group_by(SupplementFeedback.category)
        .all()
    )
    cat_counts = {c or "未分类": n for c, n in cat_rows}

    return {
        "ok": True,
        "batch_name": batch,
        "parsed": len(rows),
        "inserted": inserted,
        "skipped": skipped,
        "category_distribution": cat_counts,
        "sample": rows[:5],
    }


@router.get("/cluster")
def cluster_supplements(
    min_count: int = 3,
    db: Session = Depends(get_db),
):
    """按类别聚合，得到“人工到底在标什么”的分布（用于校准规则优先级）。"""
    cat_rows = (
        db.query(SupplementFeedback.category, func.count(SupplementFeedback.id))
        .group_by(SupplementFeedback.category)
        .order_by(func.count(SupplementFeedback.id).desc())
        .all()
    )
    distribution = {c or "未分类": n for c, n in cat_rows}

    # 类别内按意见文本聚类（相同/相似意见出现多次 -> 高频规则候选）
    clusters = defaultdict(list)
    all_rows = db.query(SupplementFeedback).filter(SupplementFeedback.comment != "").all()
    for r in all_rows:
        clusters[(r.category or "未分类", r.comment)].append(r.id)

    candidates = []
    for (cat, comment), ids in clusters.items():
        if len(ids) >= min_count:
            candidates.append(
                {
                    "category": cat,
                    "comment": comment[:200],
                    "count": len(ids),
                    "ids": ids[:100],
                    "status": "rule_draft_candidate",
                }
            )
    candidates.sort(key=lambda x: -x["count"])

    return {
        "total": db.query(SupplementFeedback).count(),
        "category_distribution": distribution,
        "rule_candidates": candidates[:50],
        "rule_candidate_count": len(candidates),
    }


@router.post("/{item_id}/convert-rule")
def convert_rule(
    item_id: int,
    db: Session = Depends(get_db),
):
    """把一条人工意见标记为规则候选（open -> rule_draft），后续人工确认转正式规则。"""
    row = db.query(SupplementFeedback).filter(SupplementFeedback.id == item_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="意见不存在")
    if row.rule_candidate_status == "converted":
        raise HTTPException(status_code=400, detail="该意见已转为正式规则")
    row.rule_candidate_status = "rule_draft"
    db.commit()
    db.refresh(row)
    return {"ok": True, "item": _fmt_row(row)}


@router.post("/{item_id}/dismiss")
def dismiss_rule(
    item_id: int,
    db: Session = Depends(get_db),
):
    """否决该意见（dismissed），不再作为规则候选。"""
    row = db.query(SupplementFeedback).filter(SupplementFeedback.id == item_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="意见不存在")
    row.rule_candidate_status = "dismissed"
    db.commit()
    db.refresh(row)
    return {"ok": True, "item": _fmt_row(row)}
