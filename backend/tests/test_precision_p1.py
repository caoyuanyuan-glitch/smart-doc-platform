"""P1 precision：二次验证路由 + completeness 模板收窄。

背景（2026-11-23）：
1. 二次验证 calls=0——`_is_deterministic_review_rule` 对 source=rule 一刀切豁免，
   ai_check_issues 恒空，AI 复核从未调用（2026-11-19 根因报告实证 547 候选 0 调用）。
   修复：新增 `_needs_ai_second_verification` 按规则 ID 白名单路由，
   CYY-CN-PUNCT/FORMAT/UNIT 等"人工经验基线"正则族（噪声主力）送 AI 复核。
2. completeness 泛化噪声——EN 模板原文直接教模型报
   "operation steps missing a required follow-up action"，
   MGIDL EN 实跑 9 条中 4 条为"缺后续动作/目的/确认触发"类泛化建议。
   修复：EN/CN 模板收窄为"节选内自证才报"，禁止与并列步骤对比式上报。
"""
import pytest

from app.api.review import _needs_ai_second_verification


def _issue(**kwargs):
    payload = {"source": "rule", "rule": "CYY-CN-PUNCT-002"}
    payload.update(kwargs)
    return payload


class TestNeedsAiSecondVerification:
    """二次验证路由：白名单豁免，基线正则族送 AI。"""

    @pytest.mark.parametrize("source", ["term", "spellcheck"])
    def test_term_and_spellcheck_exempt(self, source):
        assert _needs_ai_second_verification(_issue(source=source)) is False

    @pytest.mark.parametrize(
        "rule",
        [
            "DET-CN-UNIT-001",
            "DET-TYPO-001",
            "CYY-CN-PAGE-001",
            "DOC-PAGE-001",
            "STRUCT-PAGE-001",
            "STRUCT-LAYOUT-001",  # 几何/结构类：AI 复核只有文本证据，必误杀版式真问题
            "STRUCT-TERM-001",
            "SPELL-001",
            "FILENAME-002",
            "TOC-001",
            "REF-INDEX-001",
            "ANCHOR-FAIL-001",
            "LEARN-PATCH-001",
        ],
    )
    def test_whitelisted_deterministic_families_exempt(self, rule):
        assert _needs_ai_second_verification(_issue(rule=rule)) is False

    @pytest.mark.parametrize(
        "rule",
        [
            "CYY-CN-PUNCT-002",   # 人工经验基线正则族，噪声主力
            "CYY-CN-FORMAT-003",
            "CYY-CN-UNIT-001",
            "GRAMMAR-001",
            "UNIT-001",
            "PUNCT-001",
            "CHECKLIST-001",
            "TABLE-001",
        ],
    )
    def test_noisy_rule_families_sent_to_ai(self, rule):
        assert _needs_ai_second_verification(_issue(rule=rule)) is True

    def test_ai_source_sent_to_ai(self):
        assert _needs_ai_second_verification(_issue(source="ai", rule="")) is True

    def test_unknown_source_defaults_to_verify(self):
        assert _needs_ai_second_verification(_issue(source="", rule="")) is True


class TestPromptCompletenessNarrowing:
    """completeness 收窄：EN/CN 模板均要求节选内自证，禁并列对比式泛化建议。"""

    def _en_system_prompt(self):
        from app.utils.ai_client import AIClient

        client = AIClient.__new__(AIClient)
        return client.build_audit_prompt_payload("Sample body.", language="en")["system_prompt"]

    def _cn_system_prompt(self):
        from app.utils.ai_client import AIClient

        client = AIClient.__new__(AIClient)
        return client.build_audit_prompt_payload("示例正文。", language="cn")["system_prompt"]

    def test_en_completeness_requires_in_excerpt_proof(self):
        prompt = self._en_system_prompt()
        assert "ONLY when the excerpt itself proves the defect" in prompt
        assert "compared with parallel steps" in prompt

    def test_en_forbidden_generic_completeness(self):
        prompt = self._en_system_prompt()
        assert "Generic completeness suggestions that compare a step with its neighbors" in prompt

    def test_cn_forbidden_generic_completeness(self):
        prompt = self._cn_system_prompt()
        assert "完整性类泛化建议" in prompt
        assert "验收标准" in prompt
        assert "不安全状态" in prompt

    def test_cn_ui_transition_narrowed(self):
        prompt = self._cn_system_prompt()
        assert "不得仅因相邻步骤写了目的/结果/确认而当前步骤未写就上报" in prompt
