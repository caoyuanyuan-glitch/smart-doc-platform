"""已裁定误报过滤单测：用 POSEQ/MGIDL 实测报出的问题作样本，确保被挡住。"""
import json
import unittest
from pathlib import Path

from app.review_engine.ruled_false_positives import (
    should_drop_ruled_fp,
    is_ruled_ai_glued_word,
    is_ruled_icon_artifact,
    is_ruled_learned_patch_overfit,
    is_ruled_unit_zh_connect,
    is_ruled_warning_template,
)
from app.api.review import _detect_page_number_sequence_issues

BASE = Path(r"C:/Users/caoyuanyuan/WorkBuddy/2026-11-19-15-32-43")


class RuledFalsePositiveTestCase(unittest.TestCase):
    def test_real_reported_warning_templates_dropped(self):
        """MGIDL 中文 4 条警示模板句：实测误报。"""
        data = json.loads((BASE / "mgidl_cn_review_out/issues.json").read_text(encoding="utf-8"))
        hits = [x for x in data[:4] if "如操作不当或不避免" in x["original_text"]]
        self.assertEqual(len(hits), 4)
        for x in hits:
            self.assertTrue(is_ruled_warning_template(x), x["original_text"])

    def test_warning_template_with_prefix_dropped(self):
        """AI 把整行（含"提示操作者按照说明进行操作，"前缀）截出时也要认出。"""
        issue = {
            "source": "ai",
            "original_text": "提示操作者按照说明进行操作，如操作不当或不避免，则将会导致死亡或严重伤害",
            "suggestion": "提示操作者按照说明进行操作，如不按照说明操作，则将会导致死亡或严重伤害",
        }
        self.assertTrue(is_ruled_warning_template(issue))
        # 不含模板句的真语法问题不能被误丢
        other = {"source": "ai", "original_text": "如操作不当，可能导致设备损坏。"}
        self.assertFalse(is_ruled_warning_template(other))

    def test_real_reported_icon_artifacts_dropped(self):
        """MGIDL 英文 p32 的 tap 无控件名：渲染页有 ✓/✗ 图标，实测误报。"""
        data = json.loads((BASE / "mgidl_en_review_out/issues.json").read_text(encoding="utf-8"))
        icon_issues = [x for x in data if "Name the control" in x["suggestion"]]
        self.assertGreaterEqual(len(icon_issues), 2)
        for x in icon_issues:
            self.assertTrue(is_ruled_icon_artifact(x), x["original_text"][:60])

    def test_real_reported_table_header_concat_dropped(self):
        """故障表三列表头被连成一句：渲染页三列分开，属提取伪影 → 丢。"""
        data = json.loads((BASE / "mgidl_cn_review_out/issues.json").read_text(encoding="utf-8"))
        x = next(i for i in data if i["original_text"] == "故障现象原因分析处理方法")
        self.assertTrue(should_drop_ruled_fp(x))

    def test_table_header_missing_column_not_dropped(self):
        """同一拼接串，若 AI 指的是表格结构缺陷（缺列/列名缺失），是真问题，不能丢。

        回归背景：渲染核实 MGIDL 中文 p3 版本记录表——首列表头文字为白色字铺在
        白底上，视觉上不可见，表头确实缺列名。初版只按字符串精确匹配，把这条
        真缺陷当"表头拼接伪影"删掉了（中文首轮 12 条 → 落库 2 条时静默丢失）。
        """
        data = json.loads((BASE / "mgidl_cn_review_out/issues.json").read_text(encoding="utf-8"))
        x = next(i for i in data if i["original_text"] == "版本日期版本")
        self.assertIn("缺列", x["description"])
        self.assertFalse(should_drop_ruled_fp(x))

    def test_real_reported_learned_patch_overfit_dropped(self):
        data = json.loads((BASE / "mgidl_en_review_out/issues.json").read_text(encoding="utf-8"))
        x = next(i for i in data if i["rule"] == "LEARN-PATCH-001")
        self.assertTrue(is_ruled_learned_patch_overfit(x))

    def test_real_reported_glued_word_dropped(self):
        """POSEQ 的 nonTips：AI 输出黏连，文档中不存在。"""
        data = json.loads((BASE / "poseq_review_out/issues.json").read_text(encoding="utf-8"))
        x = next(i for i in data if "nonTips" in i["original_text"])
        content = ("Disposable non-filtered, sharp pipette tips. "
                   "② Adjust the volume and load a new 200 μL non-filtered pipette tip.")
        self.assertTrue(is_ruled_ai_glued_word(x, content))

    def test_glued_word_not_dropped_when_real_in_doc(self):
        """真实的拼写错误不能因为长得像黏连词就被丢。"""
        issue = {"source": "ai", "original_text": "nonfiltered pipette tip"}
        self.assertFalse(is_ruled_ai_glued_word(issue, "use a nonfiltered pipette tip"))

    def test_real_grammar_error_not_dropped(self):
        """DNBs enters → enter 是真问题，不能被误报过滤误伤。"""
        data = json.loads((BASE / "mgidl_en_review_out/issues.json").read_text(encoding="utf-8"))
        x = next(i for i in data if "DNBs enters" in i["original_text"])
        self.assertFalse(should_drop_ruled_fp(x))

    def test_icon_artifact_with_polluted_rule_field(self):
        """AI 问题的 rule 被污染成中文时，图标伪影过滤仍要生效。

        回归背景：早期实现 `if rule: return False`，而 AI 问题的 rule 在
        canonicalize 之前常是「信息不完整」这类中文描述，导致持久化关口
        4 条图标伪影全部漏过（MGIDL 英文实测）。
        """
        issue = {
            "source": "ai", "rule": "信息不完整", "category": "信息不完整",
            "original_text": "If the liquid has fully covered the flow cell, tap to return to the home interface.",
            "suggestion": "Name the control to tap to return to the home interface.",
            "context": "If the liquid has fully covered the flow cell, tap to return to the home interface.",
        }
        self.assertTrue(is_ruled_icon_artifact(issue))
        self.assertTrue(should_drop_ruled_fp(issue))
        # 规则号形态且来源是 rule → 不动
        rule_issue = dict(issue, source="rule", rule="UI-001")
        self.assertFalse(is_ruled_icon_artifact(rule_issue))

    def test_unit_zh_connect_bare_slice_dropped(self):
        """R025 只截到「h后」这一段时，也能认出 24 h后 属正常写法。"""
        issue = {
            "source": "rule", "rule": "R025", "original_text": "h后",
            "suggestion": "中英文之间请添加空格", "description": "禁止中英文混排无空格",
            "context": "于室温放置30 min ~\n\n24 h后使用。",
        }
        self.assertTrue(is_ruled_unit_zh_connect(issue))

    def test_unit_zh_connect_real_missing_space_not_dropped(self):
        """真的缺空格（24h后）是真问题，不能丢。"""
        issue = {
            "source": "rule", "rule": "R025", "original_text": "24h后",
            "suggestion": "中英文之间请添加空格", "context": "室温放置24h后使用",
        }
        self.assertFalse(is_ruled_unit_zh_connect(issue))

    def test_icon_artifact_zh_changan(self):
        """中文「长按 ，待进度条达到满格后」：渲染页有长按图标，文本层丢失。"""
        issue = {
            "source": "ai", "rule": "", "category": "操作步骤",
            "original_text": "长按 ，待进度条达到满格后",
            "suggestion": "长按【开始】按钮（原文按钮对象缺失）",
            "description": "操作对象缺失，用户无法判断长按哪个控件",
            "context": "8. 长按 ，待进度条达到满格后，屏幕显示提示【确认载片类型是否一致？】。",
        }
        self.assertTrue(is_ruled_icon_artifact(issue))

    def test_icon_artifact_placeholder_tap(self):
        """AI 把 tap 处标为 placeholder（p32 ✓/✗ 图标文本层缺失）的同一根因条目。"""
        issue = {
            "source": "ai", "rule": "",
            "original_text": "If the liquid still has not fully covered the flow cell after three retries, tap to return to the home interface.",
            "suggestion": "Specify the UI control to tap (e.g., the on-screen button label) instead of the placeholder 'tap to return to the home interface'.",
            "context": "three retries, tap to return to the home interface",
        }
        self.assertTrue(is_ruled_icon_artifact(issue))

    def test_named_chinese_control_not_dropped(self):
        """原文已写明【查看】等控件名的点击描述，属正常操作，不能当图标伪影丢。"""
        issue = {
            "source": "ai", "rule": "", "original_text": "点击【查看】>【运行参数】进入运行参数界面。",
            "suggestion": "指明按钮名称", "context": "点击【查看】",
        }
        self.assertFalse(is_ruled_icon_artifact(issue))

    def test_tap_to_verb_not_treated_as_named_control(self):
        """“tap to return” 里的 to 是目的状语，不是控件名。

        回归背景：早期 `_UI_NAMED_CONTROL` 正则把 to 当成控件名，导致 MGIDL 英文
        p32 的 4 条 ✓/✗ 图标伪影在持久化关口全部漏过（v4 实测：日志 15 条、
        丢 0 条）。
        """
        samples = [
            "If the liquid has fully covered the flow cell, tap to return to the home interface.",
            "If the liquid has not fully covered the flow cell, tap to retry loading.",
            "If they are inconsistent, tap to return to the home interface, reselect the correct flow cell type.",
            "If they are consistent, tap . DNB loading starts, which will be completed within 2 min.",
        ]
        for original in samples:
            issue = {
                "source": "ai", "rule": "",
                "original_text": original,
                "suggestion": "Name the UI control to tap to return to the home interface.",
                "context": original,
            }
            self.assertTrue(is_ruled_icon_artifact(issue), original[:50])

    def test_tap_named_button_still_not_dropped(self):
        """“tap the Finish button” 明确写了控件名 → 不是图标伪影。"""
        issue = {
            "source": "ai", "rule": "",
            "original_text": "Tap the Finish button to complete the run.",
            "suggestion": "Name the UI control to tap.",
            "context": "Tap the Finish button to complete the run.",
        }
        self.assertFalse(is_ruled_icon_artifact(issue))

    def test_learned_patch_scoped_to_same_source_doc(self):
        """学习补丁只对来源文档生效；文档号对不上时退回原行为（不静默整体关闭）。"""
        from app.review_engine.learned_patch import check_learned_patches

        text = "Power off the power. Power off the device."
        # 来源文档命中 → 报
        self.assertTrue(check_learned_patches(text, doc_id="H-020-000445-00_R01.pdf"))
        # 文件名不含任何来源文档号 → 退回原行为（仍然应用全部补丁），不静默关闭功能
        self.assertTrue(check_learned_patches(text, doc_id="unknown_doc.pdf"))


if __name__ == "__main__":
    unittest.main()
