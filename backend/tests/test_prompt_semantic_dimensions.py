"""验证 DeepSeek 审核 prompt 的语义维度覆盖（P3-A~D）。"""
from app.api.review_rules import (
    SEMANTIC_FEWSHOT_EXAMPLES,
    SYSTEM_PROMPT_TEMPLATE,
    build_system_prompt,
)


def test_prompt_contains_semantic_dimensions():
    prompt = build_system_prompt()
    for keyword in ["冗余", "表述不准确", "信息不完整", "一致性", "语气", "图表衔接", "句子成分", "方向"]:
        assert keyword in prompt, f"prompt 缺少语义维度: {keyword}"


def test_fewshot_contains_g99_anchor_phrases():
    assert "关于本指南" in SEMANTIC_FEWSHOT_EXAMPLES
    assert "请点击" in SEMANTIC_FEWSHOT_EXAMPLES
    assert "播放提示音" in SEMANTIC_FEWSHOT_EXAMPLES
    assert "返回主界面" in SEMANTIC_FEWSHOT_EXAMPLES
    assert "barcode" in SEMANTIC_FEWSHOT_EXAMPLES


def test_output_format_includes_semantic_types():
    assert "冗余" in SYSTEM_PROMPT_TEMPLATE
    assert "表述不准确" in SYSTEM_PROMPT_TEMPLATE
    assert "信息不完整" in SYSTEM_PROMPT_TEMPLATE
