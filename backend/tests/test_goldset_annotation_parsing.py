# -*- coding: utf-8 -*-
"""任务 11 回归守卫：goldset 解析不得再静默返回 0 条。

历史缺陷：parse_human_annotation_markdown 只认 "## 1. 标题 · 第 N 页" +
中文字段，而 human_baseline_gospatial_v2_24.md 用的是 "## 批注 N" + 英文字段，
导致该文档 10 条人工批注被整份跳过，准确率门禁长期基于空 goldset 评估。
"""
import glob
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.review_engine.annotation_baseline import (  # noqa: E402
    parse_human_annotation_markdown,
)

GOLDSET = BACKEND / "goldset"


def test_geospatial_goldset_parses_non_empty():
    """geospatial goldset 必须解析出批注，不能返回 0 条。"""
    path = GOLDSET / "human_baseline_gospatial_v2_24.md"
    if not path.exists():
        return
    annotations = parse_human_annotation_markdown(path)
    assert annotations, "geospatial goldset 解析为 0 条，准确率门禁失去依据"
    assert len(annotations) >= 10, f"期望至少 10 条，实际 {len(annotations)} 条"


def test_geospatial_annotations_keep_manual_fields():
    """解析后必须保留人工显式写定的 category / layer / expected_rule。

    这些字段已在 goldset 里由人工确认，不应被启发式分类覆盖。
    """
    path = GOLDSET / "human_baseline_gospatial_v2_24.md"
    if not path.exists():
        return
    for item in parse_human_annotation_markdown(path):
        assert item.comment, "comment 不得为空"
        assert item.category, "category 不得为空"
        assert item.layer, "layer 不得为空"
        assert item.expected_rule, "expected_rule 不得为空"


def test_new_header_and_field_format_supported():
    """旧格式（页码在标题行）必须继续被支持，不能因兼容新格式而回归。"""
    legacy = (
        "## 1. 使用说明书.pdf · 第 3 页\n"
        "- 批注类型: 批注\n"
        "- 批注人: 张三\n"
        "- 人工意见: 参数前后不一致\n"
        "- 选中文本: 温度 25℃\n"
        "- 附近正文: 温度 25℃ 保存\n"
    )
    temp = GOLDSET / "_tmp_legacy_format_probe.md"
    try:
        temp.write_text(legacy, encoding="utf-8")
        annotations = parse_human_annotation_markdown(temp)
        assert len(annotations) == 1, f"旧格式应解析出 1 条，实际 {len(annotations)}"
        assert annotations[0].page == "3", f"旧格式页码应取自标题行，实际 {annotations[0].page!r}"
        assert annotations[0].selected_text == "温度 25℃"
    finally:
        if temp.exists():
            temp.unlink()


def test_markdown_goldset_files_are_not_silently_empty():
    """任何 markdown goldset 都不允许解析为 0 条（防同类静默回归）。"""
    empty = []
    for path in sorted(GOLDSET.glob("*.md")):
        if not parse_human_annotation_markdown(path):
            empty.append(path.name)
    assert not empty, f"以下 goldset 解析为 0 条：{empty}"


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as exc:
            failures += 1
            print(f"  FAIL  {name}: {exc}")
    print()
    print("全部通过" if not failures else f"失败 {failures} 项")
    sys.exit(1 if failures else 0)
