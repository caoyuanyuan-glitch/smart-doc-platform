from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import datetime
from app.models.competitor import Competitor, CompetitorDocument, CompetitorCompareTask, WechatAccount, WechatArticle
from app.schemas.competitor import CompetitorCreate, CompetitorUpdate


# ========== 竞品 CRUD ==========

def get_competitors(
    db: Session,
    user_id: Optional[int] = None,
    keyword: Optional[str] = None,
    tag: Optional[str] = None,
    skip: int = 0,
    limit: int = 20
) -> tuple:
    """获取竞品列表"""
    query = db.query(Competitor)
    
    if user_id:
        query = query.filter(Competitor.user_id == user_id)
    
    if keyword:
        query = query.filter(
            (Competitor.name.contains(keyword)) |
            (Competitor.brand.contains(keyword))
        )
    
    if tag:
        query = query.filter(Competitor.tags.contains(tag))
    
    total = query.count()
    items = query.order_by(Competitor.created_at.desc()).offset(skip).limit(limit).all()
    
    # 为每个竞品添加文档数量
    for item in items:
        item.document_count = db.query(func.count(CompetitorDocument.id)).filter(
            CompetitorDocument.competitor_id == item.id
        ).scalar() or 0
    
    return total, items


def get_competitor(db: Session, competitor_id: int) -> Optional[Competitor]:
    """获取单个竞品"""
    competitor = db.query(Competitor).filter(Competitor.id == competitor_id).first()
    if competitor:
        competitor.document_count = db.query(func.count(CompetitorDocument.id)).filter(
            CompetitorDocument.competitor_id == competitor.id
        ).scalar() or 0
    return competitor


def create_competitor(db: Session, competitor: CompetitorCreate, user_id: int) -> Competitor:
    """创建竞品"""
    db_competitor = Competitor(
        name=competitor.name,
        brand=competitor.brand,
        website=competitor.website,
        description=competitor.description,
        tags=competitor.tags,
        user_id=user_id
    )
    db.add(db_competitor)
    db.commit()
    db.refresh(db_competitor)
    db_competitor.document_count = 0
    return db_competitor


def update_competitor(db: Session, competitor_id: int, competitor: CompetitorUpdate) -> Optional[Competitor]:
    """更新竞品"""
    db_competitor = db.query(Competitor).filter(Competitor.id == competitor_id).first()
    if not db_competitor:
        return None
    
    update_data = competitor.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_competitor, key, value)
    
    db.commit()
    db.refresh(db_competitor)
    db_competitor.document_count = db.query(func.count(CompetitorDocument.id)).filter(
        CompetitorDocument.competitor_id == db_competitor.id
    ).scalar() or 0
    return db_competitor


def delete_competitor(db: Session, competitor_id: int) -> bool:
    """删除竞品"""
    db_competitor = db.query(Competitor).filter(Competitor.id == competitor_id).first()
    if not db_competitor:
        return False
    
    db.delete(db_competitor)
    db.commit()
    return True


# ========== 文档 CRUD ==========

def get_competitor_documents(db: Session, competitor_id: int) -> tuple:
    """获取竞品的文档列表（按类型分组）"""
    competitor_docs = db.query(CompetitorDocument).filter(
        CompetitorDocument.competitor_id == competitor_id,
        CompetitorDocument.doc_type == "competitor"
    ).order_by(CompetitorDocument.upload_date.desc()).all()
    
    our_docs = db.query(CompetitorDocument).filter(
        CompetitorDocument.competitor_id == competitor_id,
        CompetitorDocument.doc_type == "ours"
    ).order_by(CompetitorDocument.upload_date.desc()).all()
    
    return competitor_docs, our_docs


def get_competitor_document(db: Session, doc_id: int) -> Optional[CompetitorDocument]:
    """获取单个文档"""
    return db.query(CompetitorDocument).filter(CompetitorDocument.id == doc_id).first()


def create_competitor_document(
    db: Session,
    competitor_id: int,
    doc_type: str,
    file_name: str,
    file_path: str,
    file_type: str,
    file_size: int,
    version: Optional[str] = None,
    notes: Optional[str] = None
) -> CompetitorDocument:
    """创建文档记录"""
    db_doc = CompetitorDocument(
        competitor_id=competitor_id,
        doc_type=doc_type,
        file_name=file_name,
        file_path=file_path,
        file_type=file_type,
        file_size=file_size,
        version=version,
        notes=notes
    )
    db.add(db_doc)
    db.commit()
    db.refresh(db_doc)
    return db_doc


def delete_competitor_document(db: Session, doc_id: int) -> bool:
    """删除文档"""
    db_doc = db.query(CompetitorDocument).filter(CompetitorDocument.id == doc_id).first()
    if not db_doc:
        return False
    
    db.delete(db_doc)
    db.commit()
    return True


# ========== 对比任务 CRUD ==========

