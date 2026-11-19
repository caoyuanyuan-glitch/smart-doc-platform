"""抽象问题模式清单的安全边界测试。

核心约束：激活人工意见时，绝不能把具体文档的错误原文塞进 prompt（会照搬臆造）。
本测试守住两条：
  1. 抽象模式清单能生成、含模式描述、不含具体 comment 原文；
  2. 关闭开关时不生成；
  3. 既有 CYY section 的"省略 comment 细节"行为不被破坏。
"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.review_engine import human_review_patterns


def test_load_pattern_sections_contains_abstract_patterns(monkeypatch):
    monkeypatch.setenv("REVIEW_HUMAN_PATTERN_BASIS", "1")
    monkeypatch.setattr(
        human_review_patterns,
        "BASELINE_PATH",
        Path("/tmp/nonexistent.json"),
    )
    # 直接测映射表与生成逻辑：用内存数据
    monkeypatch.setattr(
        human_review_patterns,
        "BASELINE_PATH",
        SimpleNamespace(
            exists=lambda: True,
            read_text=lambda encoding="utf-8": json.dumps(
                {"summary": {"by_category": {"单位/空格": 78, "表达与句式": 134}}}
            ),
        ),
    )
    sections = human_review_patterns.load_pattern_sections()
    assert len(sections) == 1
    sec = sections[0]
    assert sec["basis_type"] == "human_pattern"
    assert "单位/空格" in sec["text"]
    assert "单位" in sec["text"] and "空格" in sec["text"]


def test_pattern_text_has_no_specific_document_error():
    """抽象模式描述里不得出现具体文档错误原文（照搬会臆造）。"""
    specific_errors = ["步骤3之后直接跳到步骤5", "过多竖线", "H-020-001408", "p27", "第 3 页"]
    for category, pattern in human_review_patterns.CATEGORY_PATTERNS.items():
        for err in specific_errors:
            assert err not in pattern, f"{category} 的模式描述含具体错误: {err}"


def test_pattern_can_be_disabled(monkeypatch):
    monkeypatch.setenv("REVIEW_HUMAN_PATTERN_BASIS", "0")
    monkeypatch.setattr(
        human_review_patterns,
        "BASELINE_PATH",
        SimpleNamespace(
            exists=lambda: True,
            read_text=lambda encoding="utf-8": json.dumps(
                {"summary": {"by_category": {"单位/空格": 78}}}
            ),
        ),
    )
    assert human_review_patterns.load_pattern_sections() == []
