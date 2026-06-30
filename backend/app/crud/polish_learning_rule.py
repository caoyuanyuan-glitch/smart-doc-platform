from sqlalchemy.orm import Session

from app.models.polish_learning_rule import PolishLearningRule
from app.schemas.polish_learning_rule import PolishLearningRuleCreate, PolishLearningRuleUpdate


def get_rules(db: Session, skip: int = 0, limit: int = 100, rule_type: str = None, enabled: bool = None):
    q = db.query(PolishLearningRule)
    if rule_type:
        q = q.filter(PolishLearningRule.rule_type == rule_type)
    if enabled is not None:
        q = q.filter(PolishLearningRule.enabled == enabled)
    return q.order_by(PolishLearningRule.id.desc()).offset(skip).limit(limit).all()


def count_rules(db: Session, rule_type: str = None, enabled: bool = None):
    q = db.query(PolishLearningRule)
    if rule_type:
        q = q.filter(PolishLearningRule.rule_type == rule_type)
    if enabled is not None:
        q = q.filter(PolishLearningRule.enabled == enabled)
    return q.count()


def get_rule(db: Session, rule_id: int):
    return db.query(PolishLearningRule).filter(PolishLearningRule.id == rule_id).first()


def get_rule_by_key(db: Session, rule_key: str):
    return db.query(PolishLearningRule).filter(PolishLearningRule.rule_key == rule_key).first()


def create_rule(db: Session, rule: PolishLearningRuleCreate):
    db_rule = PolishLearningRule(
        rule_name=rule.rule_name,
        rule_type=rule.rule_type,
        engine_key=rule.engine_key,
        rule_key=rule.rule_key,
        match_pattern=rule.match_pattern,
        replacement_text=rule.replacement_text,
        description=rule.description,
        priority_level=rule.priority_level,
        enabled=rule.enabled,
    )
    db.add(db_rule)
    db.commit()
    db.refresh(db_rule)
    return db_rule


def update_rule(db: Session, rule_id: int, rule_update: PolishLearningRuleUpdate):
    db_rule = db.query(PolishLearningRule).filter(PolishLearningRule.id == rule_id).first()
    if not db_rule:
        return None
    update_data = rule_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_rule, field, value)
    db.commit()
    db.refresh(db_rule)
    return db_rule


def delete_rule(db: Session, rule_id: int):
    db_rule = db.query(PolishLearningRule).filter(PolishLearningRule.id == rule_id).first()
    if db_rule:
        db.delete(db_rule)
        db.commit()
        return True
    return False


def batch_delete_rules(db: Session, ids: list[int]):
    deleted = db.query(PolishLearningRule).filter(PolishLearningRule.id.in_(ids)).delete(synchronize_session=False)
    db.commit()
    return deleted


def export_rules(db: Session, rule_type: str = None):
    q = db.query(PolishLearningRule)
    if rule_type:
        q = q.filter(PolishLearningRule.rule_type == rule_type)
    rules = q.order_by(PolishLearningRule.id).all()
    return [
        {
            "规则名称": r.rule_name,
            "规则分类": r.rule_type,
            "匹配模式": r.match_pattern,
            "替换文本": r.replacement_text,
            "说明": r.description,
            "优先级": r.priority_level,
            "是否启用": r.enabled,
        }
        for r in rules
    ]


def import_rules(db: Session, rules_data: list[dict]) -> dict:
    import time
    created = 0
    updated = 0
    skipped = 0
    for item in rules_data:
        existing = get_rule_by_key(db, item.get("rule_key", ""))
        if existing:
            # Update existing
            for field in ("rule_name", "rule_type", "engine_key", "match_pattern", "replacement_text", "description", "priority_level", "enabled"):
                if field in item:
                    setattr(existing, field, item[field])
            updated += 1
        else:
            # Auto-generate rule_key if not provided
            rule_key = item.get("rule_key") or f"manual:{item.get('rule_type', '')}:{int(time.time() * 1000)}"
            db_rule = PolishLearningRule(
                rule_name=item.get("rule_name"),
                rule_type=item.get("rule_type", ""),
                engine_key=item.get("engine_key"),
                rule_key=rule_key,
                match_pattern=item.get("match_pattern", ""),
                replacement_text=item.get("replacement_text"),
                description=item.get("description"),
                priority_level=item.get("priority_level", 0),
                enabled=item.get("enabled", True),
            )
            db.add(db_rule)
            created += 1
    db.commit()
    return {"created": created, "updated": updated, "skipped": skipped}


