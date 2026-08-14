import argparse
import html
import hashlib
import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from app.api.convert import (  # noqa: E402
    _clean_title,
    _docx_to_markdown,
    _extract_images_md,
    _flatten_sections,
    _normalize_docx_text,
    _parse_md_sections,
)


NOTE_PREFIXES = ("注意事项", "其他注意事项", "注意", "提示", "警告", "小心", "请勿", "切勿")
EN_NOTE_PREFIX_RE = re.compile(r'^(warning|caution|tips|danger|stop\s*point|stoppoint)[:：]?\s*(.*)$', re.IGNORECASE)
TABLE_CAPTION_RE = re.compile(r'^(表|Table)\s*\d+', re.IGNORECASE)
FIGURE_CAPTION_RE = re.compile(r'^(图|Figure)\s*\d+', re.IGNORECASE)
ORDERED_LIST_RE = re.compile(r'^\s*\d+[.)、]\s+')
UNORDERED_LIST_RE = re.compile(r'^\s*[-*•]\s+')


def _strip_list_prefix(text):
    return re.sub(r'^\s*(?:[-*+•]\s+|\d+[.)、]\s+)', '', text or '').strip()


def _strip_ns(tag):
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _source_title_counts(markdown_text):
    sections = _flatten_sections(_parse_md_sections(markdown_text))
    titles = []
    for sec in sections:
        title = _clean_title(sec.get("title", ""))
        if title in {"940-001527-00 (96 RXN)", "Kit Version: V3.0"}:
            continue
        titles.append(title)
    return Counter([t for t in titles if t])


def _source_expectations(markdown_text):
    lines = [_normalize_docx_text(line) for line in markdown_text.splitlines()]
    note_like = []
    table_titles = []
    figure_titles = []
    ordered_lines = []
    unordered_lines = []
    image_refs = _extract_images_md(markdown_text)
    effective_image_refs = []
    ignored_note_icon_images = []

    image_lines = []
    for idx, raw_line in enumerate(markdown_text.splitlines()):
        match = re.search(r'!\[[^\]]*\]\(([^)]+)\)', raw_line)
        if match:
            image_lines.append((idx, match.group(1)))

    note_line_indexes = set()

    for line in lines:
        stripped = line.strip()
        normalized = _strip_list_prefix(stripped)
        if not stripped:
            continue
        if normalized in {"注意事项", "其他注意事项"}:
            continue
        if any(normalized.startswith(prefix) for prefix in NOTE_PREFIXES):
            note_like.append(normalized)
        elif EN_NOTE_PREFIX_RE.match(normalized):
            note_like.append(normalized)
        if TABLE_CAPTION_RE.match(normalized):
            table_titles.append(normalized)
        if FIGURE_CAPTION_RE.match(normalized):
            figure_titles.append(normalized)
        if ORDERED_LIST_RE.match(line):
            ordered_lines.append(stripped)
        if UNORDERED_LIST_RE.match(line):
            unordered_lines.append(stripped)

    for idx, line in enumerate(lines):
        stripped = line.strip()
        normalized = _strip_list_prefix(stripped)
        if normalized and any(normalized.startswith(prefix) for prefix in NOTE_PREFIXES):
            note_line_indexes.add(idx)
        elif normalized and EN_NOTE_PREFIX_RE.match(normalized):
            note_line_indexes.add(idx)

    for idx, image_path in image_lines:
        related_to_note = any(abs(idx - note_idx) <= 2 for note_idx in note_line_indexes)
        if related_to_note:
            ignored_note_icon_images.append(image_path)
        else:
            effective_image_refs.append(image_path)

    effective_unique_content = {}
    for image_path in effective_image_refs:
        path = str(image_path or "").strip()
        if not path or not Path(path).exists():
            continue
        data = Path(path).read_bytes()
        sig = (len(data), hashlib.sha1(data).hexdigest())
        effective_unique_content.setdefault(sig, []).append(path)

    return {
        "note_like_count": len(note_like),
        "table_caption_count": len(table_titles),
        "figure_caption_count": len(figure_titles),
        "ordered_list_line_count": len(ordered_lines),
        "unordered_list_line_count": len(unordered_lines),
        "markdown_image_ref_count": len(image_refs),
        "effective_image_ref_count": len(effective_image_refs),
        "effective_unique_image_content_count": len(effective_unique_content),
        "ignored_note_icon_image_count": len(ignored_note_icon_images),
        "table_titles": table_titles,
        "figure_titles": figure_titles,
    }


