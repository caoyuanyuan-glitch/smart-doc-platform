from importlib.machinery import SourceFileLoader
from pathlib import Path
import unittest
import tempfile
import zipfile

import fitz


CORE = SourceFileLoader(
    "review_comment_extractor_core",
    str(Path(__file__).resolve().parents[1] / "scripts" / "review_comment_extractor" / "annotation_extractor.pyw"),
).load_module()


def build_sample_page():
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 80), "1.1 Intended use", fontsize=14)
    body = (
        "This kit uses RCA to obtain DNA nanoballs for sample processing "
        "before sequencing on a high-throughput platform."
    )
    page.insert_textbox(fitz.Rect(72, 96, 520, 150), body, fontsize=11)
    page.insert_text((72, 200), "1.2 Principle", fontsize=14)
    page.insert_textbox(
        fitz.Rect(72, 216, 520, 260),
        "The kit performs RCA in one reaction system.",
        fontsize=11,
    )
    return doc, page, body


class PdfCommentContextTest(unittest.TestCase):
    def test_strikeout_keeps_paragraph_and_stops_at_next_heading(self):
        doc, page, body = build_sample_page()
        annot = page.add_strikeout_annot(fitz.Rect(72, 96, 250, 110))
        selected, context = CORE.extract_selected_and_context(page, annot)
        doc.close()

        self.assertTrue(selected)
        self.assertIn(selected.replace(" ", ""), body.replace(" ", ""))
        self.assertIn("1.1 Intended use", context)
        self.assertIn("DNA nanoballs", context)
        self.assertIn("high-throughput platform", context)
        self.assertNotIn("1.2 Principle", context)

    def test_selected_text_is_contiguous(self):
        doc, page, body = build_sample_page()
        annot = page.add_strikeout_annot(fitz.Rect(72, 96, 280, 110))
        selected, _context = CORE.extract_selected_and_context(page, annot)
        doc.close()

        collapsed_body = body.replace(" ", "")
        collapsed_selected = selected.replace(" ", "")
        self.assertIn(collapsed_selected, collapsed_body)
        self.assertGreater(len(collapsed_selected), 8)

    def test_caret_context_stays_in_section(self):
        doc, page, _body = build_sample_page()
        annot = page.add_caret_annot(fitz.Point(240, 110))
        _selected, context = CORE.extract_selected_and_context(page, annot)
        doc.close()

        self.assertIn("DNA nanoballs", context)
        self.assertNotIn("1.2 Principle", context)


