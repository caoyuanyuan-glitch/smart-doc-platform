"""已裁定误报过滤单测：用 POSEQ/MGIDL 实测报出的问题作样本，确保被挡住。"""
import json
import unittest
from pathlib import Path

from app.review_engine.ruled_false_positives import (
    should_drop_ruled_fp,
    is_ruled_ai_glued_word,
    is_ruled_icon_artifact,
    is_ruled_learned_patch_overfit,
    is_ruled_politeness,
    is_ruled_spacing_style,
    is_ruled_unit_zh_connect,
    is_ruled_warning_template,
)
from app.api.review import _detect_page_number_sequence_issues

BASE = Path(r"C:/Users/caoyuanyuan/WorkBuddy/2026-11-19-15-32-43")
HAS_FIXTURES = BASE.is_dir()


class RuledFalsePositiveTestCase(unittest.TestCase):
    @unittest.skipUnless(HAS_FIXTURES, "需要本地 POSEQ/MGIDL 实测 issues.json 样例")
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

    @unittest.skipUnless(HAS_FIXTURES, "需要本地 POSEQ/MGIDL 实测 issues.json 样例")
    def test_real_reported_icon_artifacts_dropped(self):
        """MGIDL 英文 p32 的 tap 无控件名：渲染页有 ✓/✗ 图标，实测误报。"""
        data = json.loads((BASE / "mgidl_en_review_out/issues.json").read_text(encoding="utf-8"))
        icon_issues = [x for x in data if "Name the control" in x["suggestion"]]
        self.assertGreaterEqual(len(icon_issues), 2)
        for x in icon_issues:
            self.assertTrue(is_ruled_icon_artifact(x), x["original_text"][:60])

    @unittest.skipUnless(HAS_FIXTURES, "需要本地 POSEQ/MGIDL 实测 issues.json 样例")
    def test_real_reported_table_header_concat_dropped(self):
        """故障表三列表头被连成一句：渲染页三列分开，属提取伪影 → 丢。"""
        data = json.loads((BASE / "mgidl_cn_review_out/issues.json").read_text(encoding="utf-8"))
        x = next(i for i in data if i["original_text"] == "故障现象原因分析处理方法")
        self.assertTrue(should_drop_ruled_fp(x))

    @unittest.skipUnless(HAS_FIXTURES, "需要本地 POSEQ/MGIDL 实测 issues.json 样例")
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

    @unittest.skipUnless(HAS_FIXTURES, "需要本地 POSEQ/MGIDL 实测 issues.json 样例")
    def test_real_reported_learned_patch_overfit_dropped(self):
        data = json.loads((BASE / "mgidl_en_review_out/issues.json").read_text(encoding="utf-8"))
        x = next(i for i in data if i["rule"] == "LEARN-PATCH-001")
        self.assertTrue(is_ruled_learned_patch_overfit(x))

    @unittest.skipUnless(HAS_FIXTURES, "需要本地 POSEQ/MGIDL 实测 issues.json 样例")
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

    @unittest.skipUnless(HAS_FIXTURES, "需要本地 POSEQ/MGIDL 实测 issues.json 样例")
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


    def test_politeness_please_dropped(self):
        """用户裁定：「请」「请勿」在中文说明书里是标准写法，一律不报。"""
        samples = [
            {
                "source": "ai", "category": "可读性",
                "original_text": "请按照仪器的实际情况选择清洗类型。",
                "description": "操作步骤中不加敬语“请”",
            },
            {
                "source": "ai", "category": "语法",
                "original_text": "吸取上清时，请勿触碰磁珠。",
                "description": "操作步骤中不得添加“请”等敬语（除 UI 提示外）",
            },
            {
                "source": "ai", "category": "术语一致性",
                "original_text": "请在首次登录后修改登录密码，并定期更换。",
                "suggestion": "首次登录后修改登录密码，并定期更换。",
                "rule": "操作步骤不加敬语'请'",
            },
        ]
        for issue in samples:
            self.assertTrue(is_ruled_politeness(issue), issue["original_text"])
            self.assertTrue(should_drop_ruled_fp(issue), issue["original_text"])

    def test_politeness_without_hint_not_dropped(self):
        """原文含「请」但描述不指向敬语时，不能误伤（如「申请」「请求」）。"""
        issue = {
            "source": "ai", "category": "语法",
            "original_text": "点击【申请】提交请求。",
            "description": "缺少后续动作，应补充返回主界面",
        }
        self.assertFalse(is_ruled_politeness(issue))


    def test_spacing_style_ai_issues_dropped(self):
        """AI 凭"别处有空格"反推的排版问题，价值极低（T7+RS 中文实测）。"""
        samples = [
            {
                "source": "ai",
                "original_text": "通过内置的 write_fastq 分析流程将其转换成FASTQ 文件。",
                "description": "英文缩写与中文之间应保留空格，全文统一",
            },
            {
                "source": "ai",
                "original_text": "数据盘：8 TB 企业级NL-SAS HDD×55",
                "description": "英文缩写与中文之间、乘号前后应保留空格",
            },
            {
                "source": "ai",
                "original_text": "（货号：1000028550 ）",
                "description": "全角括号内不应有多余空格",
            },
            {
                "source": "ai",
                "original_text": "MGI Barcode 序列对应创建测序方案界面【Barcode】的序列",
                "description": "同一表格内同类条目空格/分隔体例应统一",
            },
        ]
        for issue in samples:
            self.assertTrue(is_ruled_spacing_style(issue), issue["original_text"])
            self.assertTrue(should_drop_ruled_fp(issue), issue["original_text"])

    def test_spacing_style_rule_sourced_kept(self):
        """规则引擎的单位/空格规则是确定性产出，不能被 AI 排版过滤器吞掉。"""
        issue = {
            "source": "rule", "rule": "EXT-R001",
            "original_text": "2 ℃~8 ℃",
            "description": "单位前面加空格。数字、波浪线与温度单位的空格风格需要统一。",
        }
        self.assertFalse(is_ruled_spacing_style(issue))
        self.assertFalse(should_drop_ruled_fp(issue))

    def test_spacing_style_substance_kept(self):
        """描述指向错别字/术语/内容缺失等实质缺陷时，不能按空格体例丢弃。"""
        samples = [
            {
                "source": "ai", "original_text": "手工操作：10",
                "description": "时长数值缺少单位，且与相邻时长表述格式不一致",
            },
            {
                "source": "ai", "original_text": "手工制备DNB",
                "description": "同一概念全文用词不统一：正文其他处使用“手工制备 DNB”，此处用“手动”",
            },
            {
                "source": "ai", "original_text": "屏幕 尺寸",
                "description": "技术规格表中屏幕尺寸项无具体数值，内容缺失",
            },
        ]
        for issue in samples:
            self.assertFalse(is_ruled_spacing_style(issue), issue["original_text"])

    def test_joined_table_headers_dropped(self):
        """多列表头被文本层拼成一句，渲染页本应分列 → 提取伪影。"""
        samples = [
            {"source": "ai", "original_text": "标准液体积样本体积",
             "description": "表头两列标题粘连，无法区分列含义"},
            {"source": "ai", "original_text": "版本编号试剂盒版本号",
             "description": "表格列“符号/标题/说明”之间缺少分隔，“版本编号”与“试剂盒版本号”粘连"},
            {"source": "ai", "original_text": "文库类型文库接头初始环化ssDNA 文库浓度要求",
             "description": "表格表头列名应可区分"},
        ]
        for issue in samples:
            self.assertTrue(should_drop_ruled_fp(issue), issue["original_text"])

    def test_table_content_missing_kept(self):
        """表头拼接形态但 AI 指的是单元格内容缺失/结构缺陷 → 真问题，保留。"""
        samples = [
            {"source": "ai", "original_text": "组分信息管盖颜色规格及数量储存温度运输温度有效期",
             "description": "表格内容完整性：表头包含“有效期”列，但表体中该列无任何数据"},
            {"source": "ai", "original_text": "表 15 解冻方法与时长 解冻方式 室温放置解冻时长（h）",
             "description": "表格仅有表头和温度区间，缺少对应的解冻时长数值，用户无法按表执行解冻"},
        ]
        for issue in samples:
            self.assertFalse(should_drop_ruled_fp(issue), issue["original_text"])

    def test_term_entry_separator_kept(self):
        """术语条目名与解释之间缺分隔符是用户确认的真缺陷，不能当表头伪影丢。"""
        issue = {
            "source": "ai", "original_text": "暗反应是载片上拍照的无效区域",
            "description": "术语条目名与解释之间缺分隔符",
        }
        self.assertFalse(should_drop_ruled_fp(issue))


    def test_spacing_style_reads_rule_before_canonicalize(self):
        """AI 问题的 rule 字段常是判定文本、description 为空。
        持久化关口在 canonicalize_issue_rule 之前执行，过滤器必须读 rule，
        否则空格类噪音全部漏过（T7+RS 实测漏 22 条）。
        """
        issue = {
            "source": "ai", "original_text": "8 TB 企业级NL-SAS HDD×55",
            "description": "", "suggestion": "",
            "rule": "数字与单位、乘号之间必须保留空格，乘号使用 × 且前后保留空格",
        }
        self.assertTrue(is_ruled_spacing_style(issue))
        self.assertTrue(should_drop_ruled_fp(issue))

    def test_table_header_concat_reads_rule_before_canonicalize(self):
        """表头粘连判定同样要在 description 为空时读 rule 字段。"""
        issue = {
            "source": "ai", "original_text": "标准液体积样本体积",
            "description": "", "suggestion": "",
            "rule": "表头两列名称粘连，无法区分标准液体积与样本体积列",
        }
        self.assertTrue(should_drop_ruled_fp(issue))


    def test_operator_spacing_dropped(self):
        """公式运算符空格属排版，AI 来源时不报。"""
        issue = {
            "source": "ai", "original_text": "总读长=100+1+100+1+8+8=218",
            "description": "公式运算符前后应保留空格，全文统一",
        }
        self.assertTrue(is_ruled_spacing_style(issue))
        self.assertTrue(should_drop_ruled_fp(issue))

    def test_caption_number_name_glued_dropped(self):
        """示意图"编号 + 名称 + 说明"被拼成一句属提取伪影。"""
        issue = {
            "source": "ai",
            "original_text": "4 总仓门测序试剂仓和废液仓的仓门。",
            "description": "名称与说明之间缺少分隔，导致“总仓门测序试剂仓”连读，术语边界不清",
        }
        self.assertTrue(should_drop_ruled_fp(issue))


    def test_number_unit_spacing_kept(self):
        """数字与单位紧贴缺空格是人工明确要求上报的（Tina R02 批注）。"""
        samples = [
            {"source": "ai", "original_text": "960GB/SATA3.0/2.5 寸/企业级×2",
             "description": "单位前面缺空格"},
            {"source": "ai", "original_text": "耗时约54min。",
             "description": "单位前面缺空格"},
            {"source": "ai", "original_text": "＞300bp 50 mL/支",
             "description": "数字与单位之间应保留空格"},
        ]
        for issue in samples:
            self.assertFalse(is_ruled_spacing_style(issue), issue["original_text"])
            self.assertFalse(should_drop_ruled_fp(issue), issue["original_text"])

    def test_paren_leading_space_kept(self):
        """全角括号前多余空格是人工确认的问题（p41：600 mm （宽））。"""
        issue = {
            "source": "ai", "original_text": "600 mm （宽）",
            "description": "是否有多余空格",
        }
        self.assertFalse(is_ruled_spacing_style(issue))

    def test_filename_typo_not_dropped_as_concat(self):
        """文件名拼写错误（【Workpace】缺 s）不能被表头拼接过滤器误丢。"""
        issue = {
            "source": "ai", "original_text": "【Workpace】文件夹中间文件",
            "description": "表格单元格内容缺少分隔，说明文字与文件夹名连写",
        }
        self.assertFalse(should_drop_ruled_fp(issue))

    def test_six_char_joined_headers_dropped(self):
        """6 字表头粘连（设备推荐品牌）同属文本层拼接伪影。"""
        issue = {
            "source": "ai", "original_text": "设备推荐品牌",
            "description": "表格表头各列名称粘连，无法区分列边界",
            "suggestion": "表头应拆分为独立列：设备、推荐品牌",
        }
        self.assertTrue(should_drop_ruled_fp(issue))

    def test_vague_term_claim_without_concrete_pair_dropped(self):
        """只喊"术语不统一"、不给出两种具体写法的指控属误报。"""
        samples = [
            ("清理磁盘历史数据", "同一概念全文统一"),
            ("【DualBarcode】 DualBarcode 读长", "同一术语/缩写的大小写全文必须一致"),
            ("图 59 准备维护清洗试剂槽2（常规清洗）", "同一对象/动作在不同章节描述不一致"),
            ("Barcode 与 DualBarcode",
             "同一术语全文大小写/写法应统一；正文与表格中 DualBarcode 与 DualBarcode 写法需一致"),
            ("试剂仓区域", "同一概念全文统一，不混用"),
            # "Dual Barcode" 与 "DualBarcode" 归一化后相同，属同一写法
            ("【DualBarcode】", "同一概念全文统一，DualBarcode 与 Dual Barcode 写法需统一"),
        ]
        for original, description in samples:
            issue = {"source": "ai", "original_text": original, "description": description}
            self.assertTrue(should_drop_ruled_fp(issue), original)

    def test_term_claim_with_concrete_pair_kept(self):
        """指出了两种具体不同写法，或给出改写建议时，是真问题。"""
        samples = [
            {"original_text": "测序试剂槽放入试剂仓抽屉后",
             "description": "同一对象“测序试剂槽/试剂仓”用词混用，需全文统一"},
            {"original_text": "【DualBarcode】",
             "description": "同一概念全文统一，不混用；正文用“双Barcode”，UI 用“DualBarcode”"},
            {"original_text": "试剂储存系统提供试剂储存的环境。",
             "description": "术语规则：试剂舱→试剂仓；同一概念全文统一，不混用"},
            {"original_text": "如测序仪制备DNB 上机，表中的测序时长（四边/单边）…",
             "description": "同一概念全文统一，不混用",
             "suggestion": "四边/单边 应统一为 四张载片/单载片"},
        ]
        for issue in samples:
            issue["source"] = "ai"
            self.assertFalse(should_drop_ruled_fp(issue), issue["original_text"])

    def test_header_missing_separator_dropped(self):
        """"缺少列分隔"仍属粘连伪影；指出内容缺失才保留。"""
        dropped = [
            {"original_text": "设备推荐品牌",
             "description": "表头两列名称粘连，缺少列分隔"},
            {"original_text": "试剂/耗材推荐品牌货号用途",
             "description": "表头各列名称粘连，缺少列分隔"},
            {"original_text": "组分信息管盖颜色规格及数量储存温度运输温度有效期",
             "description": "表头各列名称之间缺少分隔，无法区分列边界，表格内容完整性受影响"},
        ]
        for issue in dropped:
            issue["source"] = "ai"
            self.assertTrue(should_drop_ruled_fp(issue), issue["original_text"])
        kept = {
            "source": "ai",
            "original_text": "产品货号产品名称产品型号版本文库类型理论产出数据量 （Gb/载片）",
            "description": "表格表头与数据列对应关系不清晰，数据行缺少货号、产品名称等列内容，表格内容不完整",
        }
        self.assertFalse(should_drop_ruled_fp(kept))

    def test_positive_verdict_dropped(self):
        """AI 自认"一致/无误"的短结论句属误报；讲具体缺陷的长描述保留。"""
        dropped = [
            {"source": "ai", "original_text": "X 轴 Cycle 数",
             "description": "图表与正文描述一致"},
            # suggestion 附带改写建议不应让短结论句逃过长度阈值
            {"source": "ai", "original_text": "X 轴 Cycle 数",
             "description": "图表说明与图实际坐标轴一致", "suggestion": "X 轴 Barcode ID"},
        ]
        for issue in dropped:
            self.assertTrue(should_drop_ruled_fp(issue), issue["description"])
        kept = {
            "source": "ai",
            "original_text": "7 VGA 接口连接BCS 外接显示器。",
            "description": "术语一致性：VGA 接口位于SBC 侧，与“SBC 电源键”“SBC-USB”同组，却写为连接BCS 外接显示器",
        }
        self.assertFalse(should_drop_ruled_fp(kept))

    def test_repeat_defect_not_dropped_as_vague_term(self):
        """原文确有重复表述时，"同一对象重复"是语言缺陷，必须保留。"""
        issue = {
            "source": "ai",
            "original_text": "载片回收仓载片数量已达上限或载片回收仓收集盒未放到位时",
            "description": "同一对象重复表述冗余，应精简",
        }
        self.assertFalse(should_drop_ruled_fp(issue))

    def test_cjk_term_pair_kept(self):
        """中文写法对照（"振荡混匀与涡旋混匀"）属于具体对照，必须保留。"""
        issue = {
            "source": "ai",
            "original_text": "磁珠使用前必须涡旋混匀并平衡至室温，确保回收效率。",
            "description": "术语一致性：振荡混匀与涡旋混匀混用",
        }
        self.assertFalse(should_drop_ruled_fp(issue))

    def test_cross_reference_and_compliance_claims_kept(self):
        """描述是"需与…核对"时属待核实问题，不能当"AI 自认一致"丢掉。"""
        samples = [
            {"original_text": "参考第 104 页“（可选）通过MGI-αCube 查看测序状态",
             "description": "交叉引用页码需与实际章节页码一致"},
            {"original_text": "整机激光类别 1 类",
             "description": "激光类别声明应与设备实际激光安全等级一致"},
        ]
        for issue in samples:
            issue["source"] = "ai"
            self.assertFalse(should_drop_ruled_fp(issue), issue["description"])


if __name__ == "__main__":
    unittest.main()
