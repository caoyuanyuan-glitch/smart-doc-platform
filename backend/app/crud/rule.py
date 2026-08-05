import json
import re
from pathlib import Path

from sqlalchemy.orm import Session
from app.models.rule import Rule
from app.schemas.rule import RuleCreate, RuleUpdate


REVIEW_RULE_LIBRARY_SEED_PATH = Path(__file__).resolve().parents[2] / "seed" / "review_rule_library_seed.json"

# 严重程度映射：种子数据中的中文 → 系统英文标识
SEVERITY_MAP = {
    "致命": "fatal",
    "严重": "serious",
    "一般": "general",
    "建议": "suggestion",
}


def _convert_rule_content_to_regex(rule_content: str) -> str:
    """将规则描述转换为可执行的正则表达式。

    规则描述如检测关键词/模式的规则，提取核心模式转为正则。
    无法转为纯正则的复杂语义规则使用高匹配模式。
    """
    if not rule_content or not rule_content.strip():
        return r"(?!)"

    content = rule_content.strip()
    patterns = []

    # 预定义的规则→正则映射（基于29条种子规则手工整理）
    RULE_PATTERN_MAP = {
        "仅可交互UI元素": r"【[^】]*】|（[^）]*设置[^）]*）",
        "公司官网地址": r"https?://[^\s]+mgi[^\s]*",
        "多余的(空格|空行)": r"[ ]{2,}|\n{3,}",
        "双引号": r"[\'\"](.*?)[\'\"]",
        "中英文混用": r"[\u4e00-\u9fff]\s*[a-zA-Z]{2,}\s*[\u4e00-\u9fff]|[a-zA-Z]{2,}\s[\u4e00-\u9fff]{2,}",
        "乘号": r"\*[×xX]?\s*\d+|\d+\s*\*",
        "错别字.*现成.*现场": r"现场情况|现场",
        "错别字.*避免.*不避免": r"不避免",
        "成语": r"周而复始|恰如其分|千丝万缕|不言而喻|一目了然|举足轻重",
        "文言化": r"未尽事宜|鉴于|据此|兹",
        "标点符号": r"[。，！？；：、\"\"''（）【】《》…—\-,.!?;:\"'()]",
        "引号": r"[\'\"]{2,}|[\u201c\u201d\u2018\u2019]",
        "同义表述": r"(?:点击|轻触|按|按压|长按|双击)",
        "术语.*不一致": r"(?:试剂盒|试剂|样本|标本)",
        "统一使用": r"(?:不可以|不能|不应)",
        "Cat.No": r"Cat\.?\s*No\.?",
    }

    # 匹配规则映射表
    for keyword, pattern in RULE_PATTERN_MAP.items():
        if keyword in content:
            patterns.append(pattern)

    # 如果映射表中没有匹配，则尝试取出引号中的关键词构建正则
    if not patterns:
        quoted = re.findall(r'"([^"]+)"', content)
        if quoted:
            patterns.append("|".join(re.escape(q.strip()) for q in quoted if len(q.strip()) >= 2))
        else:
            # 提取核心关键词（2-4字的中文词或3+字的英文词）
            keywords = re.findall(r'[\u4e00-\u9fff]{2,4}|[A-Za-z]{3,}', content)
            if keywords:
                patterns.append("|".join(re.escape(kw) for kw in keywords[:5]))

    return "|".join(patterns) if patterns else r"(?!)"


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

        rule_content = item.get("rule_content") or ""
        category = item.get("category") or "其他"
        chinese_severity = item.get("severity", "一般")
        severity = SEVERITY_MAP.get(chinese_severity, "general")
        scenarios = "、".join(item.get("applicable_scenarios") or []) or "通用"

        # 将规则内容转为可执行的正则表达式
        regex = _convert_rule_content_to_regex(rule_content)

        db.add(Rule(
            rule_no=rule_no,
            category=category,
            description=rule_content,
            regex=regex,
            example=f"来源: {source} | 适用场景: {scenarios}",
            suggestion=rule_content,
            audit_basis=f"{source}{' | 导出日期: ' + export_date if export_date else ''}",
            severity=severity,
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
        audit_basis=rule.audit_basis,
        severity=rule.severity,
        language=rule.language
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
        if rule_update.severity is not None:
            rule.severity = rule_update.severity
        if rule_update.language is not None:
            rule.language = rule_update.language
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
                audit_basis=rule.audit_basis,
                severity=rule.severity,
                language=rule.language
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
