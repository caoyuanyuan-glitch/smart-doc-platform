"""Markdown block parser for compare preview and structured diffs."""
import html
import re
from difflib import SequenceMatcher


def _norm_text(text):
    return re.sub(r"\s+", "", text or "").strip()


def md_inline_html(text):
    s = html.escape(text or "")
    s = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", r'<img alt="\1" src="\2">', s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", s)
    return s


def _is_fence(line):
    stripped = (line or "").lstrip()
    return stripped.startswith("```") or stripped.startswith("~~~")


def _fence_marker(line):
    stripped = (line or "").lstrip()
    if stripped.startswith("```"):
        return "```"
    if stripped.startswith("~~~"):
        return "~~~"
    return ""


def _heading(line):
    m = re.match(r"^(#{1,6})\s+(.+)$", (line or "").strip())
    if not m:
        return None
    return len(m.group(1)), m.group(2).strip()


def _is_hr(line):
    s = re.sub(r"\s+", "", line or "")
    return bool(re.match(r"^([-*_])\1{2,}$", s))


def _is_table_sep(line):
    s = (line or "").strip()
    if "|" not in s:
        return False
    parts = [p.strip() for p in s.strip("|").split("|")]
    parts = [p for p in parts if p]
    if not parts:
        return False
    return all(re.match(r"^:?-{3,}:?$", p) for p in parts)


def _is_list_item(line):
    return bool(re.match(r"^([-*+]|\d+[.)])\s+", (line or "").strip()))


def _list_item_text(line):
    m = re.match(r"^([-*+]|\d+[.)])\s+(.*)$", (line or "").strip())
    return m.group(2) if m else (line or "").strip()


def _is_ordered_item(line):
    return bool(re.match(r"^\d+[.)]\s+", (line or "").strip()))


def _table_block(lines):
    rows = []
    for i, line in enumerate(lines):
        if i == 1 and _is_table_sep(line):
            continue
        cells = [c.strip() for c in (line or "").strip().strip("|").split("|")]
        rows.append(cells)
    keys = []
    texts = []
    rows_html = []
    for ridx, cells in enumerate(rows):
        cell_tag = "th" if ridx == 0 else "td"
        html_cells = []
        for cell in cells:
            keys.append(_norm_text(cell))
            texts.append(cell)
            html_cells.append(f"<{cell_tag}>{html.escape(cell)}</{cell_tag}>")
        rows_html.append("<tr>" + "".join(html_cells) + "</tr>")
    return {
        "key": "|".join(keys),
        "text": "\n".join(texts),
        "tag": "table",
        "html": '<table class="doc-preview-table">' + "".join(rows_html) + "</table>",
    }


def parse_markdown_blocks(text):
    """Split markdown into comparable preview blocks (heading/para/list/code/table)."""
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue

        if _is_fence(stripped):
            fence = _fence_marker(stripped)
            lang = stripped[len(fence):].strip()
            i += 1
            code_lines = []
            while i < n and not lines[i].lstrip().startswith(fence):
                code_lines.append(lines[i])
                i += 1
            if i < n:
                i += 1
            code = "\n".join(code_lines)
            lang_attr = f' class="lang-{html.escape(lang)}"' if lang else ""
            blocks.append({
                "key": _norm_text(code),
                "text": code,
                "tag": "pre",
                "html": f'<pre class="md-code"><code{lang_attr}>{html.escape(code)}</code></pre>',
            })
            continue

        heading = _heading(stripped)
        if heading:
            level, body = heading
            tag = f"h{min(max(level, 1), 6)}"
            blocks.append({
                "key": _norm_text(body),
                "text": body,
                "tag": tag,
                "html": f"<{tag}>{html.escape(body)}</{tag}>",
            })
            i += 1
            continue

        if _is_hr(stripped):
            i += 1
            continue

        if stripped.startswith(">"):
            quote_lines = []
            while i < n and lines[i].strip().startswith(">"):
                quote_lines.append(re.sub(r"^>\s?", "", lines[i].strip()))
                i += 1
            body = "\n".join(quote_lines)
            blocks.append({
                "key": _norm_text(body),
                "text": body,
                "tag": "blockquote",
                "html": f"<blockquote>{md_inline_html(body)}</blockquote>",
            })
            continue

        if "|" in stripped and i + 1 < n and _is_table_sep(lines[i + 1]):
            table_lines = [stripped]
            i += 1
            while i < n and "|" in lines[i]:
                table_lines.append(lines[i].strip())
                i += 1
            blocks.append(_table_block(table_lines))
            continue

        if _is_list_item(stripped):
            ordered = _is_ordered_item(stripped)
            start_no = 1
            mnum = re.match(r"^(\d+)", stripped)
            if ordered and mnum:
                start_no = int(mnum.group(1))
            item_index = 0
            while i < n:
                raw_line = lines[i]
                s = raw_line.strip()
                if not s:
                    j = i + 1
                    while j < n and not lines[j].strip():
                        j += 1
                    if j < n and _is_list_item(lines[j]):
                        i = j
                        continue
                    break
                if _is_list_item(s):
                    item = _list_item_text(s)
                    list_tag = "ol" if ordered else "ul"
                    start_attr = f' start="{start_no + item_index}"' if ordered else ""
                    blocks.append({
                        "key": _norm_text(item),
                        "text": item,
                        "tag": "li",
                        "html": (
                            f'<{list_tag} class="md-loose-list"{start_attr}>'
                            f"<li>{md_inline_html(item)}</li></{list_tag}>"
                        ),
                    })
                    item_index += 1
                    i += 1
                    continue
                if raw_line.startswith(" ") or raw_line.startswith("\t"):
                    if blocks and blocks[-1].get("tag") == "li":
                        extra = s
                        blocks[-1]["text"] = (blocks[-1]["text"] + " " + extra).strip()
                        blocks[-1]["key"] = _norm_text(blocks[-1]["text"])
                        list_tag = "ol" if ordered else "ul"
                        blocks[-1]["html"] = (
                            f'<{list_tag} class="md-loose-list">'
                            f"<li>{md_inline_html(blocks[-1]['text'])}</li></{list_tag}>"
                        )
                    i += 1
                    continue
                break
            continue

        para = [stripped]
        i += 1
        while i < n:
            nxt = lines[i]
            ns = nxt.strip()
            if not ns:
                break
            if _is_fence(ns) or _heading(ns) or _is_hr(ns) or _is_list_item(ns) or ns.startswith(">"):
                break
            if "|" in ns and i + 1 < n and _is_table_sep(lines[i + 1]):
                break
            para.append(ns)
            i += 1
        body = " ".join(para)
        blocks.append({
            "key": _norm_text(body),
            "text": body,
            "tag": "p",
            "html": f"<p>{md_inline_html(body)}</p>",
        })

    return blocks


