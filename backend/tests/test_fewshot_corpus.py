"""P3 few-shot 判例接线：语料加载 + 选择策略 + prompt 注入。

背景（2026-11-23）：
- rule_corpus_fewshot.jsonl（168 条真实人工批注，64 个 label 族）此前无任何代码消费；
- 注入点：build_audit_prompt_payload 的 EN/CN system prompt，
  置于裁定程序之后、重要提醒之前，校准「什么样的问题值得报告」。
- 失败语义：语料缺失/损坏时返回空区块，不阻断审核主流程。
"""
import pytest

from app.review_engine import fewshot_corpus


@pytest.fixture(autouse=True)
def _clear_cache():
    fewshot_corpus.load_fewshot_examples.cache_clear()
    yield
    fewshot_corpus.load_fewshot_examples.cache_clear()


class TestLoadFewshotExamples:
    def test_loads_examples(self):
        # 168 条原始语料 + 2026-11-24 回流 R02 p145 列表批注 = 169
        rows = fewshot_corpus.load_fewshot_examples()
        assert len(rows) >= 169

    def test_rows_have_required_fields(self):
        rows = fewshot_corpus.load_fewshot_examples()
        for row in rows[:20]:
            assert row.get("label_code")
            assert row.get("comment")
            assert "label_name" in row

    def test_label_diversity(self):
        rows = fewshot_corpus.load_fewshot_examples()
        labels = {r["label_code"] for r in rows}
        assert len(labels) >= 60


class TestSelectFewshotExamples:
    def test_anchor_match_preferred(self):
        rows = fewshot_corpus.load_fewshot_examples()
        anchor_row = next(
            r for r in rows if len(r.get("anchor") or "") >= 6
        )
        excerpt = f"正文内容 {anchor_row['anchor']} 后续正文。"
        picked = fewshot_corpus.select_fewshot_examples(excerpt, match_limit=1)
        assert picked
        assert picked[0]["matched"] is True
        assert picked[0]["label_code"] == anchor_row["label_code"]

    def test_no_anchor_match_returns_empty(self):
        # 相关门控：无命中不注入（T7 回归实证——无差别兜底致 recall 回退）
        picked = fewshot_corpus.select_fewshot_examples(
            "与判例语料完全无关的一段普通正文，不会命中任何锚文本。"
        )
        assert picked == []

    def test_empty_excerpt_returns_empty(self):
        assert fewshot_corpus.select_fewshot_examples("") == []

    def test_z_family_excluded(self):
        rows = fewshot_corpus.load_fewshot_examples()
        z_row = next((r for r in rows if (r.get("label_code") or "").startswith("Z")
                      and len(r.get("anchor") or "") >= 6), None)
        assert z_row is not None  # 语料中确有 Z 族
        picked = fewshot_corpus.select_fewshot_examples(z_row["anchor"])
        assert all(not (p["label_code"] or "").startswith("Z") for p in picked)

    def test_empty_corpus_returns_empty(self, monkeypatch):
        monkeypatch.setattr(fewshot_corpus, "load_fewshot_examples", lambda: ())
        assert fewshot_corpus.select_fewshot_examples("任意正文") == []
        assert fewshot_corpus.build_fewshot_block("任意正文") == ""


class TestBuildFewshotBlock:
    def _excerpt_with_anchor(self):
        rows = fewshot_corpus.load_fewshot_examples()
        anchor = next(r["anchor"] for r in rows if len(r.get("anchor") or "") >= 6)
        return f"正文包含 {anchor} 作为上下文。"

    def test_cn_block_contains_header_and_labels(self):
        block = fewshot_corpus.build_fewshot_block(self._excerpt_with_anchor(), language="cn")
        assert block.startswith("审校判例")
        assert "｜位置上下文：" in block

    def test_en_block_english_header(self):
        block = fewshot_corpus.build_fewshot_block(self._excerpt_with_anchor(), language="en")
        assert block.startswith("CALIBRATION EXAMPLES")

    def test_block_char_budget(self):
        block = fewshot_corpus.build_fewshot_block(self._excerpt_with_anchor(), language="cn")
        assert len(block) <= fewshot_corpus._BLOCK_CHAR_BUDGET + 200

    def test_empty_when_no_examples(self, monkeypatch):
        monkeypatch.setattr(fewshot_corpus, "load_fewshot_examples", lambda: ())
        assert fewshot_corpus.build_fewshot_block("任意正文", language="cn") == ""

    def test_empty_when_no_anchor_match(self):
        assert fewshot_corpus.build_fewshot_block("无关正文，不命中任何锚文本。", language="cn") == ""


class TestPromptInjection:
    """注入点：EN/CN system prompt 均含判例区块，位于裁定程序与重要提醒之间。"""

    def _system_prompt(self, language, content=None):
        from app.utils.ai_client import AIClient

        client = AIClient.__new__(AIClient)
        if content is None:
            # 用语料中真实锚文本作节选，保证相关门控下区块非空
            rows = fewshot_corpus.load_fewshot_examples()
            anchor = next(r["anchor"] for r in rows if len(r.get("anchor") or "") >= 6)
            content = f"示例正文，包含锚文本 {anchor} 与其余内容。"
        return client.build_audit_prompt_payload(content, language=language)["system_prompt"]

    def test_cn_prompt_contains_fewshot_block(self):
        prompt = self._system_prompt("cn")
        assert "审校判例" in prompt
        # 位置：裁定程序之后、重要提醒之前
        assert prompt.index("审校判例") > prompt.index("裁定程序")
        assert prompt.index("审校判例") < prompt.index("重要提醒")

    def test_en_prompt_contains_fewshot_block(self):
        prompt = self._system_prompt("en")
        assert "CALIBRATION EXAMPLES" in prompt
        assert prompt.index("CALIBRATION EXAMPLES") > prompt.index("ADJUDICATION PROTOCOL")
        assert prompt.index("CALIBRATION EXAMPLES") < prompt.index("IMPORTANT REMINDERS")

    def test_injection_survives_corpus_failure(self, monkeypatch):
        monkeypatch.setattr(fewshot_corpus, "load_fewshot_examples", lambda: ())
        prompt = self._system_prompt("cn", content="任意正文。")
        assert "审校判例" not in prompt
        assert "重要提醒" in prompt  # 模板本身完整
