from sqlalchemy import or_
from sqlalchemy.orm import Session
from app.models.review import Review
from app.models.issue import Issue
from app.models.document import Document
from app.models.false_positive_memory import FalsePositiveMemory
from app.schemas.review import ReviewCreate, IssueCreate, IssueUpdate
from datetime import datetime


PRESET_FALSE_POSITIVE_MEMORY_ENTRIES = [
    (
        "FP-V1-001",
        "排版格式类",
        "嵌套有序列表编号差异是正常层级表达：外层 1. 2. 3.、内层子步骤 1) 2) 3)（ol 嵌套），不标记格式不统一",
    ),
    (
        "FP-V1-002",
        "排版格式类",
        "正文商标 ® 不要求重复标注：商标声明页即首次出现处，声明页已带 ® 即合规，正文中的商标名不再加 ®",
    ),
    (
        "FP-V1-003",
        "排版格式类",
        "软件实际生成的文件名，占位符+名称直接拼接（如 ROINAMEquantification.csv）属产品命名规则，不标记文件名连写",
    ),
    (
        "FP-V1-004",
        "PDF文本提取伪影类",
        "内嵌图标/按钮图片不会进入文本层，界面图标引用处显示缺失是工具限制，不判缺失图标；须渲染页面图像核实后再下结论",
    ),
    (
        "FP-V1-005",
        "PDF文本提取伪影类",
        "弯引号开/直引号闭的混用，多为字体 ToUnicode 映射伪影，不上报",
    ),
    (
        "FP-V1-006",
        "PDF文本提取伪影类",
        '英文句号在闭引号外（"xxx".）属英式标点风格，可接受，不上报',
    ),
    (
        "FP-V1-007",
        "PDF文本提取伪影类",
        "文本层单复数/短语动词词序异常（如 following status、turn on it）按可接受表达/提取伪影处理，不上报；以渲染页实际显示为准",
    ),
    (
        "FP-V1-008",
        "PDF文本提取伪影类",
        "双层文本层重复（如 一旦您开始使 / 一旦您开始使 / 用本软件）是提取伪影，非文档问题，不上报",
    ),
    (
        "FP-V1-009",
        "内容规范类",
        "海外（英文）手册的制造商/联系信息仅提供 Email、不写电话，属行业惯例与公司海外手册规范，不标记缺联系电话",
    ),
    (
        "FP-V1-012",
        "内容规范类",
        "海外（英文）手册中 https://global-mgitech.com 是正确官网地址，不标记官网地址错误或术语一致性问题",
    ),
    (
        "FP-V1-010",
        "已判定排除的疑点",
        "表 17/18 标题完全相同（凸阵式探头 B 模式声输出数据）：额定频率不同（3.5 vs 5.0 MHz），属同探头不同频率档的合规表达",
    ),
    (
        "FP-V1-011",
        "已判定排除的疑点",
        "缺页码（目录页码与实际章节页不符的扫描结果）：均为章节隔页/留白页（隔页显示章号 01-08），属正常排版",
    ),
]


def _false_positive_memory_signature(rule: str, category: str, original_text: str) -> str:
    return f"{rule}|{category}|{original_text}".strip().lower()[:512]

def create_review(db: Session, review: ReviewCreate):
    db_review = Review(
        document_id=review.document_id,
        mode=review.mode,
        provider=review.provider,
    )
    db.add(db_review)
    db.commit()
    db.refresh(db_review)
    return db_review

def get_review(db: Session, review_id: int):
    return db.query(Review).filter(Review.id == review_id).first()

def get_reviews(db: Session, document_id: int = None, skip: int = 0, limit: int = 100):
    query = db.query(Review)
    if document_id is not None:
        query = query.filter(Review.document_id == document_id)
    return query.order_by(Review.id.desc()).offset(skip).limit(limit).all()

def update_review_status(db: Session, review_id: int, status: str, total_issues: int = 0, summary: str = ""):
    review = db.query(Review).filter(Review.id == review_id).first()
    if review:
        review.status = status
        review.total_issues = total_issues
        review.summary = summary
        if status in {"completed", "failed", "cancelled"}:
            review.completed_at = datetime.utcnow()
        db.commit()
        db.refresh(review)
    return review

def create_issue(db: Session, issue: IssueCreate):
    db_issue = Issue(
        review_id=issue.review_id,
        severity=issue.severity,
        category=issue.category,
        rule=issue.rule,
        chapter=issue.chapter,
        original_text=issue.original_text,
        context=issue.context,
        suggestion=issue.suggestion,
        description=issue.description,
        audit_basis=issue.audit_basis,
        confidence=issue.confidence,
        source=issue.source,
        position=issue.position,
        status=issue.status,
        providers=issue.providers,
    )
    db.add(db_issue)
    db.commit()
    db.refresh(db_issue)
    return db_issue

