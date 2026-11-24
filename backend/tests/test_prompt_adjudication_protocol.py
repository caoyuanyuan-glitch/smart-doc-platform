"""验证审核 prompt 的裁定程序注入（四问自检 / 待裁定通道 / 证据纪律）。

背景：MGIDL EN Tina 基准测试（2026-11）暴露 AI 通道缺「证据不足 → 待裁定」出口，
250 VA 凭常识上报、step 7 不核实就报。本文件锁定裁定程序在 CN/EN 两条 prompt 与
normalize 层的接入。
"""
from app.api.review_rules import SYSTEM_PROMPT_TEMPLATE, build_system_prompt
from app.utils import ai_client as ai_client_module
from app.utils.ai_client import AIClient


def _en_prompt():
    client = AIClient.__new__(AIClient)
    return client.build_audit_prompt_payload("Sample body.", language="en")


def _cn_prompt():
    client = AIClient.__new__(AIClient)
    return client.build_audit_prompt_payload("示例正文。", language="cn")


def test_cn_system_prompt_contains_adjudication_protocol():
    prompt = build_system_prompt()
    for keyword in ["裁定程序", "四问自检", "needs_human_review", "功能等价", "兜底声明", "加和自洽", "GB/T 18268"]:
        assert keyword in prompt, f"中文 system prompt 缺少裁定程序要素: {keyword}"


def test_en_prompt_contains_adjudication_protocol():
    payload = _en_prompt()
    system_prompt = payload["system_prompt"]
    for keyword in [
        "ADJUDICATION PROTOCOL",
        "needs_human_review=true",
        "fallback declarations",
        "arithmetic self-consistency",
        "functional equivalence",
        "GB/T 18268",
    ]:
        assert keyword in system_prompt, f"英文审核 prompt 缺少裁定程序要素: {keyword}"


def test_both_language_prompts_expose_needs_human_review_field():
    for payload in (_en_prompt(), _cn_prompt()):
        assert '"needs_human_review": false' in payload["user_prompt"], (
            "输出 JSON schema 未暴露 needs_human_review 字段"
        )


def test_normalize_keeps_explicit_needs_human_review_flag():
    client = AIClient.__new__(AIClient)
    content = "Power adapter input: 250 VA."
    issues = client.normalize_audit_issues(
        [
            {
                "original_text": "250 VA",
                "description": "单位疑似应为 W，无原文依据",
                "suggestion": "",
                "confidence": 82,
                "needs_human_review": True,
                "source": "ai",
            }
        ],
        content,
        source="ai",
    )
    assert len(issues) == 1
    assert issues[0]["needs_human_review"] is True


def test_normalize_auto_flags_mid_confidence_as_needs_human_review():
    client = AIClient.__new__(AIClient)
    content = "For detailed operations, refer to step 7."
    issues = client.normalize_audit_issues(
        [
            {
                "original_text": "step 7",
                "description": "步骤引用内容无法确认",
                "suggestion": "",
                "confidence": 60,
                "source": "ai",
            }
        ],
        content,
        source="ai",
    )
    assert len(issues) == 1
    assert issues[0]["needs_human_review"] is True


def test_protocol_text_shared_by_cn_fallback_template():
    """review_rules 的静态模板（fallback 路径）与 ai_client 动态模板必须同源注入。"""
    assert "裁定程序" in SYSTEM_PROMPT_TEMPLATE
    assert "裁定程序" in _cn_prompt()["system_prompt"]
