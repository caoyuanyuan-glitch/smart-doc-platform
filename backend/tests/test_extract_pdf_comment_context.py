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

        self.assertIn("DNA nanoballs", context.replace(CORE.CARET_MARK, ""))
        self.assertNotIn("1.2 Principle", context)
        self.assertIn(CORE.CARET_MARK, context)


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
        self.assertIn("### 框选还原", text)
        self.assertIn("### 定位原文", text)
        self.assertIn("## 分类索引", text)
        self.assertIn("文档号:", text)
        self.assertNotIn("批注矩形", text)
        self.assertIn("批注截图: 批注截图/p35_ann1.jpg", text)
        self.assertIn("![批注截图](批注截图/p35_ann1.jpg)", text)
        self.assertIn("（空——批注覆盖在图上/线框区域，无文本层）", text)
        self.assertIn("【9.2 试剂盒暂存】", text)
        self.assertNotIn("知识库整理", text)
        self.assertNotIn("### 改什么", text)
        self.assertNotIn("**【如试剂盒已经融化，但不能按时使用，最多可再冻融一次。】**", text)

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
            self.assertNotIn("批注矩形:", text)
            self.assertIn("### 框选还原", text)
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

    def test_textual_comment_empty_box_writes_shot(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc, page, _body = build_sample_page()
            annot = page.add_rect_annot(fitz.Rect(20, 98, 38, 114))
            annot.set_info(content="中英文不一致")
            pdf_path = Path(tmp) / "sample.pdf"
            doc.save(str(pdf_path))
            doc.close()
            rows = CORE.extract_pdf(pdf_path, pdf_path.parent)
            self.assertFalse((rows[0]["selected"] or "").strip())
            self.assertTrue(rows[0]["shot"].endswith(".jpg"))
            text = CORE.to_markdown(rows)
            self.assertNotIn("**【This kit", text)

    def test_empty_box_writes_shot_file_and_markdown_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc, page, _body = build_sample_page()
            annot = page.add_rect_annot(fitz.Rect(20, 98, 38, 114))
            annot.set_info(content="当")
            pdf_path = Path(tmp) / "sample.pdf"
            doc.save(str(pdf_path))
            doc.close()
            rows = CORE.extract_pdf(pdf_path, pdf_path.parent)
            self.assertTrue(rows)
            self.assertFalse((rows[0]["selected"] or "").strip())
            self.assertTrue(rows[0]["shot"].endswith(".jpg"))
            shot_path = pdf_path.parent / "批注截图" / Path(rows[0]["shot"]).name
            self.assertTrue(shot_path.is_file())
            self.assertGreater(shot_path.stat().st_size, 0)
            text = CORE.to_markdown(rows)
            self.assertIn("![批注截图](", text)
            html = CORE.to_html(rows, search_dirs=[pdf_path.parent])
            self.assertIn("<img src=", html)


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
        self.assertTrue(CORE.is_visual_annot(None, None, "", "中英文不一致"))
        self.assertFalse(CORE.is_visual_annot(None, None, "Sequencing", "中英文不一致"))
        self.assertFalse(CORE.is_visual_annot(None, None, "predication", "拼写错误，应该是：prediction"))
        self.assertFalse(CORE.is_visual_annot(None, None, "The", "缺定冠词the"))
        self.assertFalse(CORE.is_visual_annot(None, None, "device", "建议改为product"))

    def test_visual_keyword_beats_textual(self):
        self.assertTrue(CORE.is_visual_annot(None, None, "", "图中文字不对"))

    def test_empty_selected_always_needs_screenshot(self):
        self.assertTrue(CORE.needs_screenshot(None, None, "", "当"))
        self.assertTrue(CORE.needs_screenshot(None, None, "", "中英文不一致"))
        self.assertTrue(CORE.needs_screenshot(None, None, "   ", "拼写错误"))
        self.assertFalse(CORE.needs_screenshot(None, None, "Sequencing", "中英文不一致"))


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
            self.assertEqual(zip_paths[0].name, "汇总.zip")
            with zipfile.ZipFile(zip_paths[0]) as zf:
                names = set(zf.namelist())
            self.assertIn("内部审核意见汇总1026/汇总.md", names)
            self.assertIn("内部审核意见汇总1026/批注截图/p1_ann1.jpg", names)

    def test_pack_output_includes_html_excludes_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            md_path = root / "汇总.md"
            md_path.write_text("# demo\n", encoding="utf-8")
            (root / "汇总.html").write_text("<html>demo</html>", encoding="utf-8")
            (root / "汇总.json").write_text("[]", encoding="utf-8")
            (root / "review_comments.jsonl").write_text("{}\n", encoding="utf-8")
            shot_dir = root / "批注截图"
            shot_dir.mkdir()
            (shot_dir / "H-020-000618-00_p10_ann6.jpg").write_bytes(b"\xff\xd8\xff")
            zip_paths = CORE.pack_output(md_path, [shot_dir], "内部审核意见汇总1026")
            self.assertEqual(len(zip_paths), 1)
            with zipfile.ZipFile(zip_paths[0]) as zf:
                names = set(zf.namelist())
            self.assertEqual(names, {
                "内部审核意见汇总1026/汇总.md",
                "内部审核意见汇总1026/汇总.html",
                "内部审核意见汇总1026/批注截图/H-020-000618-00_p10_ann6.jpg",
            })

    def test_pack_output_without_shots_still_zips_docs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            md_path = root / "汇总.md"
            md_path.write_text("# demo\n", encoding="utf-8")
            (root / "汇总.html").write_text("<html>demo</html>", encoding="utf-8")
            zip_paths = CORE.pack_output(md_path, [], "batch")
            self.assertEqual(len(zip_paths), 1)
            with zipfile.ZipFile(zip_paths[0]) as zf:
                names = set(zf.namelist())
            self.assertEqual(names, {"batch/汇总.md", "batch/汇总.html"})

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
            self.assertEqual(zip_paths[0].name, "汇总.part1.zip")
            self.assertEqual(zip_paths[1].name, "汇总.part2.zip")

    def test_pack_output_keeps_many_shots_when_html_already_over_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            md_path = root / "汇总.md"
            md_path.write_text("# demo\n", encoding="utf-8")
            (root / "汇总.html").write_bytes(b"h" * 800)
            shot_dir = root / "批注截图"
            shot_dir.mkdir()
            for i in range(6):
                (shot_dir / f"a{i}.jpg").write_bytes(b"x" * 40)
            zip_paths = CORE.pack_output(md_path, [shot_dir], "batch", max_bytes=500)
            self.assertEqual(len(zip_paths), 1)
            with zipfile.ZipFile(zip_paths[0]) as zf:
                jpgs = [name for name in zf.namelist() if name.endswith(".jpg")]
            self.assertEqual(len(jpgs), 6)

    def test_pack_output_fills_volumes_instead_of_one_image_each(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            md_path = root / "汇总.md"
            md_path.write_text("# demo\n", encoding="utf-8")
            shot_dir = root / "批注截图"
            shot_dir.mkdir()
            for i in range(5):
                (shot_dir / f"a{i}.jpg").write_bytes(b"x" * 40)
            zip_paths = CORE.pack_output(md_path, [shot_dir], "batch", max_bytes=100)
            self.assertEqual(len(zip_paths), 3)
            counts = []
            for zp in zip_paths:
                with zipfile.ZipFile(zp) as zf:
                    counts.append(sum(1 for name in zf.namelist() if name.endswith(".jpg")))
            self.assertEqual(counts, [2, 2, 1])

    def test_pack_output_replaces_old_part_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            md_path = root / "汇总.md"
            md_path.write_text("# demo\n", encoding="utf-8")
            stale = []
            for i in range(1, 6):
                path = root / f"汇总.part{i}.zip"
                path.write_bytes(b"old")
                stale.append(path)
            zip_paths = CORE.pack_output(md_path, [], "batch")
            self.assertEqual(len(zip_paths), 1)
            self.assertEqual(zip_paths[0].name, "汇总.zip")
            for path in stale:
                self.assertFalse(path.exists())

    def test_to_html_contains_comment_and_named_shot(self):
        html = CORE.to_html([{
            "file": "demo.pdf",
            "page": 2,
            "type": "Highlight",
            "author": "A",
            "comment": "列宽不对",
            "selected": "RCA",
            "heading": "",
            "sentence": "This kit uses RCA",
            "context": "This kit uses RCA",
            "shot": "批注截图/H-020-000617-00_p2_ann1.jpg",
        }])
        self.assertIn("列宽不对", html)
        self.assertIn('src="批注截图/H-020-000617-00_p2_ann1.jpg"', html)
        self.assertIn("<mark>【RCA】</mark>", html)
        self.assertIn("框选还原", html)
        self.assertIn("建议分类", html)

    def test_to_html_embeds_local_shot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shot_dir = root / "批注截图"
            shot_dir.mkdir()
            jpg = shot_dir / "p1_ann1.jpg"
            jpg.write_bytes(b"\xff\xd8\xff\xd9")
            html = CORE.to_html([{
                "file": "demo.pdf",
                "page": 1,
                "type": "Highlight",
                "author": "A",
                "comment": "列宽不对",
                "selected": "RCA",
                "heading": "",
                "sentence": "This kit uses RCA",
                "context": "This kit uses RCA",
                "shot": "批注截图/p1_ann1.jpg",
            }], search_dirs=[root])
            self.assertIn('src="批注截图/p1_ann1.jpg"', html)
            self.assertNotIn("data:image/jpeg;base64,", html)
            self.assertIn('alt="批注截图"', html)

    def test_html_marks_sentence_when_selected_empty(self):
        html = CORE.to_html([{
            "file": "demo.pdf",
            "page": 35,
            "type": "Square",
            "author": "caoyuanyuan",
            "comment": "错别字",
            "selected": "",
            "heading": "9.2 试剂盒暂存",
            "sentence": "如试剂盒已经融化，但不能按时使用，最多可再冻融一次。",
            "context": "如试剂盒已经融化，但不能按时使用，最多可再冻融一次。",
            "shot": "",
        }])
        self.assertNotIn("<mark>", html)
        self.assertIn("如试剂盒已经融化，但不能按时使用，最多可再冻融一次。", html)
        self.assertNotIn("批注矩形", html)

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


class ExpandSelectedTest(unittest.TestCase):
    def test_expands_cjk_fragment_to_phrase(self):
        self.assertEqual(
            CORE.expand_selected("部储存设", "用于连接扫码枪或外部储存设备。"),
            "外部储存设备",
        )

    def test_expands_english_midword_fragment(self):
        self.assertEqual(CORE.expand_selected("p Colo", "Cap Color"), "Cap Color")

    def test_keeps_complete_term(self):
        self.assertEqual(
            CORE.expand_selected("RCA", "This kit uses RCA to obtain DNA nanoballs."),
            "RCA",
        )

    def test_empty_stays_empty(self):
        self.assertEqual(CORE.expand_selected("", "原文"), "")

    def test_expands_wrapped_hyphen_phrase(self):
        sentence = "the system automatically applies reference-based compression leveraging reference."
        self.assertEqual(
            CORE.expand_selected("based compression", sentence),
            "reference-based compression",
        )

    def test_expands_linewrapped_hyphen_phrase(self):
        sentence = "the system automatically applies reference-\nbased compression leveraging reference."
        self.assertEqual(
            CORE.expand_selected("based compression", sentence),
            "reference-based compression",
        )

    def test_does_not_append_next_line_word_to_path(self):
        sentence = "genome files (defaults to /opt/zarc/\nreference genome files)"
        self.assertEqual(CORE.expand_selected("/opt/zarc/", sentence), "/opt/zarc/")

    def test_join_wrapped_hits_keeps_path_without_next_word(self):
        text = CORE.join_wrapped_hits([
            {"hit": "/opt/zarc/", "at_eol": True, "at_sol": False, "y0": 10},
            {"hit": "reference", "at_eol": False, "at_sol": True, "y0": 24},
        ])
        self.assertEqual(text, "/opt/zarc/")

    def test_join_wrapped_hits_joins_hyphen_phrase(self):
        text = CORE.join_wrapped_hits([
            {"hit": "reference-based", "at_eol": True, "at_sol": False, "y0": 10},
            {"hit": "compression", "at_eol": False, "at_sol": True, "y0": 24},
        ])
        self.assertEqual(text, "reference-based compression")

    def test_join_wrapped_hits_keeps_full_next_heading_line(self):
        text = CORE.join_wrapped_hits([
            {
                "hit": "Default Reference Genome & Compression",
                "full": "7. Default Reference Genome & Compression",
                "at_eol": True,
                "at_sol": False,
                "y0": 10,
            },
            {
                "hit": "Mode Auto-Detection:",
                "full": "Mode Auto-Detection:",
                "at_eol": True,
                "at_sol": True,
                "y0": 24,
            },
        ])
        self.assertEqual(text, "Default Reference Genome & Compression Mode Auto-Detection:")


class GuessCategoryTest(unittest.TestCase):
    def test_layout_and_typo(self):
        self.assertEqual(CORE.guess_category("调整列宽，让最后一列有更多空间"), "排版/布局/样式")
        self.assertEqual(CORE.guess_category("登录，不是登陆"), "术语统一/用词")
        self.assertEqual(CORE.guess_category("逗号前面多了一个空格"), "空格/标点/格式")
        self.assertEqual(CORE.guess_category("确认下是不是3.0"), "内容确认/疑问")

    def test_catalog_number(self):
        self.assertEqual(
            CORE.catalog_number("H-020-000396-00 DNBSEQ-E25RS.pdf"),
            "H-020-000396-00",
        )
        self.assertEqual(CORE.catalog_number("CSS-00065 User Manual.pdf"), "CSS-00065")


class CalloutAnnotTest(unittest.TestCase):
    def _tips_page(self):
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 80), "2. Replace the license file:", fontsize=12)
        page.insert_textbox(
            fitz.Rect(72, 96, 520, 150),
            "Copy the received file to the folder under the ZARC installation directory.",
            fontsize=11,
        )
        page.insert_text((72, 180), "Tips", fontsize=13)
        page.insert_textbox(
            fitz.Rect(72, 198, 520, 280),
            "Official licenses are available for authorization based on either compressed data throughput.",
            fontsize=11,
        )
        return doc, page

    def test_square_on_tips_marks_label_and_keeps_body(self):
        doc, page = self._tips_page()
        annot = page.add_rect_annot(fitz.Rect(70, 176, 110, 196))
        annot.set_info(content='中文是"注意"')
        view = CORE.extract_comment_view(page, annot)
        doc.close()
        self.assertEqual(view["selected"], "Tips")
        self.assertIn("Official licenses", view["context"])
        self.assertIn("Replace the license", view["context"] + " " + (view["heading"] or ""))
        text = CORE.to_markdown([{
            "file": "demo.pdf",
            "page": 3,
            "type": "Square",
            "author": "A",
            "comment": '中文是"注意"',
            "selected": view["selected"],
            "heading": view["heading"],
            "sentence": view["sentence"],
            "context": view["context"],
            "shot": "批注截图/x.jpg",
        }])
        self.assertIn("**【Tips】**", text)

    def test_square_on_tips_body_uses_note_label(self):
        doc, page = self._tips_page()
        annot = page.add_rect_annot(fitz.Rect(80, 200, 400, 230))
        annot.set_info(content='中文是"注意"')
        view = CORE.extract_comment_view(page, annot)
        doc.close()
        self.assertEqual(view["selected"], "Tips")
        self.assertIn("Official licenses", view["context"])
        text = CORE.to_markdown([{
            "file": "demo.pdf",
            "page": 3,
            "type": "Square",
            "author": "A",
            "comment": '中文是"注意"',
            "selected": view["selected"],
            "heading": view["heading"],
            "sentence": view["sentence"],
            "context": view["context"],
            "shot": "",
        }])
        self.assertIn("**【Tips】**", text)

    def test_callout_label_writes_shot(self):
        self.assertTrue(CORE.is_visual_annot(None, None, "Tips", '中文是"注意"'))

    def test_shot_includes_callout_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc, page = self._tips_page()
            annot = page.add_rect_annot(fitz.Rect(70, 176, 110, 196))
            annot.set_info(content='中文是"注意"')
            pdf_path = Path(tmp) / "sample.pdf"
            doc.save(str(pdf_path))
            doc.close()
            rows = CORE.extract_pdf(pdf_path, pdf_path.parent)
            self.assertTrue(rows)
            self.assertTrue(rows[0]["shot"].endswith(".jpg"))
            shot_path = pdf_path.parent / "批注截图" / Path(rows[0]["shot"]).name
            pix = fitz.Pixmap(str(shot_path))
            self.assertGreaterEqual(pix.height, 300)
            self.assertGreaterEqual(pix.width, 400)

    def test_empty_square_beside_word_stays_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = fitz.open()
            page = doc.new_page(width=595, height=842)
            page.insert_text((72, 80), "9.1 DNB浓度不合格", fontsize=14)
            page.insert_text((72, 120), "DNB浓度不符合第12页测定DNB浓度的要求时，执行如下操作：", fontsize=11)
            annot = page.add_rect_annot(fitz.Rect(48, 108, 66, 126))
            annot.set_info(content="当")
            pdf_path = Path(tmp) / "sample.pdf"
            doc.save(str(pdf_path))
            view = CORE.extract_comment_view(page, annot)
            doc.close()
            self.assertFalse((view["selected"] or "").strip())
            marked = CORE.format_original({
                "selected": view["selected"],
                "heading": view["heading"],
                "sentence": view["sentence"],
                "context": view["context"],
                "anchor_left": view.get("anchor_left") or "",
                "anchor_right": view.get("anchor_right") or "",
            })
            self.assertNotIn("**【DNB】**", marked)
            rows = CORE.extract_pdf(pdf_path, pdf_path.parent)
            self.assertTrue(rows)
            self.assertFalse((rows[0]["selected"] or "").strip())
            self.assertTrue(rows[0]["shot"].endswith(".jpg"))


