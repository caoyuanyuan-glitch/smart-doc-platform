"""竞品分析 v1.1 整改单测：区间制评分 / 样本量三档 / 警告0标注 / 入口页识别 /
HAT 链接反查 / 例句过滤 / 报告 N/A 渲染 / 洞察四分类。

对应 2026-08-24 外部评审（Kimi/claw）意见采纳项与用户四项裁定。
"""

import unittest

from app.utils.competitor_analysis import (
    _band_score,
    _hat_link_hints,
    _looks_like_caption_line,
    analyze_readability,
    analyze_structure,
)
from app.utils.competitor_html import entry_page_hints
from app.utils.competitor_insight import generate_rule_insights
from app.utils.competitor_report import render_competitor_report


def _make_text(n_sentences: int, sentence: str = "The instrument is ready to run. ") -> str:
    """生成指定句数的均衡英文文本（句长约 5-6 词，密度低但非空）。"""
    return sentence * n_sentences


class BandScoreTestCase(unittest.TestCase):
    """区间制评分：理想区间满分，区间外双向扣分，梯度独立。"""

    def test_inside_band_full_score(self):
        self.assertEqual(_band_score(20, 15, 40, 1.0, 1.5), 100.0)
        self.assertEqual(_band_score(15, 15, 40, 1.0, 1.5), 100.0)
        self.assertEqual(_band_score(40, 15, 40, 1.0, 1.5), 100.0)

    def test_above_band_penalized(self):
        self.assertAlmostEqual(_band_score(50, 15, 40, 1.0, 1.5), 85.0)

    def test_below_band_penalized(self):
        self.assertAlmostEqual(_band_score(10, 15, 40, 1.0, 1.5), 95.0)

    def test_k_short_zero_means_no_short_penalty(self):
        """被动句比例 k_short=0：低侧（含 0%）不扣分（用户裁定）。"""
        self.assertEqual(_band_score(0.0, 0.0, 0.10, 0.0, 200.0), 100.0)

    def test_score_clamped_to_zero(self):
        self.assertEqual(_band_score(0, 15, 40, 100.0, 1.0), 0.0)


class SampleTierTestCase(unittest.TestCase):
    """样本量三档：<100 不评分；100-500 评分+标注；>500 正常。"""

    def test_insufficient_rejects_scoring(self):
        result = analyze_readability(_make_text(50), [_make_text(50)])
        self.assertEqual(result["sample_status"], "insufficient")
        self.assertIsNone(result["overall_score"])
        self.assertEqual(result["level"], "insufficient")
        for dim in result["dimensions"].values():
            self.assertIsNone(dim.get("score"), "样本不足时维度分应置 None")
        self.assertTrue(any("样本" in w for w in result["warnings"]))

    def test_limited_scores_with_flag(self):
        text = _make_text(120)
        result = analyze_readability(text, [text])
        self.assertEqual(result["sample_status"], "limited")
        self.assertIsNotNone(result["overall_score"])
        self.assertTrue(any("样本量有限" in w for w in result["warnings"]))

    def test_sufficient_no_flag(self):
        text = _make_text(520)
        result = analyze_readability(text, [text])
        self.assertEqual(result["sample_status"], "sufficient")
        self.assertIsNotNone(result["overall_score"])
        self.assertFalse(any("样本" in w for w in result["warnings"]))


class PassiveZeroNotPenalizedTestCase(unittest.TestCase):
    """被动句 0% 不扣分（用户裁定：被动少不是问题）。"""

    def test_zero_passive_full_score(self):
        text = _make_text(120)  # 全主动句
        result = analyze_readability(text, [text])
        self.assertEqual(result["dimensions"]["passive_ratio"]["score"], 100.0)


