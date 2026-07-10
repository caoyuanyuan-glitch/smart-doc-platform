#!/usr/bin/env python3
"""Extract PDF and Word comments into one Markdown or JSON file.

Usage:
  python extract_pdf_annotations.py annotated.pdf
  python extract_pdf_annotations.py ./pdf-folder output.md
  python extract_pdf_annotations.py ./pdf-folder output.json --json
  python extract_pdf_annotations.py ./review-md-folder merged.md --merge-md
"""

import argparse
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path


WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def clean(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def has_comment(row):
    comment = clean(row.get("comment"))
    return bool(comment and comment != "-")


def input_files(path):
    path = Path(path)
    if path.is_dir():
        return sorted(
            file for file in path.rglob("*")
            if file.is_file() and file.suffix.lower() in {".pdf", ".docx"} and not file.name.startswith("~$")
        )
    return [path] if path.is_file() else []


def markdown_files(path):
    path = Path(path)
    if path.is_dir():
        return sorted(
            file for file in path.rglob("*.md")
            if file.is_file() and not file.name.startswith("~$")
        )
    return [path] if path.is_file() and path.suffix.lower() == ".md" else []


def extract_one(pdf):
    rows = []
    try:
        import fitz
    except ModuleNotFoundError:
        print("缺少 PyMuPDF 依赖，请运行：py -m pip install PyMuPDF")
        return rows

    try:
        doc = fitz.open(pdf)
    except Exception as exc:
        print(f"跳过无法读取的 PDF: {pdf} ({exc})")
        return rows
    for page_no, page in enumerate(doc, start=1):
        annot = page.first_annot
        while annot:
            info = annot.info or {}
            rect = annot.rect
            rows.append({
                "file": Path(pdf).name,
                "page": page_no,
                "type": annot.type[1],
                "author": clean(info.get("title")),
                "comment": clean(info.get("content")),
                "selected": clean(page.get_textbox(rect)),
                "context": clean(page.get_textbox(rect + (-90, -45, 180, 70))),
            })
            annot = annot.next
    return rows


def xml_text(node):
    if node is None:
        return ""
    return clean("".join(text.text or "" for text in node.findall(".//w:t", WORD_NS)))


def extract_docx(docx):
    rows = []
    try:
        archive = zipfile.ZipFile(docx)
    except zipfile.BadZipFile:
        print(f"跳过无法读取的 Word 文件: {docx}")
        return rows
    with archive:
        names = set(archive.namelist())
        if "word/comments.xml" not in names:
            return rows

        comments_root = ET.fromstring(archive.read("word/comments.xml"))
        comments = {}
        for comment in comments_root.findall("w:comment", WORD_NS):
            comment_id = comment.attrib.get(f"{{{WORD_NS['w']}}}id", "")
            comments[comment_id] = {
                "author": comment.attrib.get(f"{{{WORD_NS['w']}}}author", ""),
                "comment": xml_text(comment),
            }

        selected_by_id = {}
        if "word/document.xml" in names:
            document_root = ET.fromstring(archive.read("word/document.xml"))
            active_id = None
            parts = []
            for elem in document_root.iter():
                tag = elem.tag.rsplit("}", 1)[-1]
                if tag == "commentRangeStart":
                    active_id = elem.attrib.get(f"{{{WORD_NS['w']}}}id", "")
                    parts = []
                elif tag == "t" and active_id is not None:
                    parts.append(elem.text or "")
                elif tag == "commentRangeEnd":
                    end_id = elem.attrib.get(f"{{{WORD_NS['w']}}}id", "")
                    if active_id == end_id:
                        selected_by_id[active_id] = clean("".join(parts))
                        active_id = None
                        parts = []

        for comment_id, data in comments.items():
            selected = selected_by_id.get(comment_id, "")
            rows.append({
                "file": Path(docx).name,
                "page": "-",
                "type": "WordComment",
                "author": clean(data.get("author")),
                "comment": clean(data.get("comment")),
                "selected": selected,
                "context": selected,
            })
    return rows


def extract_all(input_path):
    rows = []
    for file in input_files(input_path):
        suffix = file.suffix.lower()
        if suffix == ".pdf":
            rows.extend(extract_one(file))
        elif suffix == ".docx":
            rows.extend(extract_docx(file))
    return [row for row in rows if has_comment(row)]


def parse_bullet(block, label):
    pattern = rf"^- {re.escape(label)}: (.*)$"
    match = re.search(pattern, block, flags=re.MULTILINE)
    return clean(match.group(1)) if match else ""


def parse_markdown_file(md_file):
    text = Path(md_file).read_text(encoding="utf-8-sig")
    rows = []
    blocks = re.split(r"(?=^## \d+\. )", text, flags=re.MULTILINE)
    for block in blocks:
        header = re.search(r"^## \d+\. (.*?) · 第 (.*?) 页", block, flags=re.MULTILINE)
        if not header:
            continue
        row = {
            "file": clean(header.group(1)),
            "page": clean(header.group(2)),
            "type": parse_bullet(block, "批注类型"),
            "author": parse_bullet(block, "批注人"),
            "comment": parse_bullet(block, "人工意见"),
            "selected": parse_bullet(block, "选中文本"),
            "context": parse_bullet(block, "附近正文"),
        }
        if has_comment(row):
            rows.append(row)
    return rows


def merge_markdown(input_path):
    rows = []
    for md_file in markdown_files(input_path):
        rows.extend(parse_markdown_file(md_file))
    return rows


def to_markdown(rows):
    lines = ["# 人工审核 PDF 和 Word 批注汇总", ""]
    for i, row in enumerate(rows, start=1):
        lines += [
            f"## {i}. {row['file']} · 第 {row['page']} 页",
            "",
            f"- 批注类型: {row['type']}",
            f"- 批注人: {row['author'] or '-'}",
            f"- 人工意见: {row['comment'] or '-'}",
            f"- 选中文本: {row['selected'] or '-'}",
            f"- 附近正文: {row['context'] or '-'}",
            "- 知识库整理:",
            "  - 类别: [待归类]",
            "  - 触发条件: [待补充]",
            "  - 例外条件: [待补充]",
            "  - 修改建议: [待补充]",
            "",
        ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Extract or merge PDF and Word comments into a single file.")
    parser.add_argument("input", help="PDF/DOCX file, folder, or Markdown folder when using --merge-md")
    parser.add_argument("output", nargs="?", default="人工审核意见汇总.md")
    parser.add_argument("--json", action="store_true", help="write JSON instead of Markdown")
    parser.add_argument("--merge-md", action="store_true", help="merge generated Markdown comment files")
    args = parser.parse_args()

    rows = merge_markdown(args.input) if args.merge_md else extract_all(args.input)
    output = Path(args.output)
    if args.json or output.suffix.lower() == ".json":
        output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        output.write_text(to_markdown(rows), encoding="utf-8")
    print(f"提取完成: {len(rows)} 条批注 -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
