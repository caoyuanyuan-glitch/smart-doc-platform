#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI: extract PDF and Word comments into one Markdown or JSON file.

Usage:
  python extract_pdf_annotations.py annotated.pdf
  python extract_pdf_annotations.py ./pdf-folder output.md
  python extract_pdf_annotations.py ./pdf-folder output.json --json
  python extract_pdf_annotations.py ./review-md-folder merged.md --merge-md
"""
import argparse
from importlib.machinery import SourceFileLoader
import json
from pathlib import Path


def load_core():
    pyw = Path(__file__).with_name("annotation_extractor.pyw")
    if not pyw.is_file():
        raise RuntimeError(f"无法加载 {pyw}")
    return SourceFileLoader("annotation_extractor_core", str(pyw)).load_module()


def main():
    parser = argparse.ArgumentParser(description="Extract or merge PDF and Word comments into a single file.")
    parser.add_argument("input", help="PDF/DOCX file, folder, or Markdown folder when using --merge-md")
    parser.add_argument("output", nargs="?", default="人工审核意见汇总.md")
    parser.add_argument("--json", action="store_true", help="write JSON instead of Markdown")
    parser.add_argument("--merge-md", action="store_true", help="merge generated Markdown comment files")
    args = parser.parse_args()

    core = load_core()
    if args.merge_md:
        rows = core.merge_markdown(args.input)
        errors = []
    else:
        rows, errors = core.extract_all(args.input)

    output = Path(args.output)
    if args.json or output.suffix.lower() == ".json":
        output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        output.write_text(core.to_markdown(rows), encoding="utf-8")
    print(f"提取完成: {len(rows)} 条批注 -> {output}")
    for err in errors:
        print(f"跳过: {err}")


if __name__ == "__main__":
    main()
