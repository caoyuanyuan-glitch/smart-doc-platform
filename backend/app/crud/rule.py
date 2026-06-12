from sqlalchemy.orm import Session
from app.models.rule import Rule
from app.schemas.rule import RuleCreate, RuleUpdate

def create_rule(db: Session, rule: RuleCreate):
    db_rule = Rule(
        rule_no=rule.rule_no,
        category=rule.category,
        description=rule.description,
        regex=rule.regex,
        example=rule.example
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
                example=rule.example
            ))
    if db_rules:
        db.add_all(db_rules)
        db.commit()
    return len(db_rules)
