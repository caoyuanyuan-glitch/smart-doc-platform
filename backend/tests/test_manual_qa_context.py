import unittest
from pathlib import Path

from app.api.manual_search import (
    _build_page_images,
    _combine_per_manual_answers,
    _expand_ranked_with_neighbors,
    _has_numbered_steps,
    _heading_match_boost,
    _heading_page_refs,
    _looks_like_toc,
    _needs_earlier_steps,
    _order_context_sources,
    _page_refs_in_text,
    _question_topic,
    _rank_page_chunks,
    _render_page_jpeg,
    _session_title,
    _topic_in_text,
)


class ManualQaContextTest(unittest.TestCase):
    def test_detects_skip_summary(self):
        summary = "根据步骤1-6准备SE测序试剂槽；根据步骤1-7准备PE测序试剂槽。"
        self.assertTrue(_needs_earlier_steps(summary))
        self.assertFalse(_has_numbered_steps(summary))

    def test_detects_detailed_steps(self):
        detail = "1. 取出试剂槽\n2. 顺时针摇晃10次\n3. 逆时针摇晃10次\n4. 按压M1孔位"
        self.assertTrue(_has_numbered_steps(detail))
        self.assertFalse(_needs_earlier_steps(detail))

    def test_extracts_page_refs(self):
        self.assertEqual(_page_refs_in_text("请转至第73页，清洗见第128页。"), [73, 128])

    def test_toc_heading_jumps_to_chapter_page(self):
        toc = "安全注意事项 8\n准备测序试剂槽 70\n测序工作流程 90"
        self.assertTrue(_looks_like_toc(toc))
        self.assertEqual(_heading_page_refs(toc, "如何准备测序试剂槽"), [70])
        documents = [{
            "title": "系统操作指南",
            "pages": [
                {"page_num": 8, "text": "目录页 安全注意事项 8 准备测序试剂槽 70 测序工作流程 90"},
                {"page_num": 70, "text": "准备测序试剂槽\n- 取出解冻好的测序试剂槽2&3，使用无尘纸擦净盖板及孔位处的冷凝水。\n- 顺时针摇晃测序试剂槽10次，再逆时针摇晃10次。\n- 使用预混压紧块按压试剂槽M1、M2、M3、M4孔位到底。"},
                {"page_num": 71, "text": "双手握住试剂槽两侧，上下摇晃混匀10次。"},
            ],
        }]
        ranked = [{
            "title": "系统操作指南",
            "chunk": toc,
            "page_num": 8,
            "score": 9.0,
        }]
        expanded = _expand_ranked_with_neighbors(
            ranked, documents, question="如何准备测序试剂槽", limit=16
        )
        pages = {item["page_num"] for item in expanded}
        self.assertIn(70, pages)
        self.assertIn(71, pages)

    def test_rank_prefers_procedure_over_toc(self):
        documents = [{
            "title": "系统操作指南",
            "pages": [
                {"page_num": 8, "text": "安全注意事项 8\n准备测序试剂槽 70\n测序工作流程 90\n维护保养 120"},
                {"page_num": 70, "text": "准备测序试剂槽\n- 取出解冻好的测序试剂槽2&3，使用无尘纸擦净盖板及孔位处的冷凝水。\n- 顺时针摇晃测序试剂槽10次，再逆时针摇晃10次。\n- 使用预混压紧块按压试剂槽M1孔位到底。"},
            ],
        }]
        ranked = _rank_page_chunks("如何准备测序试剂槽", documents, limit=5)
        self.assertEqual(ranked[0]["page_num"], 70)

    def test_question_topic_strips_how_to(self):
        self.assertEqual(_question_topic("如何准备测序试剂槽"), "准备测序试剂槽")
        self.assertGreaterEqual(_heading_match_boost("如何准备测序试剂槽", "准备测序试剂槽\n取出试剂槽"), 12.0)
        self.assertLess(_heading_match_boost("如何准备测序试剂槽", "清洗测序试剂槽\n取出试剂槽"), 8.0)

    def test_rank_prefers_chapter_heading_over_similar_section(self):
        documents = [{
            "title": "系统操作指南",
            "pages": [
                {"page_num": 70, "text": "准备测序试剂槽\n- 取出解冻好的测序试剂槽2&3\n- 顺时针摇晃测序试剂槽10次\n- 按压M1孔位"},
                {"page_num": 128, "text": "清洗测序试剂槽\n1. 取出测序试剂槽\n2. 用纯水清洗试剂槽\n3. 擦干试剂槽\n4. 放回测序试剂槽"},
            ],
        }]
        ranked = _rank_page_chunks("如何准备测序试剂槽", documents, limit=5)
        self.assertEqual(ranked[0]["page_num"], 70)

    def test_rank_prefers_prepare_page_without_isolated_heading(self):
        prepare = (
            "根据步骤1-6准备SE测序试剂槽。\n"
            "根据步骤1-7准备PE测序试剂槽。\n"
            "（可选）如需更换测序引物，请转至第73页。\n"
            "图15 试剂槽孔位\n"
            "操作步骤如下：\n"
            "1. 取出解冻好的测序试剂槽2&3，使用无尘纸擦净盖板及孔位处的冷凝水。\n"
            "2. 顺时针摇晃测序试剂槽10次，再逆时针摇晃10次。\n"
            "3. 使用预混压紧块按压试剂槽M1、M2、M3、M4孔位到底。"
        )
        wash = (
            "使用测序试剂槽进行手动清洗（测序完成后【自动清洗】设置为【否】时）\n"
            "1. 使用洁净的1 mL吸头戳破测序试剂槽3的12号孔位。\n"
            "2. 使用电动移液器移取100 mL的清洗试剂1加入到12号孔位中。\n"
            "3. 点击主界面的【清洗】，系统自动进行清洗前自检。\n"
            "4. 完成后，点击【下一步】。\n"
            "5. 如获取失败，在【测序试剂仓】区域选择【测序试剂槽】。\n"
            "6. 关闭仓门并按压门锁位置以关紧仓门。\n"
            "7. 安装载片后点击【启动】开始清洗。\n"
            "8. 在弹框中点击【是】，升降屏自动降下。\n"
            "使用清洗试剂槽进行维护清洗\n"
            "1. 确保已准备清洗试剂2和清洗试剂3。\n"
            "2. 准备清洗试剂槽：戳破11号孔、12号孔和15号孔位。"
        )
        self.assertTrue(_topic_in_text("准备测序试剂槽", prepare))
        self.assertFalse(_topic_in_text("准备测序试剂槽", wash))
        documents = [{
            "title": "系统操作指南",
            "pages": [
                {"page_num": 70, "text": prepare},
                {"page_num": 128, "text": wash},
            ],
        }]
        ranked = _rank_page_chunks("如何准备测序试剂槽", documents, limit=5)
        self.assertEqual(ranked[0]["page_num"], 70)
        expanded = _expand_ranked_with_neighbors(
            ranked, documents, question="如何准备测序试剂槽", limit=16
        )
        self.assertNotIn(128, {item["page_num"] for item in expanded})

    def test_expands_neighbors_and_earlier_steps(self):
        documents = [{
            "title": "系统操作指南",
            "pages": [
                {"page_num": 10, "text": "1. 从冰箱取出SE测序试剂槽\n2. 平衡至室温\n3. 检查包装\n4. 撕开封膜\n5. 放入仪器\n6. 确认到位"},
                {"page_num": 11, "text": "1. 从冰箱取出PE测序试剂槽\n2. 平衡至室温\n3. 检查包装\n4. 撕开封膜\n5. 放入仪器\n6. 确认到位\n7. 关闭舱门"},
                {"page_num": 40, "text": "根据步骤1-6准备SE测序试剂槽；根据步骤1-7准备PE测序试剂槽。可选操作见第73页。"},
                {"page_num": 41, "text": "取出解冻好的测序试剂槽2&3，使用无尘纸擦净盖板。"},
                {"page_num": 73, "text": "自定义测序引物的更换步骤。"},
            ],
        }]
        ranked = [{
            "title": "系统操作指南",
            "chunk": documents[0]["pages"][2]["text"],
            "page_num": 40,
            "score": 8.0,
        }]
        expanded = _expand_ranked_with_neighbors(
            ranked, documents, question="如何准备测序试剂槽", limit=16
        )
        pages = {item["page_num"] for item in expanded}
        self.assertIn(40, pages)
        self.assertIn(41, pages)
        self.assertIn(73, pages)
        self.assertIn(10, pages)
        self.assertIn(11, pages)
        ordered = _order_context_sources(expanded)
        self.assertEqual([item["page_num"] for item in ordered], sorted(item["page_num"] for item in ordered))

    def _fixture_pdf(self):
        matches = list((Path(__file__).parent / "fixtures" / "seed").glob("*.pdf"))
        return str(matches[0]) if matches else ""

    def test_render_page_jpeg_from_fixture(self):
        path = self._fixture_pdf()
        if not path:
            self.skipTest("no fixture pdf")
        data = _render_page_jpeg(path, 1, scale=1.0, quality=70)
        self.assertTrue(data)
        self.assertEqual(data[:2], b"\xff\xd8")

    def test_build_page_images_from_fixture(self):
        path = self._fixture_pdf()
        if not path:
            self.skipTest("no fixture pdf")
        documents = [{"title": "指南", "file_id": "off_test", "file_path": path}]
        sources = [{"title": "指南", "page": 1, "file_id": "off_test"}]
        images = _build_page_images(documents, sources, limit=1)
        self.assertEqual(len(images), 1)
        self.assertTrue(images[0]["data_url"].startswith("data:image/jpeg;base64,"))
        self.assertEqual(images[0]["page"], 1)
        self.assertEqual(images[0]["file_id"], "off_test")

    def test_session_title_prefixes_product(self):
        self.assertEqual(_session_title("如何准备测序试剂槽", "T7+"), "T7+ 如何准备测序试剂槽")

    def test_session_title_keeps_model_already_in_question(self):
        self.assertEqual(_session_title("T7+ 如何准备测序试剂槽", "T7+"), "T7+ 如何准备测序试剂槽")

    def test_session_title_joins_multiple_models(self):
        self.assertEqual(
            _session_title("如何准备测序试剂槽", "T7+, T1+"),
            "T7+、T1+ 如何准备测序试剂槽",
        )

    def test_combine_keeps_each_manual_section(self):
        docs = [{"title": "T7+ 指南"}, {"title": "T1+ 指南"}, {"title": "G99 指南"}]
        results = [
            {"answer": "T7 步骤", "sources": [{"title": "T7+ 指南", "page": 1}], "source_for_db": [], "search_hit": 1, "relevance_score": 1},
            {"answer": "T1 步骤", "sources": [{"title": "T1+ 指南", "page": 2}], "source_for_db": [], "search_hit": 1, "relevance_score": 2},
            {"answer": "G99 步骤", "sources": [{"title": "G99 指南", "page": 3}], "source_for_db": [], "search_hit": 1, "relevance_score": 3},
        ]
        out = _combine_per_manual_answers(docs, results)
        self.assertIn("## T7+ 指南", out["answer"])
        self.assertIn("## T1+ 指南", out["answer"])
        self.assertIn("## G99 指南", out["answer"])
        self.assertIn("T7 步骤", out["answer"])
        self.assertIn("T1 步骤", out["answer"])
        self.assertIn("G99 步骤", out["answer"])
        self.assertEqual(len(out["titles"]), 3)


if __name__ == "__main__":
    unittest.main()