class MarkSnippetTest(unittest.TestCase):
    def test_marks_preferred_sentence_not_first_hit(self):
        block = "zarc\nconfig/\nYou can then use the zarc command from any"
        marked = CORE.mark_snippet(block, "zarc", prefer="You can then use the zarc command from any")
        self.assertEqual(marked.count("**【zarc】**"), 1)
        self.assertIn("use the **【zarc】** command", marked)
        self.assertTrue(marked.startswith("zarc"))


    def test_marks_wrapped_heading(self):
        block = "7. Default Reference Genome & Compression\nMode Auto-Detection:"
        selected = "Default Reference Genome & Compression Mode Auto-Detection:"
        marked = CORE.mark_snippet(block, selected)
        self.assertIn("**【", marked)
        self.assertIn("Mode Auto-Detection:", marked)
        self.assertIn("&", marked)

    def test_keeps_ampersand_span(self):
        self.assertFalse(CORE.is_junk_span({"text": "&", "font": "Symbol"}))

    def test_keeps_times_symbol_span(self):
        self.assertFalse(CORE.is_junk_span({"text": "×", "font": "Symbol"}))

    def test_marks_times_symbol_across_wrap(self):
        block = "ZARC achieves up to 5 higher compression\nratios, while fully preserving"
        marked = CORE.mark_snippet(block, "up to 5× higher compression ratios")
        self.assertIn("**【", marked)
        self.assertIn("ratios", marked)
        self.assertRegex(marked, r"up to 5.*higher compression")


    def test_marks_anchored_occurrence_not_first(self):
        block = "The flow cell ID is ABC.\nWARNING: Keep the flow rate below 10."
        marked = CORE.mark_snippet(block, "flow", left="the ", right=" rate")
        self.assertIn("the **【flow】** rate", marked)
        self.assertNotIn("The **【flow】** cell", marked)

    def test_prefer_yields_to_anchors(self):
        block = "The flow cell ID is ABC.\nWARNING: Keep the flow rate below 10."
        prefer = "The flow cell ID is ABC."
        marked = CORE.mark_snippet(block, "flow", prefer=prefer, left="the ", right=" rate")
        self.assertIn("the **【flow】** rate", marked)
        self.assertNotIn("The **【flow】** cell", marked)


