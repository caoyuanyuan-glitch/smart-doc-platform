#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build rule-learning assets from the 2026-11-06 pack + legacy branch encodings."""
from __future__ import annotations

import csv
import json
import os
import re
import shutil
from collections import defaultdict
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[1]
PACK = _BACKEND_DIR / "tests" / "fixtures" / "rule_pack_20261106"
ASSETS = _BACKEND_DIR / "app" / "review_engine" / "assets"
FIXTURES = _BACKEND_DIR / "tests" / "fixtures"

# 24 个 legacy 分支的数据驱动编码，须与 annotation_baseline._matches_expected_rule_legacy 逐例等价。
LEGACY_MATCH = {
    "DET-REVISION-001": {
        "rule_prefixes": ["DOC-REV", "CYY-CN-REVISION-"],
        "category_keywords": ["版本记录", "修订一致性"],
    },
    "DET-CN-001": {
        "exact_rules": ["ENG-CN-001"],
        "category_keywords": ["中文混入"],
    },
    "STRUCT-SCOPE-001": {
        "exact_rules": ["DOC-SCOPE-001", "DOC-MODEL-002", "CYY-CN-SCOPE-002", "CYY-CN-SCOPE-003"],
        "blob_all": ["ne384", "硬件配置"],
    },
    "STRUCT-FIGTAB-001": {
        "rule_prefixes": ["DOC-FIGTAB"],
        "category_keywords": ["表图编号"],
    },
    "STRUCT-LAYOUT-001": {
        "overrides": [
            {
                "when": {"text_all": ["列宽"], "blob_all": ["储存环境"]},
                "then": {"always": True},
            }
        ],
        "rule_prefixes": ["CYY-CN-LAYOUT-"],
        "category_keywords": ["表格/版式"],
    },
    "STRUCT-IMAGE-001": {
        "overrides": [
            {
                "when": {"text_all": ["install", "finish", "打开本系统"]},
                "then": {"exact_rules": ["CYY-CN-LOGIC-007"], "category_keywords": ["内容逻辑"]},
            }
        ],
        "rule_prefixes": ["CYY-CN-IMAGE-"],
        "exact_rules": ["PDF-VISUAL-001"],
        "category_keywords": ["图片", "对象缺失"],
    },
    "STRUCT-STEP-001": {
        "exact_rules": ["CYY-CN-STRUCT-001", "CYY-CN-STEP-004"],
        "category_keywords": ["步骤结构"],
    },
    "STRUCT-COMPONENT-001": {
        "rule_prefixes": ["CYY-CN-ROHS-"],
        "category_keywords": ["结构完整"],
    },
    "STRUCT-INDEX-001": {
        "rule_prefixes": ["CYY-CN-INDEX-"],
        "category_keywords": ["索引"],
    },
    "AI-PROC-001": {
        "exact_rules": ["DOC-PROC-001"],
        "category_keywords": ["操作步骤语气"],
    },
    "DET-TITLE-CASE-001": {
        "exact_rules": ["DOC-TITLE-001"],
        "category_keywords": ["标题大小写"],
    },
    "AI-CHECK-001": {
        "overrides": [
            {
                "when": {"text_all": ["pos"]},
                "then": {"exact_rules": ["DOC-POS-001"], "category_keywords": ["台面位置"]},
            },
            {
                "when": {"text_all": ["install", "finish", "打开本系统"]},
                "then": {"exact_rules": ["CYY-CN-LOGIC-007"], "category_keywords": ["内容逻辑"]},
            },
        ],
        "selected_in_blob_min_len": 2,
        "rule_prefixes": ["CYY-CN-CHECK-", "CYY-CN-ADDR-"],
        "category_keywords": ["人工确认"],
    },
    "AI-ADDR-001": {
        "rule_prefixes": ["CYY-CN-ADDR-"],
        "category_keywords": ["地址"],
    },
    "STRUCT-PAGE-NUM-001": {
        "rule_prefixes": ["CYY-CN-PAGE-"],
        "category_keywords": ["页码"],
    },
    "DET-SPACE-001": {
        "selected_in_blob_min_len": 2,
        "exact_rules": [
            "R010", "HR004", "UNIT-002", "UNIT-003", "UNIT-004", "HR006",
            "DOC-FMT-003", "DOC-SPACE-001", "DOC-SPACE-002", "DOC-SPACE-003",
            "DOC-SPACE-004", "DOC-SPACE-005", "DOC-SPACE-006", "DOC-UNIT-001",
        ],
        "category_keywords": ["格式规范", "空格"],
    },
    "DET-PUNCT-001": {
        "rule_prefixes": ["DOC-PUNCT", "DOC-QUOTE", "CYY-CN-PUNCT"],
        "category_keywords": ["标点"],
    },
    "DET-CATNO-001": {
        "rule_prefixes": ["DOC-CATNO", "CYY-CN-PRODUCT-002"],
        "category_keywords": ["货号"],
    },
    "DET-MATERIAL-001": {
        "exact_rules": ["CYY-CN-REF-003"],
        "category_keywords": ["物料编码", "交叉引用"],
    },
    "DET-TYPO-001": {
        "rule_prefixes": ["CYY-CN-LAYOUT-"],
        "category_keywords": ["字体/版式", "表格/版式"],
    },
    "DOC-DATA-001": {
        "exact_rules": ["DOC-DATA-001"],
        "category_keywords": ["信息完整性"],
    },
    "DET-TERM-SPELL-001": {
        "selected_in_blob_min_len": 2,
        "rule_prefixes": ["CYY-CN-SPELL-"],
        "exact_rules": [
            "CYY-CN-TERM-006", "CYY-CN-CONSIST-032", "SPELL", "SPELL-PHRASE",
            "SPELL-PROP", "SPELL-TRANS", "SPELL-INS", "SPELL-SPLIT",
        ],
        "category_keywords": ["术语拼写", "拼写错误", "术语一致性"],
    },
    "STRUCT-DUP-001": {
        "rule_prefixes": ["DOC-DUP"],
        "exact_rules": ["CYY-CN-DUP-002"],
        "category_keywords": ["重复"],
    },
    "STRUCT-TERM-001": {
        "selected_in_blob_min_len": 4,
        "rule_prefixes": ["DOC-TERM", "CYY-CN-CONSIST-"],
        "exact_rules": [
            "CYY-CN-NAV-001", "STRUCT-TERM-001",
            "DET-TERM-BASELINE-001", "DET-TERM-CASE-001", "DET-TERM-CANON-001",
            "TERM-INCONSIST", "TERM-PAIR",
        ],
        "category_keywords": ["术语一致性"],
    },
    "AI-STYLE-001": {
        "exact_rules": [
            "DOC-MICRO-001", "DOC-PROC-001", "GRAMMAR-003", "GRAMMAR-004", "GRAMMAR-005",
            "DOC-GRAM-004", "DOC-GRAM-005", "DOC-GRAM-006", "DOC-GRAM-007", "DOC-GRAM-008",
            "DOC-GRAMMAR-001", "DOC-GRAMMAR-002",
            "CYY-CN-STYLE-003", "CYY-CN-GRAMMAR-009", "CYY-CN-GRAMMAR-010", "CYY-CN-GRAMMAR-011",
        ],
        "category_keywords": ["表达与句式"],
    },
}

