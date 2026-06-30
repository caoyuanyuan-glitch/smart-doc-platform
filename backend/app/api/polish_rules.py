import csv
import io
import json

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.crud import polish_learning_rule as crud
from app.schemas.polish_learning_rule import (
    PolishLearningRuleCreate,
    PolishLearningRuleUpdate,
    PolishLearningRuleOut,
    PolishLearningRuleBatchImport,
    PolishLearningRuleBatchDelete,
)

router = APIRouter(prefix="/api/polish-rules", tags=["润色规则管理"])

# 合法的规则分类值
VALID_RULE_TYPES = {"system_rule", "replacement_rule", "forbidden_rule", "sentence_applicability_rule"}


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/", response_model=dict)
def list_rules(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    rule_type: str = Query(None),
    enabled: bool = Query(None),
    db: Session = Depends(get_db),
):
    rules = crud.get_rules(db, skip=skip, limit=limit, rule_type=rule_type, enabled=enabled)
    total = crud.count_rules(db, rule_type=rule_type, enabled=enabled)
    return {
        "total": total,
        "items": [PolishLearningRuleOut.model_validate(r).model_dump() for r in rules],
    }


@router.get("/{rule_id}", response_model=PolishLearningRuleOut)
def get_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = crud.get_rule(db, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    return PolishLearningRuleOut.model_validate(rule)


@router.post("/", response_model=PolishLearningRuleOut)
def create_rule(rule: PolishLearningRuleCreate, db: Session = Depends(get_db)):
    existing = crud.get_rule_by_key(db, rule.rule_key)
    if existing:
        raise HTTPException(status_code=400, detail=f"规则键 {rule.rule_key} 已存在")
    return PolishLearningRuleOut.from_orm(crud.create_rule(db, rule))


@router.put("/{rule_id}", response_model=PolishLearningRuleOut)
def update_rule(rule_id: int, rule_update: PolishLearningRuleUpdate, db: Session = Depends(get_db)):
    updated = crud.update_rule(db, rule_id, rule_update)
    if not updated:
        raise HTTPException(status_code=404, detail="规则不存在")
    return PolishLearningRuleOut.from_orm(updated)


@router.delete("/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    success = crud.delete_rule(db, rule_id)
    if not success:
        raise HTTPException(status_code=404, detail="规则不存在")
    return {"ok": True}


@router.post("/batch-delete")
def batch_delete_rules(body: PolishLearningRuleBatchDelete, db: Session = Depends(get_db)):
    deleted = crud.batch_delete_rules(db, body.ids)
    return {"ok": True, "deleted": deleted}


@router.get("/export/json")
def export_rules_json(
    rule_type: str = Query(None),
    db: Session = Depends(get_db),
):
    from fastapi.responses import StreamingResponse
    rules_data = crud.export_rules(db, rule_type=rule_type)
    content = json.dumps(rules_data, ensure_ascii=False, indent=2)
    return StreamingResponse(
        io.BytesIO(content.encode("utf-8")),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=polish_rules.json"},
    )


@router.get("/export/csv")
def export_rules_csv(
    rule_type: str = Query(None),
    db: Session = Depends(get_db),
):
    from fastapi.responses import StreamingResponse
    rules_data = crud.export_rules(db, rule_type=rule_type)
    output = io.StringIO()
    if rules_data:
        writer = csv.DictWriter(output, fieldnames=rules_data[0].keys())
        writer.writeheader()
        writer.writerows(rules_data)
    content = output.getvalue()
    return StreamingResponse(
        io.BytesIO(content.encode("utf-8-sig")),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=polish_rules.csv"},
    )


@router.post("/import/json")
def import_rules_json(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="仅支持 .json 文件")
    try:
        content = file.file.read().decode("utf-8")
        rules_data = json.loads(content)
    except Exception:
        raise HTTPException(status_code=400, detail="JSON 解析失败")
    if not isinstance(rules_data, list):
        raise HTTPException(status_code=400, detail="JSON 文件应包含规则数组")

    # 中文键名 → 英文字段名映射
    FIELD_MAP = {
        "规则名称": "rule_name",
        "规则分类": "rule_type",
        "匹配模式": "match_pattern",
        "替换文本": "replacement_text",
        "说明": "description",
        "优先级": "priority_level",
        "是否启用": "enabled",
    }
    for item in rules_data:
        for chinese, english in FIELD_MAP.items():
            if chinese in item:
                item[english] = item.pop(chinese)
        # 校验规则分类
        rule_type = item.get("rule_type", "")
        if rule_type and rule_type not in VALID_RULE_TYPES:
            raise HTTPException(status_code=400, detail=f"无效的规则分类「{rule_type}」，可选: {', '.join(sorted(VALID_RULE_TYPES))}")

    result = crud.import_rules(db, rules_data)
    return {"ok": True, **result}


@router.post("/import/csv")
def import_rules_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="仅支持 .csv 文件")
    try:
        content = file.file.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
        rules_data = list(reader)
    except Exception:
        raise HTTPException(status_code=400, detail="CSV 解析失败")
    if not rules_data:
        raise HTTPException(status_code=400, detail="CSV 文件为空")

    # 中文表头 → 英文字段名映射
    FIELD_MAP = {
        "规则名称": "rule_name",
        "规则分类": "rule_type",
        "匹配模式": "match_pattern",
        "替换文本": "replacement_text",
        "说明": "description",
        "优先级": "priority_level",
        "是否启用": "enabled",
    }

    # Convert types and translate headers
    for row in rules_data:
        # Rename Chinese headers to English
        for chinese, english in FIELD_MAP.items():
            if chinese in row:
                row[english] = row.pop(chinese)
        # 校验规则分类
        rule_type = row.get("rule_type", "")
        if rule_type and rule_type not in VALID_RULE_TYPES:
            raise HTTPException(status_code=400, detail=f"无效的规则分类「{rule_type}」，可选: {', '.join(sorted(VALID_RULE_TYPES))}")
        row["priority_level"] = int(row.get("priority_level", 0))
        row["enabled"] = str(row.get("enabled", "True")).lower() in ("true", "1", "yes")
        row["trigger_count"] = int(row.get("trigger_count", 0))
    result = crud.import_rules(db, rules_data)
    return {"ok": True, **result}
