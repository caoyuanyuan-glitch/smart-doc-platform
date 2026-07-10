#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.review_engine.annotation_baseline import annotations_to_json, parse_human_annotation_markdown, summarize_annotations


def summary_to_markdown(summary):
    lines = ["# 人工批注评测集摘要", "", f"- 总条目: {summary['total']}", ""]
    for title, key in [("分层统计", "by_layer"), ("类别统计", "by_category"), ("规则统计", "by_rule"), ("文件统计", "by_file")]:
        lines.append(f"## {title}")
        lines.append("")
        for name, count in summary[key].items():
            lines.append(f"- {name}: {count}")
        lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Build a human review annotation baseline from generated Markdown.")
    parser.add_argument("input", help="Human annotation Markdown file")
    parser.add_argument("output", help="Output JSON baseline file")
    parser.add_argument("--summary", help="Optional Markdown summary output")
    args = parser.parse_args()

    annotations = parse_human_annotation_markdown(args.input)
    output = Path(args.output)
    output.write_text(annotations_to_json(annotations), encoding="utf-8")
    summary = summarize_annotations(annotations)

    if args.summary:
        Path(args.summary).write_text(summary_to_markdown(summary), encoding="utf-8")

    print(f"baseline: {summary['total']} annotations -> {output}")


if __name__ == "__main__":
    raise SystemExit(main())
