"""本地规范兜底（writing_standards_fallback）测试。

背景：知识库 DB 规范文件缺失或 ACL 不可读时，AI prompt 规范基线回退到
本地「审核依据」目录副本；知识库原文优先，兜底只填空键。
"""

import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.review_engine.writing_standards_fallback import (  # noqa: E402
    extract_human_review_kb_constraints,
    fallback_dir,
    load_fallback_spec_texts,
    reset_cache,
)


@pytest.fixture(autouse=True)
def _clean_cache(monkeypatch):
    reset_cache()
    monkeypatch.delenv("REVIEW_WRITING_STANDARDS_DIR", raising=False)
    yield
    reset_cache()


def _make_dir(tmp_path, files: dict[str, str]) -> Path:
    for name, content in files.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    return tmp_path


def test_load_fallback_maps_filenames_to_spec_keys(tmp_path):
    _make_dir(tmp_path, {
        "中文技术文档写作风格指南.md": "中文规范正文",
        "MGI英文技术文档写作风格指南.md": "EN guide body",
        "技术文档常见错误清单与规范.md": "常见错误正文",
        "2026历史人工审核意见知识库.md": "知识库正文",
    })
    texts = load_fallback_spec_texts(directory=tmp_path)
    assert texts["cn_style"] == "中文规范正文"
    assert texts["en_style"] == "EN guide body"
    assert texts["common_errors"] == "常见错误正文"
    assert texts["human_review_kb"] == "知识库正文"


def test_load_fallback_missing_dir_returns_empty(tmp_path):
    assert load_fallback_spec_texts(directory=tmp_path / "不存在") == {}


def test_load_fallback_partial_files_only_present_keys(tmp_path):
    _make_dir(tmp_path, {"中文技术文档写作风格指南.md": "仅中文"})
    texts = load_fallback_spec_texts(directory=tmp_path)
    assert "cn_style" in texts
    assert "en_style" not in texts


def test_fallback_dir_env_override(tmp_path, monkeypatch):
    _make_dir(tmp_path, {"技术文档常见错误清单与规范.md": "x"})
    monkeypatch.setenv("REVIEW_WRITING_STANDARDS_DIR", str(tmp_path))
    assert fallback_dir() == tmp_path
    assert "common_errors" in load_fallback_spec_texts()


def test_extract_kb_constraints_three_sections(tmp_path):
    kb = (
        "## 〇、统计\n统计内容\n\n"
        "## 十、人工明示待确认\n略\n\n"
        "## 十一、免报清单（人工明示不需改）★ 真免报 32 条\n"
        "免报A：弯直引号混用不报。\n免报B：商标声明页已带®不再报。\n\n"
        "## 十二、替换对照词库\n不应包含这一行\n\n"
        "## 十三、应用\n\n"
        "### 13.1 判定流程\n命中免报清单→排除\n\n"
        "### 13.2 证据要求\n术语不统一：全文出现次数+位置清单\n\n"
        "### 13.3 报告写作约束\n一条问题只出现一次\n"
    )
    out = extract_human_review_kb_constraints(kb)
    assert "免报A" in out
    assert "命中免报清单→排除" in out  # 13.1 判定流程
    assert "全文出现次数+位置清单" in out  # 13.2 证据要求
    assert "不应包含这一行" not in out  # 十二段被排除
    assert "一条问题只出现一次" not in out  # 13.3 之后的段不进约束块


def test_extract_kb_constraints_empty_input():
    assert extract_human_review_kb_constraints("") == ""
    assert extract_human_review_kb_constraints("没有任何小节标记的文本") == ""


def test_extract_kb_constraints_max_chars(tmp_path):
    kb = "## 十一、免报清单\n" + "长" * 9000
    out = extract_human_review_kb_constraints(kb, max_chars=100)
    assert len(out) <= 160
    assert "已截断" in out


def test_load_review_spec_texts_prefers_db_text(monkeypatch, tmp_path):
    """知识库原文优先：DB 有文本时不被兜底覆盖；DB 为空时启用兜底。"""
    from app.api import review as review_mod

    monkeypatch.setattr(
        review_mod, "_get_review_spec_files_from_knowledge", lambda db: {
            "cn_style": {"file_path": str(tmp_path / "db_cn.md")},
            "common_errors": {"file_path": str(tmp_path / "missing_db.md")},
        }
    )
    (tmp_path / "db_cn.md").write_text("DB中文原文", encoding="utf-8")
    import app.review_engine.writing_standards_fallback as wsf
    monkeypatch.setattr(wsf, "load_fallback_spec_texts", lambda: {
        "cn_style": "兜底中文",
        "common_errors": "兜底常见错误",
    })
    spec_texts = review_mod._load_review_spec_texts(db=None)
    assert spec_texts["cn_style"] == "DB中文原文"  # DB 优先，兜底不覆盖
    assert spec_texts["common_errors"] == "兜底常见错误"  # DB 缺失，兜底生效


def test_fallback_source_wired_into_basis_sections(tmp_path):
    """human_review_kb 非空时 basis sections 含硬约束块。"""
    from app.api import review as review_mod

    kb = "## 十一、免报清单\n免报A：弯直引号混用不报。\n"
    spec_texts = {"human_review_kb": kb, "cn_style": "", "en_style": "", "common_errors": ""}
    parts = review_mod._build_ai_review_basis_sections(spec_texts, "both")
    constraint_parts = [p for p in parts if p.get("basis_type") == "human_review_constraints"]
    assert len(constraint_parts) == 1
    assert "免报A" in constraint_parts[0]["text"]
    assert constraint_parts[0]["priority"] == 5


def test_basis_sections_no_constraints_when_kb_empty():
    from app.api import review as review_mod

    spec_texts = {"human_review_kb": "", "cn_style": "x", "en_style": "", "common_errors": ""}
    parts = review_mod._build_ai_review_basis_sections(spec_texts, "cn")
    assert all(p.get("basis_type") != "human_review_constraints" for p in parts)