GENERIC_STOP = {"数字", "文字", "内容", "格式", "说明", "问题", "错误", "规范"}


def _parse_platform_rules(raw: str) -> list[str]:
    text = str(raw or "").strip()
    if not text:
        return []
    text = re.sub(r"\(.*?\)", "", text)
    parts = re.split(r"\s*/\s*|[、，,;；]+", text)
    out = []
    for part in parts:
        token = part.strip()
        if not token or token in {"live", "dead"}:
            continue
        m = re.match(r"([A-Z0-9-]+?)(\d+)~(\d+)$", token)
        if m:
            prefix, start, end = m.group(1), int(m.group(2)), int(m.group(3))
            width = len(m.group(2))
            for n in range(start, end + 1):
                out.append(f"{prefix}{n:0{width}d}")
            continue
        if re.search(r"[A-Z]", token):
            out.append(token)
    return out


def _derive_keywords(label_name: str, *, tight: bool) -> list[str]:
    name = str(label_name or "").strip()
    if not name:
        return []
    chunks = re.split(r"[/／、，,;；|]+", name)
    keys = []
    min_len = 3 if tight else 2
    for chunk in chunks:
        token = chunk.strip()
        if len(token) < min_len:
            continue
        if tight and token in GENERIC_STOP:
            continue
        if token not in keys:
            keys.append(token)
    return keys


