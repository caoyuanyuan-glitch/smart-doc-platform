from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.api.auth import require_admin
from app.crud.rule import create_rule, get_rule, get_rule_by_no, get_rules, update_rule, delete_rule, bulk_create_rules, bulk_delete_rules
from app.schemas.rule import Rule, RuleCreate, RuleUpdate

router = APIRouter(dependencies=[Depends(require_admin)])

@router.post("/", response_model=Rule)
async def create_new_rule(rule: RuleCreate, db: Session = Depends(get_db)):
    existing = get_rule_by_no(db, rule.rule_no)
    if existing:
        raise HTTPException(status_code=400, detail="Rule already exists")
    
    return create_rule(db=db, rule=rule)

@router.get("/", response_model=list[Rule])
async def read_rules(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    rules = get_rules(db, skip=skip, limit=limit)
    return rules

@router.post("/bulk")
async def bulk_create(rules: list[RuleCreate], db: Session = Depends(get_db)):
    count = bulk_create_rules(db, rules)
    return {"message": f"Created {count} rules", "created": count, "total": len(rules)}

@router.delete("/bulk")
async def bulk_delete(rule_ids: list[int] = Query(None), db: Session = Depends(get_db)):
    if not rule_ids:
        raise HTTPException(status_code=400, detail="No rule IDs provided")
    count = bulk_delete_rules(db, rule_ids)
    return {"message": f"Deleted {count} rules"}

# 静态路径必须注册在 /{rule_id} 之前，否则 /export 会被 /{rule_id} 抢先匹配，
# rule_id 无法解析为整数而返回 422。
@router.get("/export")
async def export_rules(db: Session = Depends(get_db)):
    rules = get_rules(db, skip=0, limit=10000)
    rules_list = []
    for rule in rules:
        rules_list.append({
            "rule_no": rule.rule_no,
            "category": rule.category,
            "description": rule.description,
            "regex": rule.regex,
            "example": rule.example,
            "suggestion": rule.suggestion,
            "audit_basis": rule.audit_basis,
            "severity": rule.severity,
            "language": rule.language
        })
    return JSONResponse(content=rules_list)

@router.get("/{rule_id}", response_model=Rule)
async def read_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = get_rule(db, rule_id=rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule

@router.put("/{rule_id}", response_model=Rule)
async def update_existing_rule(rule_id: int, rule_update: RuleUpdate, db: Session = Depends(get_db)):
    rule = update_rule(db, rule_id=rule_id, rule_update=rule_update)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule

@router.delete("/{rule_id}")
async def delete_existing_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = delete_rule(db, rule_id=rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"message": "Rule deleted successfully"}
