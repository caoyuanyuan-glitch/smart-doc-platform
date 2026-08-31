#!/usr/bin/env python3
"""G2 漏检诊断评测脚本。

默认读取《评测样本-漏检诊断30条.md》。样本文件不存在时打印跳过说明。

`--prompt-version v0|current` 只替换 `_DIAGNOSE_PROMPT`。`--compare` 在同一输入上对比两个版本。
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

V0_DIAGNOSE_PROMPT = """你是{product}平台的仪器文档资深编辑。请逐句审查用户文本，找出句式库之外的
语义问题：术语不规范、歧义、风险弱化、语体不符、逻辑缺失等。

规则（必须遵守）：
1. 只报告确定的问题。拿不准的不要报，宁缺毋滥。
2. 没有问题的句子，不要出现在结果里。
3. 修改必须忠于原意，不得增删事实与参数。
4. 术语必须与给定术语表一致；术语表没有的，保留原文。
5. category 只能从枚举取；severity 只能是 low/medium/high。
6. 只输出 JSON，不要任何解释文字。

category 枚举：spelling, grammar, word, term, ambiguity, redundancy, syntax, logic, missing, register, audience, risk, other

【术语表】
{terminology_md}

【风格指南】
{sentence_guide}

【待审查句子】
{json_sentences}