def _has_strong_channel(entry: dict) -> bool:
    return bool(
        entry.get("exact_rules")
        or entry.get("rule_prefixes")
        or entry.get("text_all")
        or entry.get("blob_all")
        or entry.get("selected_in_blob_min_len")
        or entry.get("overrides")
    )


def load_02() -> list[dict]:
    path = PACK / "02_规则学习清单.csv"
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def build_families() -> dict:
    rows = load_02()
    regression_rules = set()
    with (PACK / "07_回归测试集.jsonl").open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            regression_rules.add(json.loads(line)["expected_rule"])

    entries = {}
    listed = set()
    for row in rows:
        rule_id = (row.get("期望规则") or "").strip()
        if not rule_id:
            continue
        listed.add(rule_id)
        in_legacy = rule_id in LEGACY_MATCH
        match = dict(LEGACY_MATCH.get(rule_id) or {})
        platform_rules = _parse_platform_rules(row.get("平台已有规则") or "")
        label_name = (row.get("标签名") or "").strip()
        if in_legacy:
            category_keywords = list(match.get("category_keywords") or [])
            disabled = False
        else:
            category_keywords = _derive_keywords(label_name, tight=True)
            match["category_keywords"] = category_keywords
            # 新增规则在 platform_rules 接通前不参与线上匹配。
            disabled = True

        entries[rule_id] = {
            "label_code": (row.get("标签码") or "").strip(),
            "label_name": label_name,
            "platform_dim": (row.get("平台维度") or "").strip(),
            "layer": (row.get("检出层") or "").strip(),
            "samples": int(str(row.get("样本数") or "0").replace(",", "") or 0),
            "in_legacy_code": in_legacy,
            "in_regression_set": rule_id in regression_rules,
            "rule_prefixes": list(match.get("rule_prefixes") or []),
            "exact_rules": list(match.get("exact_rules") or []),
            "category_keywords": category_keywords,
            "text_all": list(match.get("text_all") or []),
            "blob_all": list(match.get("blob_all") or []),
            "selected_in_blob_min_len": int(match.get("selected_in_blob_min_len") or 0),
            "overrides": list(match.get("overrides") or []),
            "platform_rules": platform_rules,
            "legacy_only": False,
            "disabled": disabled,
        }

    for rule_id, match in LEGACY_MATCH.items():
        if rule_id in listed:
            continue
        entries[rule_id] = {
            "label_code": "",
            "label_name": rule_id,
            "platform_dim": "",
            "layer": "",
            "samples": 0,
            "in_legacy_code": True,
            "in_regression_set": rule_id in regression_rules,
            "rule_prefixes": list(match.get("rule_prefixes") or []),
            "exact_rules": list(match.get("exact_rules") or []),
            "category_keywords": list(match.get("category_keywords") or []),
            "text_all": list(match.get("text_all") or []),
            "blob_all": list(match.get("blob_all") or []),
            "selected_in_blob_min_len": int(match.get("selected_in_blob_min_len") or 0),
            "overrides": list(match.get("overrides") or []),
            "platform_rules": [],
            "legacy_only": True,
            "disabled": False,
        }

    entries["TERM-CHECK-001"] = {
        "label_code": "E1",
        "label_name": "术语库动态校验",
        "platform_dim": "术语一致性",
        "layer": "deterministic",
        "samples": 0,
        "in_legacy_code": False,
        "in_regression_set": False,
        "rule_prefixes": [],
        "exact_rules": ["TERM-INCONSIST", "TERM-PAIR"],
        "category_keywords": [],
        "text_all": [],
        "blob_all": [],
        "selected_in_blob_min_len": 0,
        "overrides": [],
        "platform_rules": [],
        "legacy_only": False,
        "disabled": False,
        "notes": (
            "TERM-CHECK-001 与 STRUCT-TERM-001 的规则号重叠是刻意设计："
            "前者按检出层组织（术语库动态校验），后者按问题类型组织（篇内不一致）。"
            "允许一条 issue 被两族认领，统计时按族去重。"
            "TERM-FORBIDDEN 通道未启用。"
        ),
    }

    stats = {
        "total": len(entries),
        "in_legacy_code": sum(1 for e in entries.values() if e["in_legacy_code"]),
        "legacy_only": sum(1 for e in entries.values() if e["legacy_only"]),
        # TERM-CHECK-001 is a post-pack overlay, not one of the 44 new pack rules.
        "new_rules": sum(
            1 for rid, e in entries.items()
            if not e["in_legacy_code"] and rid != "TERM-CHECK-001"
        ),
        "disabled": sum(1 for e in entries.values() if e["disabled"]),
        "in_regression_set": sum(1 for e in entries.values() if e["in_regression_set"]),
    }
    return {
        "version": "2026-11-06",
        "source": "人工审核意见整理_规则学习包_20261106",
        "match_order": [
            "overrides", "selected_in_blob", "exact_rules", "rule_prefixes",
            "category_keywords", "blob_all", "text_all",
        ],
        "notes": (
            "44 条新增规则默认 disabled；WORKBUDDY_RULE_PLATFORM_CH=on 时 disabled 族只走 live platform_rules。"
            "DET-TRADEMARK-001/EXT-R006/EXT-R024 挂起。"
            "TERM-CHECK-001 与 STRUCT-TERM-001 共享 TERM-INCONSIST/TERM-PAIR；前者是术语库动态校验视角，后者是篇内不一致视角。"
            "回归样本全部挂在 STRUCT-TERM-001（40 条），TERM-CHECK-001 样本为 0。"
            "TERM-FORBIDDEN 通道未启用。"
        ),
        "stats": stats,
        "entries": entries,
    }