def get_issues(db: Session, review_id: int):
    return db.query(Issue).filter(Issue.review_id == review_id).all()

def update_issue(db: Session, issue_id: int, issue_update: IssueUpdate):
    issue = db.query(Issue).filter(Issue.id == issue_id).first()
    if issue:
        issue.status = issue_update.status
        db.commit()
        db.refresh(issue)
    return issue


def seed_preset_false_positive_memory(db: Session):
    inserted = 0
    for rule, category, original_text in PRESET_FALSE_POSITIVE_MEMORY_ENTRIES:
        signature = _false_positive_memory_signature(rule, category, original_text)
        exists = (
            db.query(FalsePositiveMemory)
            .filter(FalsePositiveMemory.signature == signature)
            .first()
        )
        if exists:
            continue
        db.add(FalsePositiveMemory(
            source_issue_id=0,
            signature=signature,
            rule=rule,
            category=category,
            original_text=original_text,
            enabled=True,
        ))
        inserted += 1
    if inserted:
        db.commit()
    return inserted


def list_false_positive_memory_signatures(db: Session):
    rows = db.query(FalsePositiveMemory).filter(FalsePositiveMemory.enabled.is_(True)).all()
    return {str(row.signature or '').strip().lower() for row in rows if str(row.signature or '').strip()}


def delete_false_positive_memory_for_issue(db: Session, source_issue_id: int):
    db.query(FalsePositiveMemory).filter(FalsePositiveMemory.source_issue_id == source_issue_id).delete(synchronize_session=False)
    db.commit()


def upsert_false_positive_memory_for_issue(db: Session, issue, signatures: set[str]):
    normalized_signatures = {
        str(signature or '').strip().lower()
        for signature in signatures
        if str(signature or '').strip()
    }
    db.query(FalsePositiveMemory).filter(FalsePositiveMemory.source_issue_id == issue.id).delete(synchronize_session=False)
    for signature in sorted(normalized_signatures):
        db.add(FalsePositiveMemory(
            source_issue_id=issue.id,
            signature=signature,
            rule=str(getattr(issue, 'rule', '') or ''),
            category=str(getattr(issue, 'category', '') or ''),
            original_text=str(getattr(issue, 'original_text', '') or ''),
            enabled=True,
        ))
    db.commit()


def list_false_positive_memory(db: Session, keyword: str = "", skip: int = 0, limit: int = 50):
    query = (
        db.query(FalsePositiveMemory, Issue, Review, Document)
        .outerjoin(Issue, Issue.id == FalsePositiveMemory.source_issue_id)
        .outerjoin(Review, Review.id == Issue.review_id)
        .outerjoin(Document, Document.id == Review.document_id)
    )

    normalized_keyword = str(keyword or "").strip()
    if normalized_keyword:
        like_pattern = f"%{normalized_keyword}%"
        query = query.filter(or_(
            FalsePositiveMemory.signature.ilike(like_pattern),
            FalsePositiveMemory.rule.ilike(like_pattern),
            FalsePositiveMemory.category.ilike(like_pattern),
            FalsePositiveMemory.original_text.ilike(like_pattern),
            Document.filename.ilike(like_pattern),
        ))

    total = query.count()
    rows = (
        query.order_by(FalsePositiveMemory.created_at.desc(), FalsePositiveMemory.id.desc())
        .offset(max(skip, 0))
        .limit(max(1, limit))
        .all()
    )

    items = []
    for memory, issue, review, document in rows:
        document_name = str(getattr(document, "filename", "") or "")
        if not document_name and getattr(memory, "source_issue_id", None) == 0:
            document_name = "预置"
        items.append({
            "id": memory.id,
            "source_issue_id": memory.source_issue_id,
            "signature": str(memory.signature or ""),
            "rule": str(memory.rule or ""),
            "category": str(memory.category or ""),
            "original_text": str(memory.original_text or ""),
            "created_at": memory.created_at,
            "review_id": getattr(review, "id", None),
            "document_id": getattr(document, "id", None),
            "document_name": document_name,
        })
    return items, total


def delete_false_positive_memory_entry(db: Session, memory_id: int):
    entry = db.query(FalsePositiveMemory).filter(FalsePositiveMemory.id == memory_id).first()
    if entry:
        db.delete(entry)
        db.commit()
    return entry

def delete_issue(db: Session, issue_id: int):
    issue = db.query(Issue).filter(Issue.id == issue_id).first()
    if issue:
        db.delete(issue)
        db.commit()
    return issue


def delete_reviews_by_document(db: Session, document_id: int):
    reviews = db.query(Review).filter(Review.document_id == document_id).all()
    if not reviews:
        return 0

    review_ids = [review.id for review in reviews]
    db.query(Issue).filter(Issue.review_id.in_(review_ids)).delete(synchronize_session=False)
    db.query(Review).filter(Review.id.in_(review_ids)).delete(synchronize_session=False)
    db.commit()
    return len(review_ids)
