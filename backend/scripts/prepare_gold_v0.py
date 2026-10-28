#!/usr/bin/env python3
"""把 gold_v0（人工审核意见分类整理成品）拆成按文档的评测套件。

输入（远端 main 已入库的成品）：
  backend/app/static/knowledge/gold_v0_content_review.json    311 条（内容语义）
  backend/app/static/knowledge/gold_v0_rule_detectable.json   539 条（规则可检出）

输出：
  backend/goldset/gold_v0/<序号>-<文档名>.json   每个文档一份 {annotations:[...]}
  backend/goldset/gold_v0_suite.json             评测配置（enforce=false 观测模式）

用法：
  python backend/scripts/prepare_gold_v0.py
  之后任意审核完成后：
  python backend/scripts/evaluate_review.py --config backend/goldset/gold_v0_suite.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE = ROOT / "app" / "static" / "knowledge"
GOLDSET_DIR = ROOT / "goldset"
GOLD_V0_DIR = GOLDSET_DIR / "gold_v0"
SUITE_PATH = GOLDSET_DIR / "gold_v0_suite.json"

# HumanAnnotation 只接收这 10 个字段，拆分时过滤多余列（如 note）
ANNOTATION_FIELDS = [
    "file", "page", "annotation_type", "author", "comment",
    "selected_text", "context", "category", "layer", "expected_rule",
]

SOURCES = [
    ("content", KNOWLEDGE / "gold_v0_content_review.json"),
    ("rule", KNOWLEDGE / "gold_v0_rule_detectable.json"),
]


def _norm_doc_key(name: str) -> str:
    """归一化文档名，去掉序号前缀和尾部 '·'。"""
    text = str(name or "").strip()
    text = re.sub(r"^\d+\.\s*", "", text)
    text = text.rstrip("· \t")
    return text


def _safe_stem(name: str) -> str:
    text = _norm_doc_key(name)
    text = re.sub(r"[\\/:*?\"<>|\s]+", "_", text)
    return text[:80] or "doc"


def main() -> int:
    if not KNOWLEDGE.exists():
        print(f"ERROR: 找不到知识库目录 {KNOWLEDGE}", file=sys.stderr)
        return 2

    merged: dict[str, list[dict]] = {}
    layers = {"content": 0, "rule": 0}
    for tag, path in SOURCES:
        if not path.exists():
            print(f"WARN: 缺少 {path.name}，跳过 {tag}", file=sys.stderr)
            continue
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(data, dict):
            data = data.get("annotations", [])
        for item in data:
            key = _norm_doc_key(item.get("file") or item.get("doc") or "")
            if not key:
                continue
            merged.setdefault(key, []).append(item)
        layers[tag] = len(data)
        print(f"加载 {path.name}: {len(data)} 条")

    total = sum(len(v) for v in merged.values())
    print(f"合并 {total} 条，跨 {len(merged)} 份文档")

    GOLD_V0_DIR.mkdir(parents=True, exist_ok=True)
    suite = {"documents": [], "thresholds": {"min_recall": 0.88, "min_precision": 0.88, "min_high_value_rate": 0.0}}

    for idx, (doc_name, items) in enumerate(sorted(merged.items(), key=lambda kv: (-len(kv[1]), kv[0])), start=1):
        stem = _safe_stem(doc_name)
        out = GOLD_V0_DIR / f"{idx:03d}-{stem}.json"
        clean_items = [{k: v for k, v in item.items() if k in ANNOTATION_FIELDS} for item in items]
        out.write_text(
            json.dumps({"document": doc_name, "annotations": clean_items}, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        suite["documents"].append(
            {
                "name": stem,
                "baseline": f"goldset/gold_v0/{out.name}",
                # 观测模式：gold 已按人工整理就位，但库中多数文档尚无对应审核记录；
                # 先只记录成绩，积累真实产出后由用户决定是否 enforce（卡 88% 门禁）。
                "enforce": False,
            }
        )

    SUITE_PATH.write_text(json.dumps(suite, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"拆分 {len(suite['documents'])} 份文档 goldset 到 {GOLD_V0_DIR}")
    print(f"评测配置写入 {SUITE_PATH}")
    print(f"阈值: min_recall=0.88, min_precision=0.88（观测模式 enforce=false，暂不卡口）")

    # 中英文构成速览
    cn = sum(1 for v in merged.values() for item in v if any("\u4e00" <= ch <= "\u9fff" for ch in str(item.get("comment", ""))))
    print(f"构成: 中文批注约 {cn} 条 / 英文批注约 {total - cn} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