class WarningZeroAnnotationTestCase(unittest.TestCase):
    """安全警告 0 标注 + unicode 符号统计。"""

    def test_zero_warning_annotated(self):
        stats = analyze_structure("sample.txt", "No warnings here at all.", ["page"])
        self.assertEqual(stats["warning_count"], 0)
        self.assertTrue(any("人工复核" in n for n in stats["notes"]))

    def test_warning_symbols_counted(self):
        text = "Step 1. ⚠ Do not open the cover. Step 2. ⚠ Power off first."
        stats = analyze_structure("sample.txt", text, [text])
        self.assertEqual(stats["warning_count"], 0)  # 行首非关键词
        self.assertEqual(stats["warning_symbol_count"], 2)
        self.assertTrue(any("警告类符号" in n for n in stats["notes"]))

    def test_supplementary_plane_symbols_counted(self):
        """🛡/🚧/🚫 为增补平面字符：完整码点写法必须可命中（交叉审查 P2 回归）。"""
        text = "Danger 🛡 shield zone. Blocked 🚧 and 🚫 marks."
        stats = analyze_structure("sample.txt", text, [text])
        self.assertEqual(stats["warning_symbol_count"], 3)

    def test_warning_noun_phrase_titles(self):
        """P1-2 修复：名词短语标题形态（Laser Safety Warning 等）应计入安全警告。
        Kimi 外部报告实测 Illumina 手册 6 大类 Safety Warning 标题，我方此前仅匹配行首 WARNING → 假阴性 0。"""
        text = ("Laser Safety Warning\n"
                "Hot Surface Safety Warning\n"
                "Heavy Object Safety Warning\n"
                "Mechanical Safety Warning\n"
                "激光安全警告\n"
                "WARNING Hot surface. Do not touch.\n"
                "Do not remove the cover. Refer to the Laser Safety Warning in the manual.\n"
                "This sentence mentions Safety Warning but is ordinary prose ending with a period.")
        stats = analyze_structure("sample.txt", text, [text])
        self.assertGreaterEqual(stats["warning_count"], 6)
        # 正文句子（含句号收尾的 Safety Warning 引用）不得误计
        self.assertLessEqual(stats["warning_count"], 7)

    def test_warning_prose_with_period_not_counted(self):
        """句号收尾的正文句子（引用 Safety Warning）不得计入警告。"""
        text = "Always refer to the Laser Safety Warning before servicing the instrument."
        stats = analyze_structure("sample.txt", text, [text])
        self.assertEqual(stats["warning_count"], 0)

    def test_warning_figure_caption_not_counted(self):
        """交叉审查实测：图题（Figure 3-1 Laser Safety Warning）与正文句不得误计。"""
        text = ("Figure 3-1 Laser Safety Warning\n"
                "See the Laser Safety Warning before servicing.\n"
                "A Safety Warning is printed on the cover.\n"
                "The following is the Laser Safety Warning.\n"
                "Read the Safety Warning carefully.\n")
        stats = analyze_structure("sample.txt", text, [text])
        self.assertEqual(stats["warning_count"], 0)

    def test_warning_zh_prose_not_counted(self):
        """交叉审查实测：中文句子形态（请参阅/检查/以上为）不得误计为警告标题。"""
        text = ("请参阅安全警告\n"
                "检查安全警告\n"
                "以上为安全警告\n"
                "请注意安全警告信息\n")
        stats = analyze_structure("sample.txt", text, [text])
        self.assertEqual(stats["warning_count"], 0)

    def test_warning_zh_noun_phrase_counted(self):
        """中文专名标题（激光安全警告）仍应计入。"""
        text = "激光安全警告\n电气安全警告\n"
        stats = analyze_structure("sample.txt", text, [text])
        self.assertGreaterEqual(stats["warning_count"], 2)