def _parse_dita_package(zip_path):
    with zipfile.ZipFile(zip_path) as zf:
        ditamap_name = next(name for name in zf.namelist() if name.endswith(".ditamap"))
        ditamap_text = zf.read(ditamap_name).decode("utf-8", errors="ignore")
        navtitles = []
        for title, href in re.findall(r'navtitle="([^"]+)"[^>]*href="([^"]+\.dita)"', ditamap_text):
            title = html.unescape(title)
            if title in {"封面CN", "关于说明书", "版本记录", "编号：H-940-001530-00"}:
                continue
            navtitles.append(title)
        dita_files = [name for name in zf.namelist() if name.endswith(".dita")]
        image_files = [name for name in zf.namelist() if name.startswith("image/") and not name.endswith("/")]

        metrics = {
            "title_counts": Counter(navtitles),
            "dita_file_count": len(dita_files),
            "image_file_count": len(image_files),
            "unique_image_content_count": 0,
            "note_count": 0,
            "table_title_count": 0,
            "table_caption_paragraph_count": 0,
            "figure_title_count": 0,
            "ol_count": 0,
            "ul_count": 0,
            "duplicate_image_group_count": 0,
            "duplicate_image_file_count": 0,
            "note_files": [],
            "table_title_files": [],
            "table_caption_paragraph_files": [],
            "figure_title_files": [],
        }

        image_signatures = {}
        for image_name in image_files:
            data = zf.read(image_name)
            image_signatures.setdefault((len(data), data[:64]), []).append(image_name)
        dup_groups = [group for group in image_signatures.values() if len(group) > 1]
        metrics["unique_image_content_count"] = len(image_signatures)
        metrics["duplicate_image_group_count"] = len(dup_groups)
        metrics["duplicate_image_file_count"] = sum(len(group) for group in dup_groups)

        for dita_name in dita_files:
            text = zf.read(dita_name).decode("utf-8", errors="ignore")
            try:
                root = ET.fromstring(text)
            except ET.ParseError:
                continue

            note_count = 0
            table_title_count = 0
            table_caption_paragraph_count = 0
            figure_title_count = 0
            ol_count = 0
            ul_count = 0

            for elem in root.iter():
                tag = _strip_ns(elem.tag)
                if tag == "note":
                    note_count += 1
                elif tag == "table":
                    title_elem = next((child for child in list(elem) if _strip_ns(child.tag) == "title" and (child.text or "").strip()), None)
                    if title_elem is not None:
                        table_title_count += 1
                elif tag == "p":
                    text = "".join(elem.itertext()).strip()
                    if TABLE_CAPTION_RE.match(text):
                        table_caption_paragraph_count += 1
                elif tag == "fig":
                    title_elem = next((child for child in list(elem) if _strip_ns(child.tag) == "title" and (child.text or "").strip()), None)
                    if title_elem is not None:
                        figure_title_count += 1
                elif tag == "ol":
                    ol_count += 1
                elif tag == "ul":
                    ul_count += 1

            metrics["note_count"] += note_count
            metrics["table_title_count"] += table_title_count
            metrics["table_caption_paragraph_count"] += table_caption_paragraph_count
            metrics["figure_title_count"] += figure_title_count
            metrics["ol_count"] += ol_count
            metrics["ul_count"] += ul_count

            if note_count:
                metrics["note_files"].append(dita_name)
            if table_title_count:
                metrics["table_title_files"].append(dita_name)
            if table_caption_paragraph_count:
                metrics["table_caption_paragraph_files"].append(dita_name)
            if figure_title_count:
                metrics["figure_title_files"].append(dita_name)

    return metrics