def get_compare_tasks(
    db: Session,
    competitor_id: int,
    skip: int = 0,
    limit: int = 20
) -> tuple:
    """获取对比任务列表（指定竞品）"""
    query = db.query(CompetitorCompareTask).filter(
        CompetitorCompareTask.competitor_id == competitor_id
    )
    
    total = query.count()
    items = query.order_by(CompetitorCompareTask.created_at.desc()).offset(skip).limit(limit).all()
    
    # 为每个任务添加文档名称和竞品名称
    for item in items:
        competitor_doc = db.query(CompetitorDocument).filter(
            CompetitorDocument.id == item.competitor_doc_id
        ).first()
        our_doc = db.query(CompetitorDocument).filter(
            CompetitorDocument.id == item.our_doc_id
        ).first()
        competitor_info = db.query(Competitor).filter(
            Competitor.id == item.competitor_id
        ).first()
        item.competitor_doc_name = competitor_doc.file_name if competitor_doc else None
        item.our_doc_name = our_doc.file_name if our_doc else None
        item.competitor_name = competitor_info.name if competitor_info else None
    
    return total, items


def get_all_compare_tasks(
    db: Session,
    skip: int = 0,
    limit: int = 20
) -> tuple:
    """获取所有对比任务列表（全局）"""
    query = db.query(CompetitorCompareTask)
    
    total = query.count()
    items = query.order_by(CompetitorCompareTask.created_at.desc()).offset(skip).limit(limit).all()
    
    # 为每个任务添加文档名称和竞品名称
    for item in items:
        competitor_doc = db.query(CompetitorDocument).filter(
            CompetitorDocument.id == item.competitor_doc_id
        ).first()
        our_doc = db.query(CompetitorDocument).filter(
            CompetitorDocument.id == item.our_doc_id
        ).first()
        competitor_info = db.query(Competitor).filter(
            Competitor.id == item.competitor_id
        ).first()
        item.competitor_doc_name = competitor_doc.file_name if competitor_doc else None
        item.our_doc_name = our_doc.file_name if our_doc else None
        item.competitor_name = competitor_info.name if competitor_info else None
    
    return total, items


def get_compare_task(db: Session, task_id: int) -> Optional[CompetitorCompareTask]:
    """获取单个对比任务"""
    task = db.query(CompetitorCompareTask).filter(CompetitorCompareTask.id == task_id).first()
    if task:
        competitor_doc = db.query(CompetitorDocument).filter(
            CompetitorDocument.id == task.competitor_doc_id
        ).first()
        our_doc = db.query(CompetitorDocument).filter(
            CompetitorDocument.id == task.our_doc_id
        ).first()
        task.competitor_doc_name = competitor_doc.file_name if competitor_doc else None
        task.our_doc_name = our_doc.file_name if our_doc else None
    return task


def create_compare_task(
    db: Session,
    competitor_id: int,
    competitor_doc_id: int,
    our_doc_id: int
) -> CompetitorCompareTask:
    """创建对比任务"""
    db_task = CompetitorCompareTask(
        competitor_id=competitor_id,
        competitor_doc_id=competitor_doc_id,
        our_doc_id=our_doc_id,
        status="pending"
    )
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task


def update_compare_task(
    db: Session,
    task_id: int,
    status: Optional[str] = None,
    similarity: Optional[float] = None,
    result_data: Optional[str] = None,
    suggestions: Optional[str] = None,
    error_message: Optional[str] = None
) -> Optional[CompetitorCompareTask]:
    """更新对比任务"""
    db_task = db.query(CompetitorCompareTask).filter(CompetitorCompareTask.id == task_id).first()
    if not db_task:
        return None
    
    if status:
        db_task.status = status
    if similarity is not None:
        db_task.similarity = similarity
    if result_data:
        db_task.result_data = result_data
    if suggestions:
        db_task.suggestions = suggestions
    if error_message:
        db_task.error_message = error_message
    
    if status == "completed" or status == "failed":
        from datetime import datetime
        db_task.completed_at = datetime.utcnow()
    
    db.commit()
    db.refresh(db_task)
    return db_task


# ========== 公众号 CRUD ==========

def get_wechat_accounts(
    db: Session,
    competitor_id: int,
    skip: int = 0,
    limit: int = 20
) -> tuple:
    """获取公众号列表"""
    query = db.query(WechatAccount).filter(WechatAccount.competitor_id == competitor_id)
    total = query.count()
    items = query.order_by(WechatAccount.created_at.desc()).offset(skip).limit(limit).all()
    # 为每个公众号添加文章数量
    for item in items:
        item.article_count = db.query(func.count(WechatArticle.id)).filter(
            WechatArticle.wechat_account_id == item.id
        ).scalar() or 0
    return total, items


def get_wechat_account(db: Session, account_id: int) -> Optional[WechatAccount]:
    """获取单个公众号"""
    account = db.query(WechatAccount).filter(WechatAccount.id == account_id).first()
    if account:
        account.article_count = db.query(func.count(WechatArticle.id)).filter(
            WechatArticle.wechat_account_id == account.id
        ).scalar() or 0
    return account


