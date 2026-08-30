#!/usr/bin/env python3
"""G2 漏检诊断评测脚本。

默认读取《评测样本-漏检诊断30条.md》。样本文件不存在时打印跳过说明。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))


SAMPLE_CANDIDATES = [
    REPO_ROOT / "评测样本-漏检诊断30条.md",
    REPO_ROOT / ".monkeycode" / "docs" / "评测样本-漏检诊断30条.md",
    Path("/workspace/.monkeycode-tmp-files") / "评测样本-漏检诊断30条.md",
]


def find_sample_file(explicit: str = "") -> Path | None:
    if explicit:
        path = Path(explicit).expanduser()
        return path if path.exists() else None
    for path in SAMPLE_CANDIDATES:
        if path.exists():
            return path
    return None


def parse_samples(markdown_text: str) -> dict:
    """尽量从 markdown 中解析 A/B 组句子。支持简单列表项。"""
    groups = {"A": [], "B": []}
    current = None
    for raw_line in markdown_text.splitlines():
        line = raw_line.strip()
        if re.search(r"A\s*组|漏检", line):
            current = "A"
            continue
        if re.search(r"B\s*组|误报|正常句", line):
            current = "B"
            continue
        if current and re.match(r"^[-*\d.、)]+", line):
            text = re.sub(r"^[-*\d.、)\s]+", "", line).strip()
            if text:
                groups[current].append(text)
    return groups


async def diagnose_sentences(sentences: list[str], product_type: str = "") -> list[dict]:
    from app.utils.cat_diagnose import open_diagnose_sentences

    items = [{"sentence_index": index, "text": text} for index, text in enumerate(sentences)]
    return await open_diagnose_sentences(items, {}, "", product_type)


def summarize(group_a: list[str], group_b: list[str], diagnoses: list[dict]) -> dict:
    hit_indexes = {item.get("sentence_index") for item in diagnoses if isinstance(item, dict)}
    a_count = len(group_a)
    b_count = len(group_b)
    a_hits = sum(1 for index in range(a_count) if index in hit_indexes)
    b_hits = sum(1 for index in range(a_count, a_count + b_count) if index in hit_indexes)
    recall = (a_hits / a_count) if a_count else None
    false_positive = (b_hits / b_count) if b_count else None
    return {
        "group_a": a_count,
        "group_b": b_count,
        "a_hits": a_hits,
        "b_hits": b_hits,
        "recall": recall,
        "false_positive_rate": false_positive,
        "recall_pass": None if recall is None else recall >= 0.70,
        "false_positive_pass": None if false_positive is None else false_positive <= 0.20,
        "diagnoses": diagnoses,
    }


DEFAULT_EVAL_RUNS = 3


def _mean(values: list) -> float | None:
    nums = [float(v) for v in values if v is not None]
    if not nums:
        return None
    return round(sum(nums) / len(nums), 6)


def aggregate_run_summaries(summaries: list[dict]) -> dict:
    """多次取样后取均值。召回≥70%、误报≤20% 以均值判定。"""
    mean_recall = _mean([item.get("recall") for item in summaries])
    mean_fp = _mean([item.get("false_positive_rate") for item in summaries])
    return {
        "runs": len(summaries),
        "mean_recall": mean_recall,
        "mean_false_positive_rate": mean_fp,
        "recall_pass": None if mean_recall is None else mean_recall >= 0.70,
        "false_positive_pass": None if mean_fp is None else mean_fp <= 0.20,
        "per_run": [
            {
                "a_hits": item.get("a_hits"),
                "b_hits": item.get("b_hits"),
                "recall": item.get("recall"),
                "false_positive_rate": item.get("false_positive_rate"),
                "diagnose_count": len(item.get("diagnoses") or []),
            }
            for item in summaries
        ],
    }


async def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate CAT open diagnose recall/false-positive")
    parser.add_argument("--sample", default="", help="评测样本 markdown 路径")
    parser.add_argument("--product-type", default="")
    parser.add_argument(
        "--runs",
        type=int,
        default=DEFAULT_EVAL_RUNS,
        help="每个文档的取样次数，默认 3 次后取均值",
    )
    args = parser.parse_args()

    enabled = str(os.getenv("AI_DIAGNOSE_ENABLED", "false")).strip().lower() in {"1", "true", "yes", "on"}
    if not enabled:
        print("AI_DIAGNOSE_ENABLED 未打开，评测不会调用诊断。请先设置 AI_DIAGNOSE_ENABLED=true 再跑。")
        return 2

    sample_path = find_sample_file(args.sample)
    if sample_path is None:
        print("未找到《评测样本-漏检诊断30条.md》。把样本放到仓库根目录或通过 --sample 指定后再跑。")
        return 3

    groups = parse_samples(sample_path.read_text(encoding="utf-8"))
    sentences = list(groups["A"]) + list(groups["B"])
    if not sentences:
        print(f"已读取 {sample_path}，但没有解析到 A/B 组句子。")
        return 4

    run_count = max(1, int(args.runs or DEFAULT_EVAL_RUNS))
    run_summaries = []
    for _ in range(run_count):
        diagnoses = await diagnose_sentences(sentences, args.product_type)
        run_summaries.append(summarize(groups["A"], groups["B"], diagnoses))
    aggregated = aggregate_run_summaries(run_summaries)
    print(json.dumps({
        "sample": str(sample_path),
        "group_a": run_summaries[0]["group_a"],
        "group_b": run_summaries[0]["group_b"],
        "runs": aggregated["runs"],
        "mean_recall": aggregated["mean_recall"],
        "mean_false_positive_rate": aggregated["mean_false_positive_rate"],
        "recall_pass": aggregated["recall_pass"],
        "false_positive_pass": aggregated["false_positive_pass"],
        "per_run": aggregated["per_run"],
    }, ensure_ascii=False, indent=2))
    if aggregated["recall_pass"] and aggregated["false_positive_pass"]:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