def _char_spans(text_a, text_b, side):
    a = text_a or ""
    b = text_b or ""
    sm = SequenceMatcher(None, a, b, autojunk=False)
    spans = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if side == "a":
            chunk = a[i1:i2]
            if not chunk:
                continue
            kind = "eq" if tag == "equal" else ("del" if tag == "delete" else "chg")
            spans.append({"t": chunk, "k": kind})
        else:
            chunk = b[j1:j2]
            if not chunk:
                continue
            kind = "eq" if tag == "equal" else ("ins" if tag == "insert" else "chg")
            spans.append({"t": chunk, "k": kind})
    return spans


def _split_lines(text):
    return (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _diff_sections(rows):
    sections = []
    start = None
    for idx, row in enumerate(rows):
        if row.get("op") != "equal":
            if start is None:
                start = idx
            continue
        if start is not None:
            sections.append({"start": start, "end": idx - 1})
            start = None
    if start is not None:
        sections.append({"start": start, "end": len(rows) - 1})
    return sections


def build_aligned_text_diff(text_a, text_b):
    """Line-aligned text diff in Beyond Compare layout: equal / replace / insert / delete."""
    lines_a = _split_lines(text_a)
    lines_b = _split_lines(text_b)
    sm = SequenceMatcher(None, lines_a, lines_b, autojunk=False)
    rows = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                line = lines_a[i1 + k]
                rows.append({
                    "op": "equal",
                    "a_no": i1 + k + 1,
                    "b_no": j1 + k + 1,
                    "a_text": line,
                    "b_text": lines_b[j1 + k],
                    "a_spans": [{"t": line, "k": "eq"}],
                    "b_spans": [{"t": lines_b[j1 + k], "k": "eq"}],
                })
            continue
        if tag == "delete":
            for k in range(i2 - i1):
                line = lines_a[i1 + k]
                rows.append({
                    "op": "delete",
                    "a_no": i1 + k + 1,
                    "b_no": None,
                    "a_text": line,
                    "b_text": "",
                    "a_spans": [{"t": line, "k": "del"}],
                    "b_spans": [],
                })
            continue
        if tag == "insert":
            for k in range(j2 - j1):
                line = lines_b[j1 + k]
                rows.append({
                    "op": "insert",
                    "a_no": None,
                    "b_no": j1 + k + 1,
                    "a_text": "",
                    "b_text": line,
                    "a_spans": [],
                    "b_spans": [{"t": line, "k": "ins"}],
                })
            continue
        n_pair = min(i2 - i1, j2 - j1)
        for k in range(n_pair):
            ta = lines_a[i1 + k]
            tb = lines_b[j1 + k]
            rows.append({
                "op": "replace",
                "a_no": i1 + k + 1,
                "b_no": j1 + k + 1,
                "a_text": ta,
                "b_text": tb,
                "a_spans": _char_spans(ta, tb, "a"),
                "b_spans": _char_spans(ta, tb, "b"),
            })
        for k in range(n_pair, i2 - i1):
            line = lines_a[i1 + k]
            rows.append({
                "op": "delete",
                "a_no": i1 + k + 1,
                "b_no": None,
                "a_text": line,
                "b_text": "",
                "a_spans": [{"t": line, "k": "del"}],
                "b_spans": [],
            })
        for k in range(n_pair, j2 - j1):
            line = lines_b[j1 + k]
            rows.append({
                "op": "insert",
                "a_no": None,
                "b_no": j1 + k + 1,
                "a_text": "",
                "b_text": line,
                "a_spans": [],
                "b_spans": [{"t": line, "k": "ins"}],
            })
    sections = _diff_sections(rows)
    return {
        "rows": rows,
        "diff_sections": sections,
        "diff_count": len(sections),
        "n_a": len(lines_a),
        "n_b": len(lines_b),
    }