class CaretAnnotTest(unittest.TestCase):
    def test_caret_marks_insert_point_and_writes_shot(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = fitz.open()
            page = doc.new_page(width=595, height=842)
            page.insert_text((72, 120), "file structure,", fontsize=11)
            page.insert_text((72, 136), "ensuring data security.", fontsize=11)
            annot = page.add_caret_annot(fitz.Point(72, 136))
            annot.set_info(content="and")
            pdf_path = Path(tmp) / "sample.pdf"
            doc.save(str(pdf_path))
            doc.close()
            rows = CORE.extract_pdf(pdf_path, pdf_path.parent)
            self.assertTrue(rows)
            self.assertIn(CORE.CARET_MARK, rows[0]["selected"] + rows[0]["sentence"] + rows[0]["context"])
            self.assertTrue(rows[0]["shot"].endswith(".jpg"))
            self.assertIn("ensuring data security", rows[0]["sentence"] or rows[0]["context"])
            blob = rows[0]["selected"] + rows[0]["sentence"] + rows[0]["context"]
            self.assertNotIn("e" + CORE.CARET_MARK + "n", blob)
            self.assertIn(CORE.CARET_MARK + "ensuring", blob)
            text = CORE.to_markdown(rows)
            self.assertIn(CORE.CARET_MARK, text)
            self.assertIn("![批注截图](", text)
            html = CORE.to_html(rows)
            self.assertIn("<img src=", html)
            self.assertIn("插入点截图", html)

    def test_caret_is_visual(self):
        doc = fitz.open()
        page = doc.new_page()
        annot = page.add_caret_annot(fitz.Point(72, 72))
        annot.set_info(content="and")
        self.assertTrue(CORE.is_visual_annot(page, annot, "ensuring data security.", "and"))
        self.assertTrue(CORE.is_visual_annot(None, None, "", "插入 and"))
        doc.close()


def _page_text_rect(page, needle, occurrence=0):
    payload = page.get_text("rawdict")
    chars = []
    for block in payload.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                for char in span.get("chars") or []:
                    glyph = char.get("c") or ""
                    box = char.get("bbox")
                    if glyph and box:
                        chars.append((glyph, fitz.Rect(box)))
    blob = "".join(item[0] for item in chars)
    at = -1
    start = 0
    for _ in range(occurrence + 1):
        at = blob.find(needle, start)
        if at < 0:
            raise AssertionError(f"missing {needle!r} occurrence {occurrence} in {blob!r}")
        start = at + 1
    rect = chars[at][1]
    for glyph, box in chars[at + 1:at + len(needle)]:
        rect |= box
    return rect


class SmallSquareHighlightTest(unittest.TestCase):
    def test_small_square_keeps_boxed_word(self):
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        line = "2) Based on the specific library adapter type, thaw Make DNB Buffer (OS-V2.0-"
        page.insert_text((72, 120), line, fontsize=11)
        annot = page.add_rect_annot(_page_text_rect(page, "thaw") + (-0.4, -0.4, 0.4, 0.4))
        annot.set_info(content="take out and")
        view = CORE.extract_comment_view(page, annot)
        doc.close()
        self.assertEqual(view["selected"].strip(), "thaw")
        marked = CORE.format_original({
            "selected": view["selected"],
            "heading": view["heading"],
            "sentence": view["sentence"],
            "context": view["context"],
        })
        self.assertIn("**【thaw】**", marked)
        self.assertNotIn("**【2) Based", marked)

    def test_short_highlight_is_marked_in_original(self):
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 120), "User Manual Rev B 20260703", fontsize=11)
        annot = page.add_highlight_annot(_page_text_rect(page, "B"))
        annot.set_info(content="确认下是不是3.0")
        view = CORE.extract_comment_view(page, annot)
        marked = CORE.format_original({
            "selected": view["selected"],
            "heading": view["heading"],
            "sentence": view["sentence"],
            "context": view["context"],
            "anchor_left": view.get("anchor_left") or "",
            "anchor_right": view.get("anchor_right") or "",
        })
        doc.close()
        self.assertEqual(view["selected"].strip(), "B")
        self.assertIn("**【B】**", marked)

    def test_short_square_letter_is_marked_in_original(self):
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 120), "User Manual Rev B 20260703", fontsize=11)
        annot = page.add_rect_annot(_page_text_rect(page, "B") + (-0.4, -0.4, 0.4, 0.4))
        annot.set_info(content="确认下是不是3.0")
        view = CORE.extract_comment_view(page, annot)
        marked = CORE.format_original({
            "selected": view["selected"],
            "heading": view["heading"],
            "sentence": view["sentence"],
            "context": view["context"],
            "anchor_left": view.get("anchor_left") or "",
            "anchor_right": view.get("anchor_right") or "",
        })
        doc.close()
        self.assertEqual(view["selected"].strip(), "B")
        self.assertIn("**【B】**", marked)

    def test_format_original_always_marks_boxed_text(self):
        marked = CORE.format_original({
            "selected": "ID",
            "heading": "",
            "sentence": "Keep the flow rate below 10.",
            "context": "Keep the flow rate below 10.",
        })
        self.assertIn("**【ID】**", marked)

    def test_textual_square_keeps_short_word_and_marks(self):
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 120), "Flow cell ID is ABC.", fontsize=11)
        annot = page.add_rect_annot(_page_text_rect(page, "ID") + (-0.4, -0.4, 0.4, 0.4))
        annot.set_info(content="中英文不一致")
        view = CORE.extract_comment_view(page, annot)
        marked = CORE.format_original({
            "selected": view["selected"],
            "heading": view["heading"],
            "sentence": view["sentence"],
            "context": view["context"],
            "anchor_left": view.get("anchor_left") or "",
            "anchor_right": view.get("anchor_right") or "",
        })
        doc.close()
        self.assertEqual(view["selected"].strip(), "ID")
        self.assertIn("**【ID】**", marked)
        self.assertFalse(CORE.needs_screenshot(
            None, None, view["selected"], "中英文不一致", view.get("context")
        ))

    def test_html_marks_inner_brackets(self):
        html = CORE.to_html([{
            "file": "demo.pdf",
            "page": 60,
            "type": "Square",
            "author": "A",
            "comment": "确认下这个状态是否正确",
            "selected": "进行中",
            "heading": "",
            "sentence": "1. 在【实验室管理】模块首页的状态显示区，点击【进行中】，进入任务管理界面。",
            "context": "1. 在【实验室管理】模块首页的状态显示区，点击【进行中】，进入任务管理界面。",
            "shot": "",
        }])
        self.assertIn("<mark>【进行中】</mark>", html)
        self.assertNotIn("**【", html)

    def test_html_marks_sentence_containing_brackets(self):
        sel = "1. 在【实验室管理】模块首页的状态显示区，点击【进行中】，进入任务管理界面。"
        html = CORE.to_html([{
            "file": "demo.pdf",
            "page": 60,
            "type": "Square",
            "author": "A",
            "comment": "确认下这个状态是否正确",
            "selected": sel,
            "heading": "",
            "sentence": sel,
            "context": sel,
            "shot": "",
        }])
        self.assertIn("<mark>", html)
        self.assertNotIn("**【", html)
        self.assertIn("进行中", html)

    def test_empty_square_on_blank_writes_shot_without_number_mark(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = fitz.open()
            page = doc.new_page(width=595, height=842)
            page.insert_text((72, 80), "9", fontsize=11)
            page.insert_text((72, 400), "Figure caption stays far away.", fontsize=11)
            annot = page.add_rect_annot(fitz.Rect(200, 200, 280, 260))
            annot.set_info(content="这是前翻门吗？")
            pdf_path = Path(tmp) / "sample.pdf"
            doc.save(str(pdf_path))
            doc.close()
            rows = CORE.extract_pdf(pdf_path, pdf_path.parent)
            self.assertTrue(rows)
            self.assertFalse((rows[0]["selected"] or "").strip())
            self.assertTrue(rows[0]["shot"].endswith(".jpg"))
            text = CORE.to_markdown(rows)
            self.assertNotIn("**【9】**", text)
            html = CORE.to_html(rows)
            self.assertNotIn("<mark>【9】</mark>", html)


class AnchorAndThinContextTest(unittest.TestCase):
    def test_pdf_marks_boxed_flow_not_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = fitz.open()
            page = doc.new_page(width=595, height=842)
            page.insert_text((72, 120), "The flow cell ID is ABC.", fontsize=11)
            page.insert_text((72, 200), "WARNING", fontsize=12)
            page.insert_text((72, 220), "Keep the flow rate below 10.", fontsize=11)
            annot = page.add_rect_annot(_page_text_rect(page, "flow", 1) + (-0.4, -0.4, 0.4, 0.4))
            annot.set_info(content="the")
            pdf_path = Path(tmp) / "sample.pdf"
            doc.save(str(pdf_path))
            doc.close()
            rows = CORE.extract_pdf(pdf_path, pdf_path.parent)
            self.assertTrue(rows)
            self.assertEqual(rows[0]["selected"].strip(), "flow")
            marked = CORE.format_original(rows[0])
            self.assertIn("the **【flow】** rate", marked)
            self.assertNotIn("The **【flow】** cell", marked)

    def test_thin_fragment_is_visual(self):
        self.assertTrue(CORE.is_visual_annot(None, None, "臂（选", "上面没有写（选配）", "臂（选"))
        self.assertTrue(CORE.is_visual_annot(None, None, "器控制软", "上面没这2个字", "器控制软"))
        self.assertFalse(CORE.is_visual_annot(None, None, "The", "缺定冠词the", "The flow cell ID is ABC."))

    def test_table_wrap_writes_shot(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = fitz.open()
            page = doc.new_page(width=595, height=842)
            page.insert_text((72, 120), "grip", fontsize=11)
            page.insert_text((72, 136), "arm (", fontsize=11)
            page.insert_text((72, 152), "ional)", fontsize=11)
            annot = page.add_rect_annot(_page_text_rect(page, "arm (") + (-0.4, -0.4, 0.4, 0.4))
            annot.set_info(content="上面没有写（选配）")
            pdf_path = Path(tmp) / "sample.pdf"
            doc.save(str(pdf_path))
            doc.close()
            rows = CORE.extract_pdf(pdf_path, pdf_path.parent)
            self.assertTrue(rows)
            self.assertTrue(rows[0]["shot"].endswith(".jpg"))


    def test_caret_stays_in_same_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = fitz.open()
            page = doc.new_page(width=595, height=842)
            page.insert_text((72, 220), "ensuring data security.", fontsize=11)
            page.insert_text((360, 220), "Other Linux distributions", fontsize=11)
            annot = page.add_caret_annot(fitz.Point(72, 220))
            annot.set_info(content="and")
            pdf_path = Path(tmp) / "sample.pdf"
            doc.save(str(pdf_path))
            doc.close()
            rows = CORE.extract_pdf(pdf_path, pdf_path.parent)
            self.assertTrue(rows)
            marked = CORE.format_original(rows[0])
            self.assertIn("ensuring data security", rows[0]["sentence"])
            self.assertNotIn("Other Linux", rows[0]["sentence"])
            self.assertIn(CORE.CARET_MARK, marked)
            self.assertIn("ensuring", marked)
            self.assertNotIn(CORE.CARET_MARK + "Other", marked.replace(" ", ""))

    def test_caret_mid_line_not_neighbor_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = fitz.open()
            page = doc.new_page(width=595, height=842)
            page.insert_text((72, 300), "-P: Specify the software installation", fontsize=11)
            page.insert_text((300, 300), "Please contact technical support", fontsize=11)
            rect = _page_text_rect(page, "technical")
            annot = page.add_caret_annot(fitz.Point(rect.x0, (rect.y0 + rect.y1) / 2))
            annot.set_info(content="the")
            pdf_path = Path(tmp) / "sample.pdf"
            doc.save(str(pdf_path))
            doc.close()
            rows = CORE.extract_pdf(pdf_path, pdf_path.parent)
            self.assertTrue(rows)
            sentence = rows[0]["sentence"] or ""
            self.assertIn("technical", sentence)
            self.assertIn("contact", sentence)
            self.assertNotIn("Specify the software", sentence)
            self.assertIn(CORE.CARET_MARK, CORE.format_original(rows[0]))


if __name__ == "__main__":
    unittest.main()
