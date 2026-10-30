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


def test_aligned_text_diff_pairs_headings_ignoring_section_numbers():
    a = (
        "## 6. Software Activation (Official Version)\n"
        "\n"
        "The software is a trial version with the following limitations:\n"
        "\n"
        "## 7. FAQ and Support\n"
        "Contact us.\n"
    )
    b = (
        "## 7. Software Activation (Official Version)\n"
        "\n"
        "The software is a trial version, with the following limitations:\n"
        "\n"
        "## 8. FAQ and Support\n"
        "Contact us.\n"
    )
    data = build_aligned_text_diff(a, b)
    activation = next(row for row in data["rows"] if "Software Activation" in row["a_text"])
    assert "Software Activation" in activation["b_text"]
    assert activation["op"] == "replace"
    faq = next(row for row in data["rows"] if "FAQ" in row["a_text"])
    assert "FAQ" in faq["b_text"]
    assert "Software Activation" not in faq["b_text"]


def test_aligned_text_diff_extra_section_does_not_shift_later_headings():
    a = "## 1. Alpha\n\nA body.\n\n## 2. Gamma\n\nG body.\n"
    b = "## 1. Alpha\n\nA body.\n\n## 2. Beta\n\nB body.\n\n## 3. Gamma\n\nG body.\n"
    data = build_aligned_text_diff(a, b)
    gamma = next(row for row in data["rows"] if "Gamma" in row["a_text"])
    assert "Gamma" in gamma["b_text"]
    assert any(row["op"] == "insert" and "Beta" in row["b_text"] for row in data["rows"])


def test_aligned_text_diff_pairs_rewritten_lines_on_same_row():
    a = (
        "If you have purchased an official license, activate it as follows:\n"
        "- Validity period: **90 days**\n"
    )
    b = (
        "If you have purchased an official license, please follow these steps to activate:\n"
        "- Validity period: **30 days**\n"
    )
    data = build_aligned_text_diff(a, b)
    activate = next(row for row in data["rows"] if "purchased an official license" in row["a_text"])
    assert "please follow these steps" in activate["b_text"]
    assert activate["op"] == "replace"
    assert activate["b_no"] is not None
    period = next(row for row in data["rows"] if "90 days" in row["a_text"])
    assert "30 days" in period["b_text"]
    assert period["op"] == "replace"


def test_aligned_text_diff_marks_case_only_as_unimportant():
    data = build_aligned_text_diff(
        "1. **Request a license file**\n",
        "1. **Request a License File**\n",
    )
    row = next(row for row in data["rows"] if "Request" in row["a_text"])
    assert row["op"] == "replace"
    assert row.get("unimportant") is True


def test_aligned_text_diff_keeps_gap_for_extra_line():
    data = build_aligned_text_diff("alpha\nbeta\n", "alpha\nINSERT\nbeta\n")
    assert any(row["op"] == "insert" and "INSERT" in row["b_text"] for row in data["rows"])
    assert any(row["op"] == "equal" and row["a_text"] == "beta" for row in data["rows"])
