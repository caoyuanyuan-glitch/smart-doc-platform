#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""指令 G 验收：术语库动态解析完整性 / 正确率 / 不落库。"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from openpyxl import load_workbook
from sqlalchemy import text

from app.database import SessionLocal
from app.services.terminology import load_terminology, reset_terminology_cache

DEFAULT_XLSX = (
    Path(__file__).resolve().parents[1]
    / "seed"
    / "knowledge"
    / "资源库"
    / "术语库"
    / "术语&固定表达-V3.0.xlsx"
)


def _truth_pairs(path: Path) -> list[tuple[str, str]]:
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        rows = list(wb.active.iter_rows(values_only=True))
    finally:
        wb.close()
    if not rows:
        return []
    headers = [str(v or "").strip().lower().replace(" ", "") for v in rows[0]]
    zi = headers.index("zh-cn") if "zh-cn" in headers else 0
    ei = headers.index("en-us") if "en-us" in headers else 6
    out = []
    for row in rows[1:]:
        zh = str(row[zi]).strip() if row and zi < len(row) and row[zi] is not None else ""
        en = str(row[ei]).strip() if row and ei < len(row) and row[ei] is not None else ""
        if zh and en:
            out.append((zh, en))
    return out


def verify(path: Path) -> dict:
    reset_terminology_cache()
    t0 = time.perf_counter()
    pack = load_terminology(str(path))
    first_ms = (time.perf_counter() - t0) * 1000
    t1 = time.perf_counter()
    pack2 = load_terminology(str(path))
    second_ms = (time.perf_counter() - t1) * 1000

    db = SessionLocal()
    try:
        terms_count = db.execute(text("SELECT count(*) FROM terms")).scalar() or 0
    finally:
        db.close()

    if pack is None:
        return {
            "xlsx": str(path),
            "pairs": 0,
            "truth": 0,
            "correct": 0,
            "accuracy": 0.0,
            "terms_table": terms_count,
            "cache_hit_ms": round(second_ms, 3),
            "first_ms": round(first_ms, 3),
            "arm": None,
            "ok": False,
        }

    truth = _truth_pairs(path)
    pair_set = {(zh, en) for zh, en, _src, _note in pack.get("pairs") or []}
    correct = sum(1 for item in truth if item in pair_set)
    accuracy = (correct / len(truth)) if truth else 0.0
    arm = (pack.get("zh_index") or {}).get("%1:机械臂归零")
    ok = (
        len(pack.get("pairs") or []) == 5506
        and len(truth) == 5506
        and correct == 5506
        and arm == ["%1: robotic arm back to zero"]
        and pack2 is pack
        and second_ms < 5
        and terms_count == 0
    )
    return {
        "xlsx": str(path),
        "pairs": len(pack.get("pairs") or []),
        "truth": len(truth),
        "correct": correct,
        "accuracy": round(accuracy * 100, 2),
        "terms_table": terms_count,
        "cache_hit_ms": round(second_ms, 3),
        "first_ms": round(first_ms, 3),
        "arm": arm,
        "it": (pack.get("zh_index") or {}).get("IT产品与服务"),
        "ok": ok,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--xlsx", default=str(DEFAULT_XLSX))
    args = parser.parse_args()
    stats = verify(Path(args.xlsx))
    print(
        f"pairs={stats['pairs']} / 正确率={stats['accuracy']:.2f}% / terms 表={stats['terms_table']}"
    )
    print(stats)
    raise SystemExit(0 if stats["ok"] else 1)


if __name__ == "__main__":
    main()
