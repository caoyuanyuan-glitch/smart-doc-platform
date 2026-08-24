# -*- coding: utf-8 -*-
"""竞品分析算法校准 CLI（评审意见采纳项：先跑真实文档，人工复核指标后再信评分）。

用途：
    对一批真实竞品/自家手册批量运行分析引擎，输出各维度**原始指标**（句长、术语密度、
    被动句比例等）与评分汇总，供人工复核阈值与权重是否合理。
    - 若多份公认"写得好"的手册某维度普遍低分 → 阈值过严，应放宽；
    - 若公认"晦涩"的文档普遍高分 → 扣分梯度不足，应加严。

用法（在 backend 目录下）：
    python scripts/calibrate_competitor.py <文件或目录>... [--out 报告.md]
    python scripts/calibrate_competitor.py D:/manuals --out calibration.md

支持格式与线上分析一致：.pdf / .docx / .md / .markdown / .txt / .html / .htm
目录输入时递归收集上述格式。不依赖数据库与鉴权，纯本地运行。
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
from datetime import datetime

# 允许直接 python scripts/calibrate_competitor.py 运行：把 backend 根目录加入 sys.path
_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

SUPPORTED_EXTS = {".pdf", ".docx", ".md", ".markdown", ".txt", ".html", ".htm"}


def collect_files(inputs):
    files = []
    for item in inputs:
        if os.path.isfile(item):
            files.append(item)
        elif os.path.isdir(item):
            for root, _dirs, names in os.walk(item):
                for name in sorted(names):
                    if os.path.splitext(name)[1].lower() in SUPPORTED_EXTS:
                        files.append(os.path.join(root, name))
        else:
            print(f"[warn] 路径不存在，跳过: {item}")
    # 去重保序
    return list(dict.fromkeys(files))


def parse_one(path):
    """复用平台解析器，返回 (full_text, pages_text, html_extraction)；失败返回 None。"""
    from app.utils import doc_parser
    from app.utils.competitor_html import extract_main_text

    ext = os.path.splitext(path)[1].lower()
    html_extraction = None
    if ext == ".pdf":
        result = doc_parser.parse_pdf(path)
    elif ext == ".docx":
        result = doc_parser.parse_docx(path)
    elif ext in (".html", ".htm"):
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            extraction = extract_main_text(f.read())
        html_extraction = extraction
        result = {"full_text": extraction.get("full_text", ""), "pages_text": []}
    else:
        result = doc_parser.parse_markdown(path)
    full_text = (result or {}).get("full_text", "")
    pages_text = (result or {}).get("pages_text") or ([full_text] if full_text else [])
    return full_text, pages_text, html_extraction


def analyze_one(path):
    """对单个文件运行完整分析，返回行 dict；异常不中断批处理。"""
    from app.utils.competitor_analysis import (
        analyze_tool_usage, analyze_readability, analyze_structure,
    )

    row = {"file": os.path.basename(path), "error": ""}
    try:
        full_text, pages_text, html_extraction = parse_one(path)
        if not full_text.strip():
            row["error"] = "未提取到文本（扫描件/空文档）"
            return row
        readability = analyze_readability(full_text, pages_text)
        structure = analyze_structure(path, full_text, pages_text, html_extraction)
        dims = readability.get("dimensions", {})
        stats = readability.get("stats", {})
        tool = analyze_tool_usage(path, full_text, pages_text)

        def _dim_score(key):
            return (dims.get(key) or {}).get("score")

        def _fmt(v, nd=1):
            return round(v, nd) if isinstance(v, (int, float)) else v

        row.update({
            "lang": readability.get("language"),
            "pages": structure.get("page_count"),
            "sents": stats.get("sentence_count"),
            "avg_sent": _fmt(stats.get("avg_sentence_len")),
            "avg_para": _fmt(stats.get("avg_paragraph_len")),
            "term_pct": stats.get("term_density_pct"),
            "passive_pct": stats.get("passive_ratio_pct"),
            "score_sent": _dim_score("sentence_length"),
            "score_term": _dim_score("term_density"),
            "score_passive": _dim_score("passive_ratio"),
            "score_para": _dim_score("paragraph_length"),
            "score_modifier": _dim_score("modifier_stack"),
            "overall": readability.get("overall_score"),
            "level": readability.get("level"),
            "headings": structure.get("heading_count"),
            "figures": structure.get("figure_count"),
            "tables": structure.get("table_count"),
            "warnings": structure.get("warning_count"),
            "tool": (tool.get("tools") or [{}])[0].get("name", "未知"),
        })
    except Exception as exc:  # 单文件失败不影响整批
        row["error"] = f"{type(exc).__name__}: {exc}"
    return row


_COLUMNS = [
    ("file", "文件"), ("lang", "语言"), ("pages", "页数"),
    ("avg_sent", "平均句长"), ("term_pct", "术语密度%"), ("passive_pct", "被动句%"),
    ("avg_para", "平均段长"),
    ("score_sent", "句长分"), ("score_term", "术语分"), ("score_passive", "被动分"),
    ("score_para", "段长分"), ("score_modifier", "修饰分"),
    ("overall", "综合分"), ("level", "评级"),
    ("headings", "章节"), ("figures", "图"), ("tables", "表"), ("warnings", "警告"),
    ("tool", "识别工具"), ("error", "错误"),
]

_NUMERIC_COLS = [k for k, _ in _COLUMNS if k not in ("file", "lang", "level", "tool", "error")]


def _median_fmt(values):
    vals = [v for v in values if isinstance(v, (int, float))]
    if not vals:
        return "—"
    return round(statistics.median(vals), 2)


def build_report(rows, started_at):
    lines = [
        "# 竞品分析算法校准报告",
        "",
        f"- **生成时间**：{started_at:%Y-%m-%d %H:%M}",
        f"- **样本数**：{len(rows)}（成功 {sum(1 for r in rows if not r['error'])} / 失败 {sum(1 for r in rows if r['error'])}）",
        "",
        "> 用途：人工复核各维度原始指标与评分是否合理。公认优质手册普遍低分 → 阈值过严；",
        "> 公认晦涩文档普遍高分 → 扣分梯度不足。阈值与权重定义见《竞品文档分析算法设计说明》。",
        "",
        "## 逐文档指标",
        "",
    ]
    header = "| " + " | ".join(label for _, label in _COLUMNS) + " |"
    lines.append(header)
    lines.append("|" + "---|" * len(_COLUMNS))
    for r in rows:
        cells = [str(r.get(k, "") if r.get(k) is not None else "—") for k, _ in _COLUMNS]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")

    ok_rows = [r for r in rows if not r["error"]]
    if ok_rows:
        lines.append("## 指标分布（中位数，用于复核阈值落点）")
        lines.append("")
        lines.append("| 指标 | 中位数 | 满分阈值参考 |")
        lines.append("|---|---|---|")
        refs = {
            "avg_sent": "中文 ≤40 字 / 英文 ≤20 词满分",
            "term_pct": "≤15% 满分",
            "passive_pct": "≤10% 满分",
            "avg_para": "中文 ≤150 字 / 英文 ≤80 词满分",
        }
        for key, label in _COLUMNS:
            if key in ("file", "level", "tool", "error", "lang"):
                continue
            lines.append(f"| {label} | {_median_fmt([r.get(key) for r in ok_rows])} | {refs.get(key, '')} |")
        lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="竞品分析算法校准：批量运行分析引擎并输出指标汇总，供人工复核阈值")
    parser.add_argument("inputs", nargs="+", help="文档文件或目录（支持 pdf/docx/md/txt/html）")
    parser.add_argument("--out", default="", help="汇总报告输出路径（Markdown，默认仅终端打印）")
    args = parser.parse_args()

    started_at = datetime.now()
    files = collect_files(args.inputs)
    if not files:
        print("[error] 未找到可分析的文件")
        return 1

    print(f"[calibrate] 共 {len(files)} 个文件，开始分析…")
    rows = []
    for path in files:
        print(f"  analyzing: {os.path.basename(path)}")
        rows.append(analyze_one(path))

    report = build_report(rows, started_at)
    print("\n" + report + "\n")
    if args.out:
        out_path = os.path.abspath(args.out)
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"[calibrate] 报告已写入: {out_path}")
    failed = sum(1 for r in rows if r["error"])
    print(f"[calibrate] 完成：成功 {len(rows) - failed}，失败 {failed}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
