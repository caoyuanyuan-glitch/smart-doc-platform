"""11-23 裁定的 4 个系统性误报修复（T7 EN R03 驱动）：

1. DOC-FMT-003 缺全文一致性守卫——全文 26 处 "Buffer(" 全无空格仍建议加空格（27 条误报）。
2. a/an 规则缺前置词检查——"side A outward"、"Flow cell A operation"、"32 A industrial"
   的大写 A 是侧别标签/安培单位，不是冠词（园园裁定 7 条误报）。
3. rule↔AI 跨源去重缺口——T7 EN p181「测序停止」rule/AI 同文本同页，
   因章节闸门不同漏折叠。
4. AI 建议方向锚定主写法——Read1×52 主写法被建议改成少数派带空格形（提示词层修复）。
"""

import inspect
import json

from app.api.review import (
    _run_manual_engineering_audit,
    dedupe_issues_by_original,
)
from app.api.review_rules import SYSTEM_PROMPT_TEMPLATE
from app.utils import ai_client


def _fmt003_issues(content):
    return [i for i in _run_manual_engineering_audit(content, "pdf")
            if i.get("rule") == "DOC-FMT-003"]


def _grammar002_issues(content):
    return [i for i in _run_manual_engineering_audit(content, "pdf")
            if i.get("rule") == "DOC-GRAMMAR-002"]


class TestDocFmt003DominantFormGuard:
    def test_dominant_nospace_not_reported(self):
        # T7 EN 实况：同一词形全文均为无空格写法 → 主写法，不报
        content = "Make DNB Buffer(OS-App-D-V4.0) is ready. " * 6
        assert _fmt003_issues(content) == []

    def test_minority_nospace_reported(self):
        # 主写法为带空格（5 处），个别无空格（1 处）→ 只报少数派
        content = ("Buffer (OS-App-D-V4.0) is ready. " * 5
                   + "Buffer(OS-App-D-V4.0) is ready.")
        issues = _fmt003_issues(content)
        assert len(issues) == 1
        assert "Buffer(OS-App-D-V4.0)" in issues[0]["original_text"].replace(" ", "") or \
            "Buffer(OS-App-D-V4.0)" in issues[0]["original_text"]

    def test_other_word_unaffected(self):
        # 守卫按词形计数，不影响其他词的既有行为
        content = "Progress(10/302) shown in UI. " * 3
        assert _fmt003_issues(content) == []


class TestArticleSideLabelGuard:
    def test_side_label_a_not_article(self):
        content = ("side A outward direction is normal. "
                   "Flow cell A operation area remains clean. "
                   "The power supply is 32 A industrial grade.")
        assert _grammar002_issues(content) == []

    def test_sentence_start_article_still_reported(self):
        # 行首/句首的大写 A 是真冠词，元音词仍应报 an
        content = "A operation manual is provided for the user."
        issues = _grammar002_issues(content)
        assert len(issues) == 1
        assert issues[0]["suggestion"].startswith("an")

    def test_lowercase_article_unaffected(self):
        # 小写 a 不受守卫影响
        content = "a operation error occurred"
        issues = _grammar002_issues(content)
        assert len(issues) == 1


def _pos(page, start=None):
    payload = {"page_number": page}
    if start is not None:
        payload.update({"char_start": start, "char_end": start + 20})
    return json.dumps(payload)


def _issue(text, page, rule, chapter, source):
    return {
        "rule": rule,
        "category": "语法与表达",
        "chapter": chapter,
        "original_text": text,
        "position": _pos(page),
        "severity": "general",
        "confidence": 80,
        "source": source,
    }


class TestCrossSourceSamePageFold:
    def test_rule_ai_same_text_same_page_folds(self):
        # T7 EN p181「测序停止」：rule(ENG-CN-001) 与 AI 同文本同页但章节名不同 → 折叠
        issues = [
            _issue("测序停止", 181, "ENG-CN-001", "附录", "rule"),
            _issue("测序停止", 181, "AI", "4 °C", "ai"),
        ]
        result = dedupe_issues_by_original(issues)
        assert len(result) == 1
        assert result[0]["source"] == "rule"

    def test_same_text_different_page_kept(self):
        issues = [
            _issue("测序停止", 181, "ENG-CN-001", "附录", "rule"),
            _issue("测序停止", 200, "AI", "4 °C", "ai"),
        ]
        assert len(dedupe_issues_by_original(issues)) == 2

    def test_disjoint_spans_still_kept_despite_same_page(self):
        # 同页同词两次独立出现（char 跨度不相交）仍不折叠——occurrence 守卫优先
        rule = _issue("requirment", 57, "SPELL", "TOC", "rule")
        ai = _issue("requirment", 57, "AI", "TOC", "ai")
        rule["position"] = json.dumps({"page_number": 57, "char_start": 100, "char_end": 120})
        ai["position"] = json.dumps({"page_number": 57, "char_start": 50000, "char_end": 50020})
        assert len(dedupe_issues_by_original([rule, ai])) == 2


class TestDominantFormPromptAnchoring:
    def test_en_prompt_has_dominant_form_rule(self):
        source = inspect.getsource(ai_client)
        assert "Dominant-form anchoring" in source
        assert "dominant (majority) form" in source

    def test_cn_prompt_has_dominant_form_rule(self):
        assert "主写法锚定" in SYSTEM_PROMPT_TEMPLATE
        assert "主写法" in SYSTEM_PROMPT_TEMPLATE