def get_enabled_engine_keys(db: Session) -> list:
    """获取所有启用的系统规则的 engine_key 列表，供规则引擎使用。"""
    rules = db.query(PolishLearningRule)\
        .filter(PolishLearningRule.rule_type == 'system_rule')\
        .filter(PolishLearningRule.enabled == True)\
        .all()
    return [r.engine_key for r in rules if r.engine_key]


def seed_system_rules(db: Session) -> int:
    """初始化 5 条系统规则到数据库（使用原始 SQL 避免 FK 约束校验）。已存在则跳过。"""
    from sqlalchemy import text
    system_rules = [
        {
            "rule_name": "术语替换",
            "rule_type": "system_rule",
            "engine_key": "termReplace",
            "rule_key": "system:termReplace",
            "match_pattern": "完整词边界匹配，非标准术语→标准术语",
            "replacement_text": "仅替换明确错误的非标准说法，通用名词不匹配",
            "description": "保守匹配：只替换完整词且明确错误的非标准说法。如'试验台'→'操作台'，不匹配通用名词如'仪器'。",
            "priority_level": 10,
            "enabled": 1,
        },
        {
            "rule_name": "祈使句规范",
            "rule_type": "system_rule",
            "engine_key": "imperativePlease",
            "rule_key": "system:imperativePlease",
            "match_pattern": "操作类动词(点击/输入/打开…)→不加请 | 建议类(检查/确认/避免…)→加请 | 警告类(严禁/禁止…)→保持",
            "replacement_text": "根据动词分类自动处理'请'字",
            "description": "操作类动词不加'请'（如'点击下一步'），建议类动词加'请'（如'请确认'），警告类保持原样（如'严禁触碰'）。",
            "priority_level": 20,
            "enabled": 1,
        },
        {
            "rule_name": "数字单位空格",
            "rule_type": "system_rule",
            "engine_key": "numberSpace",
            "rule_key": "system:numberSpace",
            "match_pattern": r"\d+\.?\d*\s*(μL|mL|L|℃|rpm|mm|cm|m|kg|g|mg|μg|s|min|h|V|A|W|Hz|%)",
            "replacement_text": "在数字和单位之间加空格",
            "description": "数字与单位之间加一个空格：200μL→200 μL，20℃→20 ℃，100rpm→100 rpm。",
            "priority_level": 30,
            "enabled": 1,
        },
        {
            "rule_name": "中英文空格",
            "rule_type": "system_rule",
            "engine_key": "cnEnSpace",
            "rule_key": "system:cnEnSpace",
            "match_pattern": r"[\u4e00-\u9fff][A-Za-z0-9]|[A-Za-z0-9][\u4e00-\u9fff]",
            "replacement_text": "在中文与英文/数字之间加空格",
            "description": "中文与英文/数字之间加空格：AIO基因→AIO 基因。例外：英文缩写与数字之间不加空格（V1.0保持）。",
            "priority_level": 40,
            "enabled": 1,
        },
        {
            "rule_name": "标点规范",
            "rule_type": "system_rule",
            "engine_key": "punctuation",
            "rule_key": "system:punctuation",
            "match_pattern": "句尾缺标点(.|!|?) | 条件句后缺逗号",
            "replacement_text": "补充缺失的标点符号",
            "description": "句尾缺少标点时补充句号，条件从句后补充逗号（如'如需修改密码可点击'→'如需修改密码，可点击'）。",
            "priority_level": 50,
            "enabled": 1,
        },
    ]

    created = 0
    sql = text(
        "INSERT INTO polish_learning_rules (rule_name, rule_type, engine_key, rule_key, match_pattern, replacement_text, description, priority_level, enabled) "
        "VALUES (:rule_name, :rule_type, :engine_key, :rule_key, :match_pattern, :replacement_text, :description, :priority_level, :enabled)"
    )
    for item in system_rules:
        check = db.execute(
            text("SELECT id FROM polish_learning_rules WHERE rule_key = :rk"),
            {"rk": item["rule_key"]}
        ).fetchone()
        if check:
            continue
        db.execute(sql, item)
        created += 1

    if created:
        db.commit()
    return created
