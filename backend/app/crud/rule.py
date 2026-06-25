import json
from pathlib import Path

from sqlalchemy.orm import Session
from app.models.rule import Rule
from app.schemas.rule import RuleCreate, RuleUpdate


REVIEW_RULE_LIBRARY_SEED_PATH = Path(__file__).resolve().parents[2] / "seed" / "review_rule_library_seed.json"


def seed_external_review_rules(db: Session):
    if not REVIEW_RULE_LIBRARY_SEED_PATH.exists():
        return 0

    payload = json.loads(REVIEW_RULE_LIBRARY_SEED_PATH.read_text(encoding="utf-8"))
    source = payload.get("source", "外部评审规则库")
    export_date = payload.get("export_date", "")
    created = 0

    for item in payload.get("rules", []):
        original_rule_id = str(item.get("rule_id", "")).strip()
        if not original_rule_id:
            continue

        rule_no = f"EXT-{original_rule_id}"
        if get_rule_by_no(db, rule_no):
            continue

        scenarios = "、".join(item.get("applicable_scenarios") or []) or "通用"
        sync_status = "已同步" if item.get("synced") else "未同步"
        severity = item.get("severity", "一般")

        db.add(Rule(
            rule_no=rule_no,
            category=item.get("category") or "其他",
            description=item.get("rule_content") or "",
            regex=r"(?!)",
            example=f"原编号: {original_rule_id} | 适用场景: {scenarios} | 同步状态: {sync_status}",
            suggestion=f"严重级别: {severity} | 该规则当前作为规则库知识展示，请人工确认后补充可执行规则。",
            audit_basis=f"{source}{' | 导出日期: ' + export_date if export_date else ''}",
            language="both",
        ))
        created += 1

    if created:
        db.commit()
    return created

def create_rule(db: Session, rule: RuleCreate):
    db_rule = Rule(
        rule_no=rule.rule_no,
        category=rule.category,
        description=rule.description,
        regex=rule.regex,
        example=rule.example,
        suggestion=rule.suggestion,
        audit_basis=rule.audit_basis
    )
    db.add(db_rule)
    db.commit()
    db.refresh(db_rule)
    return db_rule

def get_rule(db: Session, rule_id: int):
    return db.query(Rule).filter(Rule.id == rule_id).first()

def get_rule_by_no(db: Session, rule_no: str):
    return db.query(Rule).filter(Rule.rule_no == rule_no).first()

def get_rules(db: Session, skip: int = 0, limit: int = 100):
    return db.query(Rule).offset(skip).limit(limit).all()

def update_rule(db: Session, rule_id: int, rule_update: RuleUpdate):
    rule = db.query(Rule).filter(Rule.id == rule_id).first()
    if rule:
        if rule_update.category is not None:
            rule.category = rule_update.category
        if rule_update.description is not None:
            rule.description = rule_update.description
        if rule_update.regex is not None:
            rule.regex = rule_update.regex
        if rule_update.example is not None:
            rule.example = rule_update.example
        if rule_update.suggestion is not None:
            rule.suggestion = rule_update.suggestion
        if rule_update.audit_basis is not None:
            rule.audit_basis = rule_update.audit_basis
        db.commit()
        db.refresh(rule)
    return rule

def delete_rule(db: Session, rule_id: int):
    rule = db.query(Rule).filter(Rule.id == rule_id).first()
    if rule:
        db.delete(rule)
        db.commit()
    return rule

def bulk_create_rules(db: Session, rules: list[RuleCreate]):
    db_rules = []
    for rule in rules:
        if not get_rule_by_no(db, rule.rule_no):
            db_rules.append(Rule(
                rule_no=rule.rule_no,
                category=rule.category,
                description=rule.description,
                regex=rule.regex,
                example=rule.example,
                suggestion=rule.suggestion,
                audit_basis=rule.audit_basis
            ))
    if db_rules:
        db.add_all(db_rules)
        db.commit()
    return len(db_rules)

def bulk_delete_rules(db: Session, rule_ids: list[int]):
    count = 0
    for rule_id in rule_ids:
        rule = db.query(Rule).filter(Rule.id == rule_id).first()
        if rule:
            db.delete(rule)
            count += 1
    db.commit()
    return count
