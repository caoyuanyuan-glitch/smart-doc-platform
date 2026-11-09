#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import 2026-11-06 rule candidates into the rules table."""
from __future__ import annotations

import argparse
import re
from pathlib import Path
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine
from app.models.rule import Rule
from app.schemas.rule import RuleCreate
from app.crud.rule import bulk_create_rules, get_rules

CANDIDATE_XLSX = Path(__file__).resolve().parents[1] / "app" / "review_engine" / "assets" / "rule_candidates_20261106.xlsx"
BUILTIN_HR = {f"HR{i:03d}" for i in range(1, 15)}
SEVERITY_MAP = {"致命": "fatal", "严重": "serious", "一般": "general", "建议": "suggestion"}
LANGUAGE_MAP = {"中文": "cn", "英文": "en", "中英通用": "both", "cn": "cn", "en": "en", "both": "both"}

SINGLE_WORD_BLOCKLIST = {
    "report", "place", "your", "pool", "name", "note", "figure", "table",
    "system", "sample", "result", "data", "value", "user", "device",
}
COMMENT_MARKERS = ("我看", "通查", "均可", "统一为", "反了", "缺-", "未更新", "页面信息说明")
TECH_ATTR_WHITELIST = {"outputclass", "classname", "conkeyref", "conref"}


def _bare_word(regex: str) -> str | None:
    """Strip literal \\b; return the word if the rest is a single English token."""
    s = (regex or "").replace("\\b", "").strip()
    m = re.fullmatch(r"([A-Za-z][A-Za-z0-9_-]*)", s)
    return m.group(1).lower() if m else None


def _bare_token_allowed(regex: str) -> bool:
    w = _bare_word(regex)
    if not w:
        return True
    if w in TECH_ATTR_WHITELIST:
        return True
    return w not in SINGLE_WORD_BLOCKLIST


def _suggestion_is_writable(rule_no: str, suggestion: str) -> bool:
    """LEX suggestions must be substitutable text, not reviewer commentary."""
    if "-LEX-" not in (rule_no or ""):
        return True
    sug = suggestion or ""
    if not sug.strip():
        return False
    return not any(k in sug for k in COMMENT_MARKERS)


def _backup_rules(db: Session) -> None:
    name = f"rules_bak_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        db.execute(text(f'CREATE TABLE "{name}" (LIKE rules INCLUDING ALL)'))
        db.execute(text(f'INSERT INTO "{name}" SELECT * FROM rules'))
    else:
        db.execute(text(f"CREATE TABLE {name} AS SELECT * FROM rules"))
    db.commit()


def load_candidates(path: Path) -> tuple[list[RuleCreate], list[str]]:
    from openpyxl import load_workbook

    wb = load_workbook(path, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not rows:
        return [], []
    header = [str(v or "").strip() for v in rows[0]]
    idx = {name: header.index(name) for name in header}

    def cell(row, name):
        i = idx.get(name)
        if i is None or i >= len(row):
            return ""
        return str(row[i] or "").strip()

    out = []
    skipped: list[str] = []
    for row in rows[1:]:
        rule_no = cell(row, "规则编号")
        regex = cell(row, "正则")
        if not rule_no or not regex:
            continue
        if str(rule_no).startswith("HR-FP-SUPPRESS"):
            continue
        if rule_no in BUILTIN_HR or re.fullmatch(r"HR0*(?:[1-9]|1[0-4])", rule_no):
            continue
        if regex in {"(?!)", "(?!x?x?)"}:
            continue
        try:
            re.compile(regex)
        except re.error:
            continue
        if not _bare_token_allowed(regex):
            skipped.append(f"{rule_no}: 纯英文单词命中停用词 {regex}")
            continue
        if not _suggestion_is_writable(rule_no, cell(row, "建议")):
            skipped.append(f"{rule_no}: 建议栏是审核评论而非替换写法")
            continue
        out.append(RuleCreate(
            rule_no=rule_no,
            category=cell(row, "分类") or "其他",
            description=cell(row, "规则描述"),
            regex=regex,
            example=cell(row, "示例"),
            suggestion=cell(row, "建议"),
            audit_basis=cell(row, "审核依据"),
            severity=SEVERITY_MAP.get(cell(row, "严重程度"), "general"),
            language=LANGUAGE_MAP.get(cell(row, "语言"), cell(row, "语言") or "both"),
        ))
    return out, skipped


def import_candidates(db: Session, path: Path = CANDIDATE_XLSX, backup: bool = True) -> dict:
    if backup:
        _backup_rules(db)
    before = get_rules(db, skip=0, limit=10000)
    idle_before = sum(1 for r in before if (r.regex or "") == "(?!)")
    live_before = len(before) - idle_before
    candidates, skipped = load_candidates(path)
    created = bulk_create_rules(db, candidates)
    after = get_rules(db, skip=0, limit=10000)
    idle_after = sum(1 for r in after if (r.regex or "") == "(?!)")
    live_after = len(after) - idle_after
    return {
        "before_total": len(before),
        "after_total": len(after),
        "created": created,
        "idle_before": idle_before,
        "idle_after": idle_after,
        "live_before": live_before,
        "live_after": live_after,
        "candidate_count": len(candidates),
        "skipped": skipped,
        "skipped_count": len(skipped),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--xlsx", default=str(CANDIDATE_XLSX))
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args()
    db = SessionLocal()
    try:
        stats = import_candidates(db, Path(args.xlsx), backup=not args.no_backup)
        print(stats)
    finally:
        db.close()


if __name__ == "__main__":
    main()
