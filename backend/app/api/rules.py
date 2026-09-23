from datetime import date
from io import BytesIO

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.api.auth import require_admin
from app.crud.rule import create_rule, get_rule, get_rule_by_no, get_rules, update_rule, delete_rule, bulk_create_rules, bulk_delete_rules
from app.schemas.rule import Rule, RuleCreate, RuleUpdate

router = APIRouter(dependencies=[Depends(require_admin)])

# 规则库的导入导出统一使用 Excel，列顺序与页面字段一一对应。
RULE_EXPORT_COLUMNS = (
    ("规则编号", "rule_no", 16),
    ("分类", "category", 14),
    ("规则描述", "description", 60),
    ("正则", "regex", 40),
    ("示例", "example", 32),
    ("建议", "suggestion", 32),
    ("审核依据", "audit_basis", 34),
    ("严重程度", "severity", 12),
    ("语言", "language", 12),
)
REQUIRED_FIELDS = ("rule_no", "category", "description", "regex")

SEVERITY_LABELS = {"fatal": "致命", "serious": "严重", "general": "一般", "suggestion": "建议"}
LANGUAGE_LABELS = {"cn": "中文", "en": "英文", "both": "中英通用"}

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

TEMPLATE_GUIDE_ROWS = (
    ("规则编号", "必填", "规则的唯一标识，库中已存在的编号会被跳过。示例：R-EXAMPLE-001", "R-EXAMPLE-001"),
    ("分类", "必填", "规则所属分类。示例：拼写 / 格式错误 / 语法", "拼写"),
    ("规则描述", "必填", "说明该规则检查什么问题", "检查误拼写 teh"),
    ("正则", "必填", "规则对应的正则表达式", r"\bteh\b"),
    ("示例", "选填", "命中该规则的示例文本", "to return to teh lab"),
    ("建议", "选填", "修改建议", "改为 the"),
    ("审核依据", "选填", "规则来源或依据", "英语语法规范 - 拼写"),
    ("严重程度", "选填", "可填：致命 / 严重 / 一般 / 建议。留空按「一般」处理", "一般"),
    ("语言", "选填", "可填：中文 / 英文 / 中英通用。留空按「中英通用」处理", "中英通用"),
)


def _normalize_choice(raw, labels, default):
    """严重程度/语言既接受中文标签，也接受英文枚举值。"""
    text = str(raw or "").strip()
    if not text:
        return default
    if text in labels:
        return text
    lowered = text.lower()
    if lowered in labels.values():
        return lowered
    return None


def _build_rules_workbook(rules):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "规则库"
    header_fill = PatternFill("solid", fgColor="E8F1FF")
    header_font = Font(bold=True)
    wrap = Alignment(vertical="top", wrap_text=True)

    for index, (title, _field, width) in enumerate(RULE_EXPORT_COLUMNS, start=1):
        cell = sheet.cell(row=1, column=index, value=title)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = wrap
        sheet.column_dimensions[get_column_letter(index)].width = width
    sheet.freeze_panes = "A2"

    for offset, rule in enumerate(rules, start=2):
        for index, (_title, field, _width) in enumerate(RULE_EXPORT_COLUMNS, start=1):
            if field == "severity":
                value = SEVERITY_LABELS.get(rule.severity, rule.severity)
            elif field == "language":
                value = LANGUAGE_LABELS.get(rule.language, rule.language)
            else:
                value = getattr(rule, field, "")
            cell = sheet.cell(row=offset, column=index, value=value)
            cell.alignment = wrap
    return workbook


def _build_template_workbook():
    from openpyxl.styles import Alignment, Font

    workbook = _build_rules_workbook([])
    guide = workbook.create_sheet("填写说明")
    guide.append(("列名", "是否必填", "说明", "示例值"))
    for cell in guide[1]:
        cell.font = Font(bold=True)
    for row in TEMPLATE_GUIDE_ROWS:
        guide.append(row)
    guide.column_dimensions["A"].width = 14
    guide.column_dimensions["B"].width = 10
    guide.column_dimensions["C"].width = 58
    guide.column_dimensions["D"].width = 22
    for row in guide.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    return workbook


def _xlsx_response(workbook, filename):
    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
    return _xlsx_response(_build_rules_workbook(rules), f"rules_export_{date.today().isoformat()}.xlsx")


@router.get("/import-template")
async def download_import_template():
    return _xlsx_response(_build_template_workbook(), "rules_import_template.xlsx")


@router.post("/import")
async def import_rules(file: UploadFile = File(...), db: Session = Depends(get_db)):
    from openpyxl import load_workbook

    filename = (file.filename or "").strip()
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx 格式的 Excel 文件")

    try:
        workbook = load_workbook(BytesIO(await file.read()), data_only=True)
    except Exception:
        raise HTTPException(status_code=400, detail="Excel 文件无法解析，请确认文件未损坏且为 .xlsx 格式")

    sheet = workbook.worksheets[0]
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        raise HTTPException(status_code=400, detail="Excel 文件内容为空")

    header = [str(value or "").strip() for value in rows[0]]
    column_index = {}
    for title, field, _width in RULE_EXPORT_COLUMNS:
        if title in header:
            column_index[field] = header.index(title)
    missing_columns = [title for title, field, _width in RULE_EXPORT_COLUMNS if field in REQUIRED_FIELDS and field not in column_index]
    if missing_columns:
        raise HTTPException(status_code=400, detail=f"表头缺少必需列: {'、'.join(missing_columns)}")

    def cell_value(row, field):
        index = column_index.get(field)
        if index is None or index >= len(row):
            return ""
        return str(row[index] or "").strip()

    candidates = []
    errors = []
    for offset, row in enumerate(rows[1:], start=2):
        if not any(str(value or "").strip() for value in row):
            continue
        rule_no = cell_value(row, "rule_no")
        if not rule_no:
            errors.append({"row": offset, "message": "缺少规则编号"})
            continue
        missing = [title for title, field, _width in RULE_EXPORT_COLUMNS if field in REQUIRED_FIELDS and not cell_value(row, field)]
        if missing:
            errors.append({"row": offset, "message": f"规则 {rule_no} 缺少必填列: {'、'.join(missing)}"})
            continue
        severity = _normalize_choice(cell_value(row, "severity"), SEVERITY_LABELS, "general")
        if severity is None:
            errors.append({"row": offset, "message": f"规则 {rule_no} 的严重程度需为 致命/严重/一般/建议"})
            continue
        language = _normalize_choice(cell_value(row, "language"), LANGUAGE_LABELS, "both")
        if language is None:
            errors.append({"row": offset, "message": f"规则 {rule_no} 的语言需为 中文/英文/中英通用"})
            continue
        candidates.append(RuleCreate(
            rule_no=rule_no,
            category=cell_value(row, "category"),
            description=cell_value(row, "description"),
            regex=cell_value(row, "regex"),
            example=cell_value(row, "example"),
            suggestion=cell_value(row, "suggestion"),
            audit_basis=cell_value(row, "audit_basis"),
            severity=severity,
            language=language,
        ))

    created = bulk_create_rules(db, candidates) if candidates else 0
    return {
        "created": created,
        "duplicates": len(candidates) - created,
        "total": len(candidates) + len(errors),
        "errors": errors,
    }

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
