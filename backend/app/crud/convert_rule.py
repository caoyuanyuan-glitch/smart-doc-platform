from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.convert_rule import ConvertRule
from app.schemas.convert_rule import ConvertRuleCreate
from datetime import datetime


def _next_rule_number(db: Session) -> str:
    max_num = db.query(func.max(ConvertRule.rule_number)).scalar()
    if max_num and max_num.startswith("R"):
        try:
            n = int(max_num[1:]) + 1
        except ValueError:
            n = 1
    else:
        n = 1
    return f"R{n:03d}"


def create_convert_rule(db: Session, rule: ConvertRuleCreate):
    rule_number = rule.rule_number or _next_rule_number(db)
    db_rule = ConvertRule(
        rule_number=rule_number,
        category=rule.category,
        description=rule.description,
        is_active=rule.is_active if rule.is_active is not None else True,
    )
    db.add(db_rule)
    db.commit()
    db.refresh(db_rule)
    return db_rule


def get_convert_rule(db: Session, rule_id: int):
    return db.query(ConvertRule).filter(ConvertRule.id == rule_id).first()


def get_convert_rules(db: Session, skip: int = 0, limit: int = 200):
    return db.query(ConvertRule).order_by(ConvertRule.rule_number).offset(skip).limit(limit).all()


def get_active_rules(db: Session):
    return db.query(ConvertRule).filter(ConvertRule.is_active == True).order_by(ConvertRule.rule_number).all()


def toggle_convert_rule(db: Session, rule_id: int):
    rule = db.query(ConvertRule).filter(ConvertRule.id == rule_id).first()
    if rule:
        rule.is_active = not rule.is_active
        db.commit()
        db.refresh(rule)
    return rule


def delete_convert_rule(db: Session, rule_id: int):
    rule = db.query(ConvertRule).filter(ConvertRule.id == rule_id).first()
    if rule:
        db.delete(rule)
        db.commit()
    return rule


def bulk_delete_convert_rules(db: Session, rule_ids: list[int]):
    count = db.query(ConvertRule).filter(ConvertRule.id.in_(rule_ids)).delete(synchronize_session=False)
    db.commit()
    return count


def seed_default_rules(db: Session):
    defaults = [
        ("R001", "内容", "转换内容须100%与原文保持一致，不得遗漏或添加任何文字、符号、空白段落"),
        ("R002", "图片", "原文中引用的外部图片须下载并嵌入到输出文档包中，确保离线可查看"),
        ("R003", "编号", "去除所有章节标题前的编号（如1.1、Chapter 1:、第1章 等），由模板样式自动生成"),
        ("R004", "表格标题", "表格标题（Table N-N xxx）须识别并转换为DITA table/title标签对"),
        ("R005", "列表-无序", "Markdown无序列表（-/*/+开头）须转换为DITA ul/li标签"),
        ("R006", "列表-有序", "Markdown有序列表（1./1)开头）须转换为DITA ol/li标签"),
        ("R007", "结构", "所有标题层级（H1-H6）均拆分为独立topic，各topic通过bookmap组织"),
        ("R008", "模板", "提供参考模板时复用frontmatter整段（含Cover等子章节）及Manufacturer附录"),
    ]
    count = 0
    for rn, cat, desc in defaults:
        existing = db.query(ConvertRule).filter(ConvertRule.rule_number == rn).first()
        if not existing:
            db.add(ConvertRule(
                rule_number=rn, category=cat, description=desc,
                is_active=True, created_at=datetime.utcnow()
            ))
            count += 1
    if count:
        db.commit()
    return count