class ChangeHintTest(unittest.TestCase):
    def test_replace_pattern(self):
        hint = CORE.interpret_change("试剂盒", "试剂盒改成试剂槽", "试剂盒已经融化")
        self.assertIn("把「试剂盒」改成「试剂槽」", hint)

    def test_space_before_comma(self):
        hint = CORE.interpret_change("6", "逗号前面多了一个空格", "7.0 April 16, 2026")
        self.assertIn("逗号前面多了一个空格", hint)
        self.assertIn("7.0 April 16, 2026", hint)

    def test_short_insert_uses_sentence(self):
        sentence = "如试剂盒已经融化，但不能按时使用，最多可再冻融一次。"
        hint = CORE.interpret_change("", "当", sentence)
        self.assertIn("当", hint)
        self.assertIn("如试剂盒已经融化", hint)

    def test_markdown_has_change_section(self):
        text = CORE.to_markdown([{
            "file": "demo.pdf",
            "page": 35,
            "type": "Square",
            "author": "caoyuanyuan",
            "comment": "当",
            "selected": "",
            "heading": "9.2 试剂盒暂存",
            "sentence": "如试剂盒已经融化，但不能按时使用，最多可再冻融一次。",
            "context": "如试剂盒已经融化，但不能按时使用，最多可再冻融一次。",
            "change": "",
            "rect": "(72.0, 401.2, 210.5, 409.8)",
            "shot": "批注截图/p35_ann1.jpg",
        }])
        self.assertIn("### 批注覆盖文本", text)
        self.assertIn("批注矩形: (72.0, 401.2, 210.5, 409.8)", text)
        self.assertIn("批注截图: 批注截图/p35_ann1.jpg", text)
        self.assertIn("（空——批注覆盖在图上/线框区域，无文本层）", text)
        self.assertIn("### 原文", text)
        self.assertIn("【9.2 试剂盒暂存】", text)
        self.assertNotIn("知识库整理", text)
        self.assertNotIn("### 改什么", text)

    def test_square_margin_keeps_sentence(self):
        doc, page, body = build_sample_page()
        annot = page.add_rect_annot(fitz.Rect(20, 98, 38, 114))
        annot.set_info(content="逗号前面多了一个空格")
        view = CORE.extract_comment_view(page, annot)
        doc.close()
        self.assertIn("DNA nanoballs", view["sentence"] or view["context"])
        self.assertNotEqual(view["selected"], "6")
        self.assertIn("空格", view["change"])

    def test_extract_pdf_writes_rect_and_shot(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc, page, _body = build_sample_page()
            annot = page.add_rect_annot(fitz.Rect(72, 96, 250, 110))
            annot.set_info(content="多余了一条线")
            pdf_path = Path(tmp) / "sample.pdf"
            doc.save(str(pdf_path))
            doc.close()
            rows = CORE.extract_pdf(pdf_path, pdf_path.parent)
            self.assertTrue(rows)
            self.assertTrue(rows[0]["rect"].startswith("("))
            self.assertTrue(rows[0]["shot"].endswith(".jpg"))
            self.assertTrue(rows[0]["shot"].startswith("批注截图/"))
            shot_path = pdf_path.parent / "批注截图" / Path(rows[0]["shot"]).name
            self.assertTrue(shot_path.is_file())
            text = CORE.to_markdown(rows)
            self.assertIn("批注矩形:", text)
            self.assertIn("### 批注覆盖文本", text)
            self.assertNotIn("知识库整理", text)
            pix = fitz.Pixmap(str(shot_path))
            self.assertGreaterEqual(min(pix.width, pix.height), 300)

    def test_text_strikeout_skips_shot(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc, page, _body = build_sample_page()
            annot = page.add_strikeout_annot(fitz.Rect(72, 96, 250, 110))
            annot.set_info(content="逗号前面多了一个空格")
            pdf_path = Path(tmp) / "sample.pdf"
            doc.save(str(pdf_path))
            doc.close()
            rows = CORE.extract_pdf(pdf_path, pdf_path.parent)
            self.assertTrue(rows)
            self.assertTrue(rows[0]["selected"].strip())
            self.assertEqual(rows[0]["shot"], "")
            shot_dir = pdf_path.parent / "批注截图"
            shots = list(shot_dir.glob("*.jpg")) if shot_dir.exists() else []
            self.assertEqual(shots, [])
            self.assertIn("批注截图: -", CORE.to_markdown(rows))

    def test_visual_keyword_writes_shot(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc, page, _body = build_sample_page()
            annot = page.add_strikeout_annot(fitz.Rect(72, 96, 250, 110))
            annot.set_info(content="列宽不对")
            pdf_path = Path(tmp) / "sample.pdf"
            doc.save(str(pdf_path))
            doc.close()
            rows = CORE.extract_pdf(pdf_path, pdf_path.parent)
            self.assertTrue(rows[0]["selected"].strip())
            self.assertTrue(rows[0]["shot"].endswith(".jpg"))
            shot_path = pdf_path.parent / "批注截图" / Path(rows[0]["shot"]).name
            self.assertTrue(shot_path.is_file())

    def test_textual_comment_skips_shot_when_selected_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc, page, _body = build_sample_page()
            annot = page.add_rect_annot(fitz.Rect(20, 98, 38, 114))
            annot.set_info(content="中英文不一致")
            pdf_path = Path(tmp) / "sample.pdf"
            doc.save(str(pdf_path))
            doc.close()
            rows = CORE.extract_pdf(pdf_path, pdf_path.parent)
            self.assertEqual(rows[0]["shot"], "")
            self.assertIn("批注截图: -", CORE.to_markdown(rows))


class VerticesCompatibilityTest(unittest.TestCase):
    def _assert_one_rect(self, vertices):
        class FakeAnnot:
            def __init__(self, verts, rect):
                self.vertices = verts
                self.rect = rect

        annot = FakeAnnot(vertices, fitz.Rect(72, 98, 220, 118))
        rects = CORE.markup_rects(annot)
        self.assertEqual(len(rects), 1)
        self.assertFalse(rects[0].is_empty)

    def test_nested_quad_of_point_tuples(self):
        self._assert_one_rect([
            [(72.0, 98.0), (220.0, 98.0), (72.0, 118.0), (220.0, 118.0)],
        ])

    def test_list_of_point_tuples(self):
        self._assert_one_rect([
            (72.0, 98.0), (220.0, 98.0), (72.0, 118.0), (220.0, 118.0),
        ])

    def test_flat_floats(self):
        self._assert_one_rect([72.0, 98.0, 220.0, 98.0, 72.0, 118.0, 220.0, 118.0])

    def test_as_float_skips_tuple(self):
        self.assertEqual(CORE._as_float((11.0, 12.0)), 0.0)
        self.assertEqual(CORE._as_float(11.5), 11.5)


class OutputPathTest(unittest.TestCase):
    def test_custom_filename_joins_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = CORE.normalize_output_path(tmp, "内部审核意见汇总1026.md")
            self.assertEqual(out, Path(tmp) / "内部审核意见汇总1026.md")

    def test_existing_directory_name_gets_default_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            nested = Path(tmp) / "new"
            nested.mkdir()
            out = CORE.normalize_output_path(tmp, "new")
            self.assertEqual(out, nested / "人工审核意见汇总.md")

    def test_bare_name_gets_md_suffix(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = CORE.normalize_output_path(tmp, "汇总1026")
            self.assertEqual(out.name, "汇总1026.md")
            self.assertEqual(out.parent, Path(tmp))


class VisualAnnotTest(unittest.TestCase):
    def test_empty_selected_is_visual(self):
        self.assertTrue(CORE.is_visual_annot(None, None, "", "当"))

    def test_visual_keyword_is_visual(self):
        self.assertTrue(CORE.is_visual_annot(None, None, "April 16", "列宽不对"))

    def test_text_comment_is_not_visual(self):
        self.assertFalse(
            CORE.is_visual_annot(None, None, "April 16 , 2026", "逗号前面多了一个空格")
        )

    def test_page_drawing_outside_box_is_visual(self):
        doc, page, _body = build_sample_page()
        shape = page.new_shape()
        shape.draw_line(fitz.Point(40, 104), fitz.Point(550, 104))
        shape.finish(color=(0, 0, 0), width=1)
        shape.commit()
        annot = page.add_strikeout_annot(fitz.Rect(72, 96, 250, 110))
        self.assertFalse(
            CORE.is_visual_annot(page, annot, "This kit uses RCA", "逗号前面多了一个空格")
        )
        doc.close()

    def test_textual_keyword_skips_empty_selected(self):
        self.assertFalse(CORE.is_visual_annot(None, None, "", "中英文不一致"))
        self.assertFalse(CORE.is_visual_annot(None, None, "", "重复内容"))
        self.assertFalse(CORE.is_visual_annot(None, None, "", "逗号前面多了一个空格"))
        self.assertFalse(CORE.is_visual_annot(None, None, "", "拼写错误，应该是：prediction"))
        self.assertFalse(CORE.is_visual_annot(None, None, "", "缺定冠词the"))
        self.assertFalse(CORE.is_visual_annot(None, None, "", "建议改为product"))

    def test_visual_keyword_beats_textual(self):
        self.assertTrue(CORE.is_visual_annot(None, None, "", "图中文字不对"))


class PackOutputTest(unittest.TestCase):
    def test_pack_output_includes_md_and_jpg(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            md_path = root / "汇总.md"
            md_path.write_text("# demo\n", encoding="utf-8")
            shot_dir = root / "批注截图"
            shot_dir.mkdir(parents=True)
            (shot_dir / "p1_ann1.jpg").write_bytes(b"\xff\xd8\xff")
            zip_paths = CORE.pack_output(md_path, CORE.collect_shot_dirs(root), "内部审核意见汇总1026")
            self.assertEqual(len(zip_paths), 1)
            self.assertTrue(zip_paths[0].is_file())
            with zipfile.ZipFile(zip_paths[0]) as zf:
                names = set(zf.namelist())
            self.assertIn("内部审核意见汇总1026/汇总.md", names)
            self.assertIn("内部审核意见汇总1026/批注截图/p1_ann1.jpg", names)

    def test_pack_output_splits_over_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            md_path = root / "汇总.md"
            md_path.write_text("# demo\n", encoding="utf-8")
            shot_dir = root / "批注截图"
            shot_dir.mkdir()
            (shot_dir / "a.jpg").write_bytes(b"x" * 80)
            (shot_dir / "b.jpg").write_bytes(b"y" * 80)
            zip_paths = CORE.pack_output(md_path, [shot_dir], "batch", max_bytes=100)
            self.assertEqual(len(zip_paths), 2)
            for zp in zip_paths:
                with zipfile.ZipFile(zp) as zf:
                    self.assertIn("batch/汇总.md", zf.namelist())

    def test_collect_shot_dirs_ignores_nested_pdf_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "sample" / "批注截图"
            nested.mkdir(parents=True)
            (nested / "old.jpg").write_bytes(b"x")
            self.assertEqual(CORE.collect_shot_dirs(root), [])
            unified = root / "批注截图"
            unified.mkdir()
            self.assertEqual(CORE.collect_shot_dirs(root), [unified])


class ShortPrefixTest(unittest.TestCase):
    def test_extracts_catalog_number(self):
        self.assertEqual(
            CORE.short_prefix("H-020-000617-00_IFU.pdf"),
            "H-020-000617-00",
        )

    def test_falls_back_to_stem(self):
        self.assertEqual(CORE.short_prefix("sample.pdf"), "sample")
        self.assertEqual(
            CORE.short_prefix("very-long-filename-without-catalog-number.pdf"),
            "very-long-filename-without-catalog-number",
        )

    def test_allocate_prefix_adds_suffix_on_collision(self):
        used = set()
        self.assertEqual(CORE.allocate_prefix("note.pdf", used), "note")
        self.assertEqual(CORE.allocate_prefix("note.pdf", used), "note_2")
        self.assertEqual(CORE.allocate_prefix("note.pdf", used), "note_3")

    def test_extract_all_writes_unified_shot_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "内部审核意见汇总1026"
            root.mkdir()
            doc, page, _body = build_sample_page()
            annot = page.add_rect_annot(fitz.Rect(72, 96, 250, 110))
            annot.set_info(content="多余了一条线")
            pdf_path = root / "H-020-000617-00_IFU.pdf"
            doc.save(str(pdf_path))
            doc.close()
            rows, errors = CORE.extract_all(root)
            self.assertEqual(errors, [])
            self.assertTrue(rows)
            self.assertEqual(rows[0]["shot"], "批注截图/H-020-000617-00_p1_ann1.jpg")
            self.assertTrue((root / "批注截图" / "H-020-000617-00_p1_ann1.jpg").is_file())
            self.assertFalse((pdf_path.with_suffix("") / "批注截图").exists())

    def test_extract_all_disambiguates_same_stem(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("sub1", "sub2"):
                folder = root / name
                folder.mkdir()
                doc, page, _body = build_sample_page()
                annot = page.add_rect_annot(fitz.Rect(72, 96, 250, 110))
                annot.set_info(content="多余了一条线")
                doc.save(str(folder / "note.pdf"))
                doc.close()
            rows, errors = CORE.extract_all(root)
            self.assertEqual(errors, [])
            shots = sorted(row["shot"] for row in rows)
            self.assertEqual(shots, [
                "批注截图/note_2_p1_ann1.jpg",
                "批注截图/note_p1_ann1.jpg",
            ])
            self.assertTrue((root / "批注截图" / "note_p1_ann1.jpg").is_file())
            self.assertTrue((root / "批注截图" / "note_2_p1_ann1.jpg").is_file())


if __name__ == "__main__":
    unittest.main()