def create_wechat_account(
    db: Session,
    competitor_id: int,
    account_name: str,
    account_id: Optional[str] = None,
    description: Optional[str] = None
) -> WechatAccount:
    """创建公众号"""
    db_account = WechatAccount(
        competitor_id=competitor_id,
        account_name=account_name,
        account_id=account_id,
        description=description,
        is_active=1
    )
    db.add(db_account)
    db.commit()
    db.refresh(db_account)
    db_account.article_count = 0
    return db_account


def update_wechat_account(
    db: Session,
    account_id: int,
    account_name: Optional[str] = None,
    account_id_str: Optional[str] = None,
    description: Optional[str] = None,
    is_active: Optional[int] = None
) -> Optional[WechatAccount]:
    """更新公众号"""
    db_account = db.query(WechatAccount).filter(WechatAccount.id == account_id).first()
    if not db_account:
        return None
    if account_name:
        db_account.account_name = account_name
    if account_id_str:
        db_account.account_id = account_id_str
    if description:
        db_account.description = description
    if is_active is not None:
        db_account.is_active = is_active
    db.commit()
    db.refresh(db_account)
    db_account.article_count = db.query(func.count(WechatArticle.id)).filter(
        WechatArticle.wechat_account_id == db_account.id
    ).scalar() or 0
    return db_account


def delete_wechat_account(db: Session, account_id: int) -> bool:
    """删除公众号"""
    db_account = db.query(WechatAccount).filter(WechatAccount.id == account_id).first()
    if not db_account:
        return False
    db.delete(db_account)
    db.commit()
    return True


# ========== 公众号文章 CRUD ==========

def get_wechat_articles(
    db: Session,
    competitor_id: Optional[int] = None,
    wechat_account_id: Optional[int] = None,
    category: Optional[str] = None,
    keyword: Optional[str] = None,
    skip: int = 0,
    limit: int = 20
) -> tuple:
    """获取文章列表"""
    query = db.query(WechatArticle)
    if competitor_id:
        query = query.filter(WechatArticle.competitor_id == competitor_id)
    if wechat_account_id:
        query = query.filter(WechatArticle.wechat_account_id == wechat_account_id)
    if category:
        query = query.filter(WechatArticle.category == category)
    if keyword:
        query = query.filter(
            (WechatArticle.title.contains(keyword)) |
            (WechatArticle.content.contains(keyword)) |
            (WechatArticle.keywords.contains(keyword))
        )
    total = query.count()
    items = query.order_by(WechatArticle.publish_date.desc()).offset(skip).limit(limit).all()
    # 为每篇文章添加公众号名称
    for item in items:
        account = db.query(WechatAccount).filter(WechatAccount.id == item.wechat_account_id).first()
        item.account_name = account.account_name if account else None
    return total, items


def get_wechat_article(db: Session, article_id: int) -> Optional[WechatArticle]:
    """获取单个文章"""
    article = db.query(WechatArticle).filter(WechatArticle.id == article_id).first()
    if article:
        account = db.query(WechatAccount).filter(WechatAccount.id == article.wechat_account_id).first()
        article.account_name = account.account_name if account else None
    return article


def create_wechat_article(
    db: Session,
    wechat_account_id: int,
    competitor_id: int,
    title: str,
    url: str,
    author: Optional[str] = None,
    publish_date: Optional[datetime] = None,
    content: Optional[str] = None,
    keywords: Optional[str] = None,
    category: Optional[str] = None
) -> WechatArticle:
    """创建文章"""
    db_article = WechatArticle(
        wechat_account_id=wechat_account_id,
        competitor_id=competitor_id,
        title=title,
        url=url,
        author=author,
        publish_date=publish_date,
        content=content,
        keywords=keywords,
        category=category
    )
    db.add(db_article)
    db.commit()
    db.refresh(db_article)
    account = db.query(WechatAccount).filter(WechatAccount.id == wechat_account_id).first()
    db_article.account_name = account.account_name if account else None
    return db_article


def update_wechat_article(
    db: Session,
    article_id: int,
    tags: Optional[str] = None,
    category: Optional[str] = None,
    notes: Optional[str] = None,
    summary: Optional[str] = None
) -> Optional[WechatArticle]:
    """更新文章"""
    db_article = db.query(WechatArticle).filter(WechatArticle.id == article_id).first()
    if not db_article:
        return None
    if tags:
        db_article.tags = tags
    if category:
        db_article.category = category
    if notes:
        db_article.notes = notes
    if summary:
        db_article.summary = summary
    db.commit()
    db.refresh(db_article)
    account = db.query(WechatAccount).filter(WechatAccount.id == db_article.wechat_account_id).first()
    db_article.account_name = account.account_name if account else None
    return db_article


def delete_wechat_article(db: Session, article_id: int) -> bool:
    """删除文章"""
    db_article = db.query(WechatArticle).filter(WechatArticle.id == article_id).first()
    if not db_article:
        return False
    db.delete(db_article)
    db.commit()
    return True