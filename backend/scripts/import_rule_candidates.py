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


def _backup_rules(db: Session) -> None:
    name = f"rules_bak_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        db.execute(text(f'CREATE TABLE "{name}" (LIKE rules INCLUDING ALL)'))
        db.execute(text(f'INSERT INTO "{name}" SELECT * FROM rules'))
    else:
        db.execute(text(f"CREATE TABLE {name} AS SELECT * FROM rules"))
    db.commit()


def load_candidates(path: Path) -> list[RuleCreate]:
    from openpyxl import load_workbook

    wb = load_workbook(path, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not rows:
        return []
    header = [str(v or "").strip() for v in rows[0]]
    idx = {name: header.index(name) for name in header}

    def cell(row, name):
        i = idx.get(name)
        if i is None or i >= len(row):
            return ""
        return str(row[i] or "").strip()

    out = []
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
    return out


def import_candidates(db: Session, path: Path = CANDIDATE_XLSX, backup: bool = True) -> dict:
    if backup:
        _backup_rules(db)
    before = get_rules(db, skip=0, limit=10000)
    idle_before = sum(1 for r in before if (r.regex or "") == "(?!)")
    live_before = len(before) - idle_before
    candidates = load_candidates(path)
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
