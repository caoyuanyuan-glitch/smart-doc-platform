import unittest

from app.api.qa import (
    _format_markdown_tables,
    _is_valid_answer,
    _split_content_to_chunks,
    _unwrap_qa_answer,
    _strip_source_files_from_answer,
)
from app.utils.ai_client import build_qa_answer_prompt, detect_source_lang


class QaAnswerFormatTest(unittest.TestCase):
    def test_unwrap_fenced_json_answer(self):
        raw = """```json
{
  "answer": "适配器翻译为 Adapter。",
  "source": "平台反馈的术语对照表.md"
}
```"""
        self.assertEqual(_unwrap_qa_answer(raw), "适配器翻译为 Adapter。")

    def test_short_term_answer_is_valid(self):
        self.assertTrue(_is_valid_answer("适配器翻译为 Adapter。"))

    def test_markdown_table_becomes_list(self):
        md = """# 术语对照表

| 非标准 | 标准 | Non-standard | Standard |
|---|---|---|---|
| 接头 | 适配器 | 接头 | Adapter |
| 转接头 | 适配器 | 转接头 | Adapter |
"""
        formatted = _format_markdown_tables(md)
        self.assertIn("- 接头 → 适配器（Adapter）", formatted)
        self.assertIn("- 转接头 → 适配器（Adapter）", formatted)
        self.assertNotIn("| 接头 |", formatted)

    def test_chunks_keep_markdown_list_rows(self):
        content = "术语对照\n- 接头 → 适配器（Adapter）\n- 转接头 → 适配器（Adapter）"
        chunks = _split_content_to_chunks(content, chunk_size=80, overlap=20)
        joined = "\n".join(chunks)
        self.assertIn("- 接头 → 适配器（Adapter）", joined)

    def test_strips_file_paths_keeps_descriptions(self):
        raw = """中、检查基准
- 中文说明书写作 Checklist: `.monkeycode-tmp-files/152fab92-中文说明书写作Checklist-1.xlsx`
- 英文说明书写作 Checklist: `.monkeycode-tmp-files/bb261344-英文说明书写作Checklist-2.xlsx`
- 知识库管理中的发布前规范文件位于：`写作规范 > 说明书自检checklist`

六、审核依据汇总中当前实际生效的依据
- `../写作风格指南/中文技术文档写作风格指南.md`：中文文档写作风格约束
- `../说明书自检checklist/中文说明书写作Checklist.xlsx`：中文说明书发布前自检
- `../说明书自检checklist/英文说明书写作Checklist.xlsx`：英文说明书发布前自检
- `cyy-human-review-baseline.json`
"""
        cleaned = _strip_source_files_from_answer(raw)
        self.assertNotIn(".xlsx", cleaned)
        self.assertNotIn(".md", cleaned)
        self.assertNotIn(".json", cleaned)
        self.assertNotIn("monkeycode-tmp-files", cleaned)
        self.assertIn("中文说明书写作 Checklist", cleaned)
        self.assertIn("中文文档写作风格约束", cleaned)
        self.assertIn("中文说明书发布前自检", cleaned)

    def test_drops_dangling_location_sentence(self):
        raw = """发布前自检应依据以下内容：
三、英文说明书发布前 Checklist
网址链接：统一不加下划线，且正文内斜体、独立成行。

此外，知识库管理中的发布前规范文件位于：
"""
        cleaned = _strip_source_files_from_answer(raw)
        self.assertNotIn("位于", cleaned)
        self.assertIn("英文说明书发布前 Checklist", cleaned)

    def test_english_manual_prompt_uses_source_wording(self):
        title = "H-020-001104-00 DNBSEQ-T1+RS Genetic Sequencer System Guide_English_RUO_SZ"
        self.assertEqual(detect_source_lang("The expected service life is 7 years.", [title]), "en")
        prompt = build_qa_answer_prompt("service life", "The expected service life of the instrument is 7 years.", "en")
        self.assertIn("original English wording", prompt)
        self.assertIn("write the answer in english", prompt.lower())
        self.assertIn("Format the answer as Markdown lists", prompt)
        self.assertIn("Numbered lists", prompt)
        self.assertIn("Unordered lists", prompt)

    def test_chinese_manual_prompt_keeps_original_sentences(self):
        title = "H-020-001105-00 DNBSEQ-T1+RS 基因测序仪系统操作指南_中文_RUO"
        self.assertEqual(detect_source_lang("该设备的使用寿命为七年。", [title]), "zh")
        prompt = build_qa_answer_prompt("使用寿命", "该设备的使用寿命为七年。", "zh")
        self.assertIn("用说明书原文作答", prompt)