class ComparisonNoneSafeTestCase(unittest.TestCase):
    """对比模块 None 安全（交叉审查 P1 回归）：insufficient 任务（score=None）入对比不崩溃。"""

    def test_insufficient_tasks_comparison(self):
        from app.utils.competitor_comparison import build_comparison
        payloads = [
            {"task_id": 1, "name": "a.htm", "readability": {
                "overall_score": None, "level": "insufficient", "warnings": [],
                "dimensions": {k: {"score": None} for k in (
                    "sentence_length", "term_density", "passive_ratio", "paragraph_length", "modifier_stack")},
            }, "tool_analysis": {}},
            {"task_id": 2, "name": "b.htm", "readability": {
                "overall_score": None, "level": "insufficient", "warnings": [],
                "dimensions": {k: {"score": None} for k in (
                    "sentence_length", "term_density", "passive_ratio", "paragraph_length", "modifier_stack")},
            }, "tool_analysis": {}},
        ]
        result, insights = build_comparison(payloads)  # 旧实现此处抛 TypeError
        self.assertEqual(len(result["overall_ranking"]), 2)
        self.assertTrue(any("样本不足" in i["action"] for i in insights),
                        "全员样本不足时应给出解释性洞察而非综合排名结论")

    def test_mixed_none_and_scored_comparison(self):
        from app.utils.competitor_comparison import build_comparison
        dims = lambda: {k: {"score": 80.0} for k in (
            "sentence_length", "term_density", "passive_ratio", "paragraph_length", "modifier_stack")}
        payloads = [
            {"task_id": 1, "name": "scored.pdf", "readability": {
                "overall_score": 82.0, "level": "good", "warnings": [], "dimensions": dims()},
             "tool_analysis": {}},
            {"task_id": 2, "name": "entry.htm", "readability": {
                "overall_score": None, "level": "insufficient", "warnings": [],
                "dimensions": {k: {"score": None} for k in dims()}},
             "tool_analysis": {}},
        ]
        result, _ = build_comparison(payloads)
        # 有分数的排第一，样本不足排最后（不崩溃）
        self.assertEqual(result["overall_ranking"][0], 1)
        self.assertEqual(result["overall_ranking"][-1], 2)


class EntryPageHintsTestCase(unittest.TestCase):
    """入口页识别：路径特征（大小写不敏感）/ 全文过短；正常正文页不误报。"""

    def test_frontpages_path_case_insensitive(self):
        hints = entry_page_hints(
            "https://x.com/IN/T1000/Content/IN/FrontPages/cover.htm", "x" * 2000
        )
        self.assertTrue(any("入口页" in h for h in hints))

    def test_index_path(self):
        hints = entry_page_hints("https://x.com/manual/index.htm", "x" * 2000)
        self.assertTrue(any("入口页" in h for h in hints))

    def test_short_text_flagged(self):
        hints = entry_page_hints("https://x.com/manual/topic.htm", "short text")
        self.assertTrue(any("封面" in h or "导航" in h for h in hints))

    def test_normal_topic_page_not_flagged(self):
        hints = entry_page_hints("https://x.com/manual/topic.htm", "x" * 2000)
        self.assertEqual(hints, [])


class HatLinkHintsTestCase(unittest.TestCase):
    """PDF 内嵌链接反查：HAT 导出特征提示。"""

    def test_hat_features_hinted(self):
        hrefs = [
            "https://support.example.com/Content/IN/T1000/topics/run.htm",
            "https://support.example.com/Skins/Default/Stylesheets/topic.css",
        ]
        hints = _hat_link_hints(hrefs)
        self.assertTrue(any("HAT" in h for h in hints))

    def test_plain_links_no_hint(self):
        hints = _hat_link_hints(["https://example.com/about", "https://example.com/a.pdf"])
        self.assertEqual(hints, [])


class CaptionLineFilterTestCase(unittest.TestCase):
    """例句过滤：标题/图表题注/规格数字行不进入问题例句。"""

    def test_spec_lines_filtered(self):
        for line in ("1500 VA LCD 100 V", "111 cm (43.7 in)", "Figure 3-2 Flow Cell"):
            self.assertTrue(_looks_like_caption_line(line), f"「{line}」应被过滤")

    def test_normal_sentence_kept(self):
        self.assertFalse(_looks_like_caption_line("Make sure the instrument is connected to a power outlet before use."))


