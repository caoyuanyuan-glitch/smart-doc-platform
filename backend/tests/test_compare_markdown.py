import os
import tempfile

from app.utils.doc_parser import compare_documents_by_format, parse_markdown
from app.utils.md_compare import parse_markdown_blocks, build_aligned_text_diff
from app.utils.compare_preview import build_highlighted_preview


def _write(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def test_parse_markdown_headingless_becomes_full_text_chapter():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "plain.md")
        _write(path, "Hello world.\n\nSecond paragraph.")
        parsed = parse_markdown(path)
        assert parsed["type"] == "md"
        assert parsed["chapters"]
        assert parsed["chapters"][0]["heading"] == "全文"
        assert "Hello world" in parsed["chapters"][0]["content"]
        assert "Second paragraph" in parsed["chapters"][0]["content"]


def test_parse_markdown_keeps_preamble_before_first_heading():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "intro.md")
        _write(path, "Intro sentence.\n\n# Chapter\n\nBody text.")
        parsed = parse_markdown(path)
        assert parsed["chapters"]
        first = parsed["chapters"][0]
        assert "Intro sentence" in first["content"]
        assert "Body text" in first["content"]


def test_compare_headingless_markdown_detects_change():
    with tempfile.TemporaryDirectory() as tmp:
        a = os.path.join(tmp, "a.md")
        b = os.path.join(tmp, "b.md")
        _write(a, "Keep this sentence. Old value is 12.")
        _write(b, "Keep this sentence. New value is 34.")
        result = compare_documents_by_format(a, b)
        assert result["type_a"] == "md"
        assert result["type_b"] == "md"
        assert result["stats"]["n_topics_a"] >= 1
        assert result["stats"]["overall_sim"] < 1.0
        assert result["results"]


def test_compare_identical_markdown_is_full_match():
    with tempfile.TemporaryDirectory() as tmp:
        a = os.path.join(tmp, "a.md")
        b = os.path.join(tmp, "b.md")
        text = "# Title\n\nSame paragraph.\n\n- item one\n"
        _write(a, text)
        _write(b, text)
        result = compare_documents_by_format(a, b)
        assert result["stats"]["overall_sim"] >= 0.99


def test_parse_markdown_blocks_splits_structure():
    text = "# Title\n\nHello\n\n```\ncode\n\nstill code\n```\n\n- a\n- b\n"
    blocks = parse_markdown_blocks(text)
    tags = [b["tag"] for b in blocks]
    assert tags[0] == "h1"
    assert "pre" in tags
    assert tags.count("li") == 2
    pre = next(b for b in blocks if b["tag"] == "pre")
    assert "still code" in pre["text"]


def test_md_preview_marks_insert_and_change():
    with tempfile.TemporaryDirectory() as tmp:
        a = os.path.join(tmp, "a.md")
        b = os.path.join(tmp, "b.md")
        _write(a, "# Title\n\nHello world\n\nKeep me")
        _write(b, "# Title\n\nHello WORLD\n\nKeep me\n\nNew para")
        html_a = build_highlighted_preview(a, "a.md", b, "b.md", "a")
        html_b = build_highlighted_preview(b, "b.md", a, "a.md", "b")
        assert "hl-chg" in html_a
        assert "hl-ins" in html_b
        assert "New para" in html_b


def test_md_preview_keeps_fenced_code_as_one_block():
    with tempfile.TemporaryDirectory() as tmp:
        a = os.path.join(tmp, "a.md")
        b = os.path.join(tmp, "b.md")
        _write(a, "# Demo\n\n```python\nfoo\n\nbar\n```\n")
        _write(b, "# Demo\n\n```python\nfoo\n\nbaz\n```\n")
        html_a = build_highlighted_preview(a, "a.md", b, "b.md", "a")
        html_b = build_highlighted_preview(b, "b.md", a, "a.md", "b")
        assert html_a.count("md-code") == 1
        assert html_b.count("md-code") == 1
        assert "hl-chg" in html_a
        assert "hl-chg" in html_b
        assert "bar" in html_a
        assert "baz" in html_b


def test_md_preview_marks_list_insert_and_table_change():
    with tempfile.TemporaryDirectory() as tmp:
        a = os.path.join(tmp, "a.markdown")
        b = os.path.join(tmp, "b.markdown")
        _write(a, "- Alpha\n- Beta\n")
        _write(b, "- Alpha\n- Beta\n- Gamma\n")
        html_b = build_highlighted_preview(b, "b.markdown", a, "a.markdown", "b")
        assert "Gamma" in html_b
        assert "hl-ins" in html_b


def test_md_preview_marks_table_cell_change():
    with tempfile.TemporaryDirectory() as tmp:
        a = os.path.join(tmp, "a.md")
        b = os.path.join(tmp, "b.md")
        _write(a, "| Name | Val |\n| --- | --- |\n| n | 1 |\n")
        _write(b, "| Name | Val |\n| --- | --- |\n| n | 2 |\n")
        html_a = build_highlighted_preview(a, "a.md", b, "b.md", "a")
        html_b = build_highlighted_preview(b, "b.md", a, "a.md", "b")
        assert "hl-chg" in html_a
        assert "hl-chg" in html_b
        assert ">1<" in html_a
        assert ">2<" in html_b


def test_aligned_text_diff_identical_has_no_sections():
    data = build_aligned_text_diff("a\nb\n", "a\nb\n")
    assert data["diff_count"] == 0
    assert all(row["op"] == "equal" for row in data["rows"])


def test_aligned_text_diff_replace_insert_and_char_spans():
    data = build_aligned_text_diff("alpha\nkeep\n", "beta\nkeep\ngamma\n")
    ops = [row["op"] for row in data["rows"]]
    assert "replace" in ops
    assert any(row["op"] == "insert" and "gamma" in row["b_text"] for row in data["rows"])
    assert data["diff_count"] >= 1
    first = next(row for row in data["rows"] if row["op"] == "replace")
    assert any(span["k"] != "eq" for span in first["a_spans"])
    assert any(span["k"] != "eq" for span in first["b_spans"])


def test_aligned_text_diff_delete_leaves_gap():
    data = build_aligned_text_diff("keep\ngone\n", "keep\n")
    deleted = [row for row in data["rows"] if row["op"] == "delete"]
    assert deleted
    assert deleted[0]["b_no"] is None
    assert "gone" in deleted[0]["a_text"]