输出格式：
{{"diagnoses":[{{"sentence_index":0,"quote":"...","category":"term","severity":"high","problem":"...","revised":"...","rationale":"..."}}]}}
无问题返回 {{"diagnoses":[]}}。
"""


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


def apply_prompt_version(version: str) -> None:
    from app.utils import cat_diagnose

    original = getattr(apply_prompt_version, "_original", None)
    if original is None:
        apply_prompt_version._original = cat_diagnose._DIAGNOSE_PROMPT
        original = cat_diagnose._DIAGNOSE_PROMPT
    if version == "v0":
        cat_diagnose._DIAGNOSE_PROMPT = V0_DIAGNOSE_PROMPT
    else:
        cat_diagnose._DIAGNOSE_PROMPT = original


def read_document_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8")
    if suffix == ".docx":
        import docx

        document = docx.Document(str(path))
        return "\n".join(paragraph.text for paragraph in document.paragraphs)
    raise RuntimeError(f"不支持的文档类型: {suffix or path.name}")


def load_document_sentences(path: Path) -> list[str]:
    text = read_document_text(path)
    sentences = []
    for paragraph in re.split(r"\n+", text):
        chunk = paragraph.strip()
        if not chunk:
            continue
        parts = re.split(r"(?<=[。！？!?])", chunk)
        for part in parts:
            sentence = part.strip()
            sentence = re.sub(r"^\d{1,3}(?:\.\d{1,3}){1,3}\s*", "", sentence.strip())
            if sentence:
                sentences.append(sentence)
    return sentences


FORBIDDEN_SOURCE_RE = re.compile(
    r"版本记录|产品信息|第[一二三四五六七八九十\d]+[章节]|图示|表格|标准|\d{1,3}(?:\.\d{1,3}){1,3}"
)


def quality_metrics(diagnoses: list[dict]) -> dict:
    from app.utils.cat_diagnose import hint_import_requires_replacement

    total = 0
    hint = 0
    high = 0
    term_high = 0
    revised_nonempty = 0
    forbidden = 0
    logic_high = 0
    forbidden_hits = []
    for item in diagnoses or []:
        if not isinstance(item, dict):
            continue
        total += 1
        category = str(item.get("category") or "")
        severity = str(item.get("severity") or "")
        revised = str(item.get("revised") or "").strip()
        problem = str(item.get("problem") or "")
        if hint_import_requires_replacement(category, revised):
            hint += 1
        if severity == "high":
            high += 1
        if category == "term" and severity == "high":
            term_high += 1
        if revised:
            revised_nonempty += 1
        if category == "logic" and severity == "high":
            logic_high += 1
        if FORBIDDEN_SOURCE_RE.search(problem):
            forbidden += 1
            forbidden_hits.append(problem)
    return {
        "diagnose_count": total,
        "hint_count": hint,
        "hint_ratio": round((hint / total), 6) if total else 0.0,
        "high_count": high,
        "term_high_count": term_high,
        "revised_nonempty_count": revised_nonempty,
        "logic_high_count": logic_high,
        "forbidden_count": forbidden,
        "forbidden_hits": forbidden_hits,
    }


def aggregate_quality_metrics(runs: list[dict]) -> dict:
    return {
        "runs": len(runs),
        "diagnose_count": _mean([item.get("diagnose_count") for item in runs]),
        "hint_count": _mean([item.get("hint_count") for item in runs]),
        "hint_ratio": _mean([item.get("hint_ratio") for item in runs]),
        "high_count": _mean([item.get("high_count") for item in runs]),
        "term_high_count": _mean([item.get("term_high_count") for item in runs]),
        "revised_nonempty_count": _mean([item.get("revised_nonempty_count") for item in runs]),
        "logic_high_count": _mean([item.get("logic_high_count") for item in runs]),
        "forbidden_count": _mean([item.get("forbidden_count") for item in runs]),
        "per_run": runs,
    }


def _format_metric(value, kind: str = "count") -> str:
    if value is None:
        return "-"
    if kind == "ratio":
        return f"{float(value) * 100:.1f}%"
    return f"{float(value):.2f}"


def print_prompt_compare_table(v0: dict, current: dict) -> None:
    rows = [
        ("诊断总条数（均值）", "diagnose_count", "count"),
        ("hint 类占比（logic/missing/ambiguity 且 revised 空）", "hint_ratio", "ratio"),
        ("severity = high 条数", "high_count", "count"),
        ("term 类报 high 条数", "term_high_count", "count"),
        ("revised 非空条数", "revised_nonempty_count", "count"),
        ("logic high 条数", "logic_high_count", "count"),
        ("problem 出处正则命中", "forbidden_count", "count"),
    ]
    print("指标\tv0\tcurrent")
    for label, key, kind in rows:
        print(f"{label}\t{_format_metric(v0.get(key), kind)}\t{_format_metric(current.get(key), kind)}")
    print()
    print("判定参考：")
    print("v0 的 hint 占比显著低 + 总条数相当 → 主因确认是逃生口 → 下一步收紧或回滚第 7 条")
    print("v0 条数远多但质量也杂 → 逃生口其实在控噪，退化另有主因")
    print("两者差不多 → prompt 不是变量，查 temp 或批次切分")


async def run_quality_eval(sentences: list[str], product_type: str, runs: int) -> dict:
    per_run = []
    for _ in range(runs):
        diagnoses = await diagnose_sentences(sentences, product_type)
        per_run.append(quality_metrics(diagnoses))
    return aggregate_quality_metrics(per_run)


async def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate CAT open diagnose recall/false-positive or prompt A/B")
    parser.add_argument("--sample", default="", help="评测样本 markdown 路径")
    parser.add_argument("--document", default="", help="待诊断文档路径（txt/md/docx），用于 prompt A/B")
    parser.add_argument("--product-type", default="")
    parser.add_argument(
        "--runs",
        type=int,
        default=DEFAULT_EVAL_RUNS,
        help="每个文档的取样次数，默认 3 次后取均值",
    )
    parser.add_argument(
        "--prompt-version",
        choices=["v0", "current"],
        default="current",
        help="诊断 prompt 版本，默认 current；v0 为 ad13f5d 六条规则版",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="同一输入上对比 v0 与 current，各跑 --runs 次后输出对比表",
    )
    args = parser.parse_args()

    enabled = str(os.getenv("AI_DIAGNOSE_ENABLED", "false")).strip().lower() in {"1", "true", "yes", "on"}
    if not enabled:
        print("AI_DIAGNOSE_ENABLED 未打开，评测不会调用诊断。请先设置 AI_DIAGNOSE_ENABLED=true 再跑。")
        return 2

    run_count = max(1, int(args.runs or DEFAULT_EVAL_RUNS))
    document_path = Path(args.document).expanduser() if args.document else None
    sentences = []
    source_label = ""
    groups = {"A": [], "B": []}
    if document_path:
        if not document_path.exists():
            print(f"未找到文档：{document_path}")
            return 3
        try:
            sentences = load_document_sentences(document_path)
        except Exception as exc:
            print(f"读取文档失败：{exc}")
            return 3
        source_label = str(document_path)
        if not sentences:
            print(f"已读取 {document_path}，但没有解析到句子。")
            return 4

    if args.compare or document_path:
        if not sentences:
            sample_path = find_sample_file(args.sample)
            if sample_path is None:
                print("未找到评测样本或 --document。请通过 --document 指定 DNBelab-D4RS，或放置《评测样本-漏检诊断30条.md》。")
                return 3
            groups = parse_samples(sample_path.read_text(encoding="utf-8"))
            sentences = list(groups["A"]) + list(groups["B"])
            source_label = str(sample_path)
            if not sentences:
                print(f"已读取 {sample_path}，但没有解析到句子。")
                return 4
        versions = ["v0", "current"] if args.compare else [args.prompt_version]
        results = {}
        for version in versions:
            apply_prompt_version(version)
            results[version] = await run_quality_eval(sentences, args.product_type, run_count)
        payload = {
            "source": source_label,
            "sentence_count": len(sentences),
            "runs": run_count,
            "prompt_version": versions if args.compare else args.prompt_version,
            "results": results,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        if args.compare:
            print()
            print_prompt_compare_table(results["v0"], results["current"])
        return 0

    sample_path = find_sample_file(args.sample)
    if sample_path is None:
        print("未找到《评测样本-漏检诊断30条.md》。把样本放到仓库根目录或通过 --sample 指定后再跑。")
        return 3

    groups = parse_samples(sample_path.read_text(encoding="utf-8"))
    sentences = list(groups["A"]) + list(groups["B"])
    if not sentences:
        print(f"已读取 {sample_path}，但没有解析到 A/B 组句子。")
        return 4

    apply_prompt_version(args.prompt_version)
    run_summaries = []
    for _ in range(run_count):
        diagnoses = await diagnose_sentences(sentences, args.product_type)
        run_summaries.append(summarize(groups["A"], groups["B"], diagnoses))
    aggregated = aggregate_run_summaries(run_summaries)
    print(json.dumps({
        "sample": str(sample_path),
        "prompt_version": args.prompt_version,
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