class ReportInsufficientRenderTestCase(unittest.TestCase):
    """报告渲染联动：样本不足时综合评分/维度 N/A，跳过例句。"""

    def _insufficient_readability(self):
        text = _make_text(50)
        result = analyze_readability(text, [text])
        return result

    def test_insufficient_renders_na(self):
        readability = self._insufficient_readability()
        tool_analysis = {
            "summary": "测试",
            "meta": {"format": "TXT", "pages": 1},
            "structure_stats": analyze_structure("a.txt", _make_text(50), [_make_text(50)]),
        }
        report = render_competitor_report("a.txt", tool_analysis, readability)
        self.assertIn("样本不足（未评分）", report)
        self.assertIn("N/A", report)
        self.assertNotIn("典型问题例句", report)

    def test_normal_report_has_score(self):
        text = _make_text(120)
        readability = analyze_readability(text, [text])
        tool_analysis = {"summary": "测试", "meta": {"format": "TXT", "pages": 1}}
        report = render_competitor_report("a.txt", tool_analysis, readability)
        self.assertNotIn("样本不足（未评分）", report)
        self.assertIn("规则引擎 v1.1", report)


class InsightRefactorTestCase(unittest.TestCase):
    """洞察四分类：高分合并单条竞品基准，不逐维刷屏；上限 10 条。"""

    def _full_score_readability(self):
        text = _make_text(120)
        result = analyze_readability(text, [text])
        # 人为将全部维度抬到高分（结构化指标不变），验证合并逻辑
        for k in result["dimensions"]:
            result["dimensions"][k]["score"] = 100.0
        result["overall_score"] = 100.0
        result["level"] = "excellent"
        return result

    def test_high_dims_merged_into_single_baseline(self):
        readability = self._full_score_readability()
        insights = generate_rule_insights({"summary": "t", "meta": {}}, readability)
        baseline = [i for i in insights if i["area"] == "可读性 · 竞品基准"]
        self.assertEqual(len(baseline), 1, "高分维度应合并为单条竞品基准")

    def test_insights_capped_at_10(self):
        """构造 >10 条候选洞察（3 低分 P1 + 1 中分 P2 + 1 高分基准 + 工具/结构/警告/基线/总体/可信度），验证上限截断且 P1 在前。"""
        dims = {
            "sentence_length": {"score": 40.0, "label": "x", "samples": []},
            "term_density": {"score": 50.0, "label": "x", "samples": []},
            "passive_ratio": {"score": 45.0, "label": "x", "samples": []},
            "paragraph_length": {"score": 60.0, "label": "x", "samples": []},
            "modifier_stack": {"score": 90.0, "label": "x", "samples": []},
        }
        readability = {
            "language": "en", "overall_score": 72.0, "level": "good",
            "level_note": "", "warnings": ["文本样本量有限（120 句），评分仅供参考。"],
            "dimensions": dims, "stats": {"sentence_count": 120}, "suggestions": [],
        }
        tool_analysis = {
            "summary": "主编辑工具：Adobe FrameMaker（high 置信）", "meta": {},
            "tools": [{"name": "Adobe FrameMaker"}],
            "structure_stats": {"figure_count": 0, "table_count": 0, "page_count": 10, "warning_count": 0},
        }
        insights = generate_rule_insights(tool_analysis, readability)
        # 候选共 11 条（4 P1 + 7 P2），应被截断为 10
        self.assertEqual(len(insights), 10, f"应截断为 10 条，实际 {len(insights)}")
        priorities = [i["priority"] for i in insights]
        self.assertEqual(priorities, sorted(priorities, key=lambda p: 0 if p == "P1" else 1),
                         "P1 应排在前面")

    def test_low_dim_yields_p1(self):
        text = _make_text(120)
        readability = analyze_readability(text, [text])
        # 人为压低一个维度 → P1 机会洞察
        readability["dimensions"]["sentence_length"]["score"] = 30.0
        insights = generate_rule_insights({"summary": "t", "meta": {}}, readability)
        p1 = [i for i in insights if i["priority"] == "P1" and "平均句长" in i["area"]]
        self.assertTrue(p1, "维度 <55 应产出 P1 机会洞察")

    def test_experience_insights_low_score_p1(self):
        """体验三维度低分 → P1 可执行建议。"""
        from app.utils.competitor_insight import _experience_insights
        exp = {
            "access": {
                "dimensions": {
                    "has_search": {"score": 0, "grade": "无", "note": "未检出", "applicable": True},
                    "mobile_adaptation": {"score": 40, "grade": "需登录", "note": "需登录", "applicable": True},
                }
            },
            "findability": {
                "dimensions": {
                    "toc_completeness": {"score": 60, "grade": "部分", "note": "部分", "applicable": True},
                }
            },
            "usability": {
                "dimensions": {
                    "task_oriented_headings": {"score": 80, "grade": "良好", "note": "良好", "applicable": True},
                }
            }
        }
        ins = _experience_insights(exp)
        areas = [i["area"] for i in ins]
        self.assertTrue(any("站内搜索" in a for a in areas))
        self.assertTrue(any("移动端适配" in a for a in areas))
        self.assertTrue(any("目录结构" in a for a in areas))
        self.assertFalse(any("任务导向标题" in a for a in areas))  # 80 分不生成
        p1s = [i for i in ins if i["priority"] == "P1"]
        p2s = [i for i in ins if i["priority"] == "P2"]
        self.assertEqual(len(p1s), 2)  # has_search=0, mobile_adaptation=40
        self.assertEqual(len(p2s), 1)  # toc_completeness=60

    def test_experience_insights_skips_inapplicable(self):
        """applicable=False 的维度应跳过。"""
        from app.utils.competitor_insight import _experience_insights
        exp = {
            "access": {
                "dimensions": {
                    "access_barrier": {"score": None, "grade": None, "note": "N/A", "applicable": False},
                }
            }
        }
        self.assertEqual(_experience_insights(exp), [])

    def test_experience_insights_none(self):
        from app.utils.competitor_insight import _experience_insights
        self.assertEqual(_experience_insights(None), [])
        self.assertEqual(_experience_insights({}), [])

    def test_experience_insights_boundaries(self):
        """55/70 边界 + 异常类型/结构容错（P2-5 修复）。"""
        from app.utils.competitor_insight import _experience_insights
        exp = {
            "access": {
                "dimensions": {
                    # 55 归 P2（55–70 区间）；70 不生成；字符串 score 跳过
                    "has_search": {"score": 55, "applicable": True, "note": "边界"},
                    "formats": {"score": 70, "applicable": True, "note": "不生成"},
                    "languages": {"score": "60", "applicable": True, "note": "字符串"},
                }
            },
            "findability": "not-a-dict",  # section 非 dict 应跳过
        }
        ins = _experience_insights(exp)
        p2 = [i for i in ins if i["priority"] == "P2"]
        self.assertEqual(len(p2), 1, "仅 score=55 生成 1 条 P2")
        self.assertIn("站内搜索", p2[0]["area"])
        self.assertNotIn("格式选择", [i["area"] for i in ins], "70 分不应生成")
        self.assertNotIn("多语言支持", [i["area"] for i in ins], "字符串 score 应跳过")

    def test_experience_insights_no_double_punctuation(self):
        """映射文案以「。」结尾时，拼接不得出现「。，形成差异化优势」双标点粘连（查缺补漏修复）。"""
        from app.utils.competitor_insight import _experience_insights
        # formats 的 action 文案以「。」结尾（真实数据形态）
        exp = {
            "access": {
                "dimensions": {
                    "formats": {"score": 50, "applicable": True, "note": "单一格式"},
                    "version_transparency": {"score": 60, "applicable": True, "note": "部分版本号"},
                }
            }
        }
        ins = _experience_insights(exp)
        self.assertEqual(len(ins), 2)
        for i in ins:
            action = i["action"]
            self.assertNotIn("。，", action, f"双标点粘连: {action}")
            self.assertNotIn("。形成", action, f"双标点粘连: {action}")
            self.assertTrue(action.endswith("。"), f"行动建议应以句号结尾: {action}")
        p1 = next(i for i in ins if i["priority"] == "P1")
        self.assertIn("提供多格式输出", p1["action"])
        self.assertNotIn("。，", p1["evidence"])

    def test_experience_insights_quota_per_section(self):
        """每区最多 3 条（分数最低优先），防体验全低分洪峰挤占其他类别（P1-2 修复）。"""
        from app.utils.competitor_insight import _experience_insights
        exp = {
            "access": {
                "dimensions": {
                    "access_barrier": {"score": 10, "applicable": True, "note": "a"},
                    "formats": {"score": 20, "applicable": True, "note": "b"},
                    "has_search": {"score": 30, "applicable": True, "note": "c"},
                    "mobile_adaptation": {"score": 40, "applicable": True, "note": "d"},
                }
            }
        }
        ins = _experience_insights(exp)
        self.assertEqual(len(ins), 3, "access 区 4 个低分维度应截断为 3 条")
        # 分数最低的 3 条被保留（10/20/30），40 分被丢弃
        scores = [int(i["evidence"].split("得分 ")[1].split("（")[0]) for i in ins]
        self.assertEqual(sorted(scores), [10, 20, 30])

    def test_experience_insights_has_search_single_source(self):
        """has_search 仅从 Access 区生成（映射表只登记 access.has_search），Findability 区不重复（P2-3 对齐）。"""
        from app.utils.competitor_insight import _experience_insights
        exp = {
            "access": {
                "dimensions": {
                    "has_search": {"score": 30, "applicable": True, "note": "无搜索"},
                }
            },
            "findability": {
                "dimensions": {
                    "has_search": {"score": 30, "applicable": True, "note": "无搜索"},
                }
            },
        }
        ins = _experience_insights(exp)
        areas = [i["area"] for i in ins]
        self.assertEqual(sum(1 for a in areas if "站内搜索" in a), 1, "has_search 只应出现一次")
        self.assertTrue(any(a.startswith("可获得性") for a in areas))

    def test_rule_insights_baseline_preserved_under_experience_flood(self):
        """体验全低分洪峰时，「对比基线」引导条仍保底保留（P1-2 修复）。"""
        from app.utils.competitor_insight import generate_rule_insights
        dims = {
            "sentence_length": {"score": 40.0, "label": "x", "samples": []},
            "term_density": {"score": 50.0, "label": "x", "samples": []},
        }
        readability = {
            "language": "en", "overall_score": 50.0, "level": "fair",
            "level_note": "", "warnings": [],
            "dimensions": dims, "stats": {"sentence_count": 600}, "suggestions": [],
        }
        tool_analysis = {
            "summary": "主编辑工具：Adobe FrameMaker（high 置信）", "meta": {},
            "tools": [{"name": "Adobe FrameMaker"}],
            "structure_stats": {"figure_count": 0, "table_count": 0, "page_count": 10, "warning_count": 0},
        }
        # 体验三区全部低分 → 9 条体验洞察（3/区）
        exp = {}
        for sec in ("access", "findability", "usability"):
            dims_part = {}
            for i, k in enumerate(["access_barrier", "formats", "has_search", "mobile_adaptation",
                                   "toc_completeness", "has_breadcrumb", "has_index_glossary",
                                   "task_oriented_headings", "step_completeness", "error_recovery"][:4]):
                dims_part[k] = {"score": 10 + i * 10, "applicable": True, "note": "低分"}
            exp[sec] = {"dimensions": dims_part}
        insights = generate_rule_insights(tool_analysis, readability, exp)
        self.assertLessEqual(len(insights), 10, "总上限仍为 10 条")
        baselines = [i for i in insights if i["area"] == "对比基线"]
        self.assertEqual(len(baselines), 1, "体验洪峰下对比基线引导条不应被挤掉")
        self.assertEqual(insights[-1]["area"], "对比基线", "对比基线应保底在最后一位")


if __name__ == "__main__":
    unittest.main()