def build_fewshot() -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    with (PACK / "03_规则学习语料.jsonl").open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            grouped[row["expected_rule"]].append(row)
    out = []
    for rule_id, rows in grouped.items():
        picked = []
        for row in rows:
            comment = str(row.get("comment") or "")
            suggestion = str(row.get("suggestion") or "")
            blob = (comment + suggestion)[:300]
            picked.append({
                "expected_rule": rule_id,
                "label_code": row.get("label_code") or "",
                "label_name": row.get("label_name") or "",
                "doc": row.get("doc") or "",
                "page": row.get("page") or "",
                "comment": comment[:300],
                "anchor": row.get("anchor") or "",
                "suggestion": suggestion[:300],
                "comment_suggestion": blob,
            })
            if len(picked) >= 3:
                break
        out.extend(picked)
    return out


def build_candidates_xlsx() -> int:
    from openpyxl import Workbook

    src = PACK / "06_规则候选_可启用.csv"
    with src.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    wb = Workbook()
    ws = wb.active
    ws.title = "规则库"
    headers = ["规则编号", "分类", "规则描述", "正则", "示例", "建议", "审核依据", "严重程度", "语言"]
    ws.append(headers)
    kept = 0
    for row in rows:
        rule_no = (row.get("规则编号") or "").strip()
        if rule_no.startswith("HR-FP-SUPPRESS"):
            continue
        regex = row.get("正则") or ""
        if regex.strip() in {"(?!)", "(?!x?x?)"}:
            continue
        try:
            re.compile(regex)
        except re.error:
            continue
        ws.append([
            rule_no,
            row.get("分类") or "",
            row.get("规则描述") or "",
            regex,
            row.get("示例") or "",
            row.get("建议") or "",
            row.get("审核依据") or "",
            row.get("严重程度") or "",
            row.get("语言") or "",
        ])
        kept += 1
    dest = ASSETS / "rule_candidates_20261106.xlsx"
    wb.save(dest)
    return kept


def main() -> None:
    asset_path = ASSETS / "expected_rule_families.json"
    if asset_path.exists() and not os.getenv("FORCE_REBUILD_ASSETS"):
        raise SystemExit(
            f"{asset_path} 已存在。要重建请先删除它，或设置 FORCE_REBUILD_ASSETS=1。"
        )
    ASSETS.mkdir(parents=True, exist_ok=True)
    FIXTURES.mkdir(parents=True, exist_ok=True)
    families = build_families()
    asset_path.write_text(
        json.dumps(families, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    fewshot = build_fewshot()
    with (ASSETS / "rule_corpus_fewshot.jsonl").open("w", encoding="utf-8") as fh:
        for row in fewshot:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    kept = build_candidates_xlsx()
    shutil.copyfile(PACK / "07_回归测试集.jsonl", FIXTURES / "regression_701_rules.jsonl")
    print("families", families["stats"])
    print("fewshot", len(fewshot))
    print("candidates", kept)
    print("regression lines", sum(1 for _ in (FIXTURES / "regression_701_rules.jsonl").open(encoding="utf-8")))


if __name__ == "__main__":
    main()