def _source_docx_media_count(docx_path):
    with zipfile.ZipFile(docx_path) as zf:
        return len([name for name in zf.namelist() if name.startswith("word/media/") and not name.endswith("/")])


def build_report(docx_path, dita_zip_path):
    markdown_text = _docx_to_markdown(str(docx_path))
    source_titles = _source_title_counts(markdown_text)
    source_expect = _source_expectations(markdown_text)
    source_media_count = _source_docx_media_count(docx_path)
    dita_metrics = _parse_dita_package(dita_zip_path)

    missing_titles = source_titles - dita_metrics["title_counts"]
    extra_titles = dita_metrics["title_counts"] - source_titles

    checks = {
        "titles_match": {
            "passed": not missing_titles and not extra_titles,
            "source_count": sum(source_titles.values()),
            "dita_count": sum(dita_metrics["title_counts"].values()),
            "missing": dict(missing_titles),
            "extra": dict(extra_titles),
        },
        "images_not_lost": {
            "passed": dita_metrics["unique_image_content_count"] >= source_expect["effective_unique_image_content_count"],
            "source_docx_media_count": source_media_count,
            "source_markdown_image_ref_count": source_expect["markdown_image_ref_count"],
            "source_effective_image_ref_count": source_expect["effective_image_ref_count"],
            "source_effective_unique_image_content_count": source_expect["effective_unique_image_content_count"],
            "ignored_note_icon_image_count": source_expect["ignored_note_icon_image_count"],
            "dita_image_file_count": dita_metrics["image_file_count"],
            "dita_unique_image_content_count": dita_metrics["unique_image_content_count"],
            "duplicate_image_group_count": dita_metrics["duplicate_image_group_count"],
            "duplicate_image_file_count": dita_metrics["duplicate_image_file_count"],
        },
        "table_titles_converted": {
            "passed": dita_metrics["table_title_count"] + dita_metrics["table_caption_paragraph_count"] >= source_expect["table_caption_count"],
            "source_table_caption_count": source_expect["table_caption_count"],
            "dita_table_title_count": dita_metrics["table_title_count"],
            "dita_table_caption_paragraph_count": dita_metrics["table_caption_paragraph_count"],
        },
        "figure_titles_converted": {
            "passed": dita_metrics["figure_title_count"] >= source_expect["figure_caption_count"],
            "source_figure_caption_count": source_expect["figure_caption_count"],
            "dita_figure_title_count": dita_metrics["figure_title_count"],
        },
        "notes_converted": {
            "passed": dita_metrics["note_count"] >= source_expect["note_like_count"],
            "source_note_like_count": source_expect["note_like_count"],
            "dita_note_count": dita_metrics["note_count"],
        },
        "unordered_lists_converted": {
            "passed": dita_metrics["ul_count"] > 0 or source_expect["unordered_list_line_count"] == 0,
            "source_unordered_list_line_count": source_expect["unordered_list_line_count"],
            "dita_ul_count": dita_metrics["ul_count"],
        },
        "ordered_lists_converted": {
            "passed": dita_metrics["ol_count"] > 0 or source_expect["ordered_list_line_count"] == 0,
            "source_ordered_list_line_count": source_expect["ordered_list_line_count"],
            "dita_ol_count": dita_metrics["ol_count"],
        },
    }

    overall_passed = all(item["passed"] for item in checks.values())
    return {
        "passed": overall_passed,
        "docx_path": str(docx_path),
        "dita_zip_path": str(dita_zip_path),
        "checks": checks,
    }


def main():
    parser = argparse.ArgumentParser(description="校验 Word -> DITA 输出包")
    parser.add_argument("docx_path", type=Path)
    parser.add_argument("dita_zip_path", type=Path)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    report = build_report(args.docx_path, args.dita_zip_path)
    if args.pretty:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(report, ensure_ascii=False))

    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
