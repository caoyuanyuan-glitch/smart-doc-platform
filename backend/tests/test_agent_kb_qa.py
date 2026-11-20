"""Agent 知识库问答分流测试。

不依赖真实 DB/模型/知识库文件：用 monkeypatch 替换 _answer_from_knowledge
和 _answer_general，验证 _dispatch 的 qa 分支在"命中知识库"与"回退通用"两种
情况下都返回正确结构（sources / answer_source / reply 后缀）。
"""
import pytest

from app.api import agent


def test_qa_knowledge_hit_returns_sources(monkeypatch):
    """知识库命中：reply 带来源说明，answer_source=knowledge，携带 sources。"""
    monkeypatch.setattr(
        agent, "_answer_from_knowledge",
        lambda q, db: {
            "answer": "根据风格指南，日期应使用 YYYY-MM-DD 格式。",
            "sources": [{"title": "写作风格指南", "snippet": "日期格式", "score": 4.5}],
            "hit": True,
        },
    )
    # 命中时不应调用通用回答
    def _should_not_call(*a, **kw):
        raise AssertionError("知识库命中时不应回退到通用回答")
    monkeypatch.setattr(agent, "_answer_general", _should_not_call)

    out = agent._dispatch("qa", {"question": "日期格式怎么写？"}, db=object())
    assert out["intent"] == "qa"
    assert out["answer_source"] == "knowledge"
    assert "来自平台知识库" in out["reply"]
    assert len(out["sources"]) == 1
    assert out["sources"][0]["title"] == "写作风格指南"
    assert out["action"]["type"] == "navigate"
    assert out["action"]["params"]["question"] == "日期格式怎么写？"


def test_qa_no_hit_falls_back_to_general(monkeypatch):
    """知识库无命中：回退通用回答，answer_source=general，sources 为空。"""
    monkeypatch.setattr(agent, "_answer_from_knowledge", lambda q, db: None)
    monkeypatch.setattr(agent, "_answer_general", lambda q: "这是通用知识回答。")

    out = agent._dispatch("qa", {"question": "今天天气怎么样？"}, db=object())
    assert out["answer_source"] == "general"
    assert "通用回答" in out["reply"]
    assert out["sources"] == []


def test_qa_empty_question_shows_intro(monkeypatch):
    """空问题：返回能力介绍，不检索、不调模型。"""
    def _should_not_call(*a, **kw):
        raise AssertionError("空问题不应触发检索或模型调用")
    monkeypatch.setattr(agent, "_answer_from_knowledge", _should_not_call)
    monkeypatch.setattr(agent, "_answer_general", _should_not_call)

    out = agent._dispatch("qa", {"question": ""}, db=object())
    assert out["answer_source"] if "answer_source" in out else True
    assert "六个模块" in out["reply"] or "帮你" in out["reply"]


def test_kb_disabled_returns_none(monkeypatch):
    """关闭开关时 _answer_from_knowledge 直接返回 None（回退通用）。"""
    monkeypatch.setattr(agent, "_KB_QA_ENABLED", False)
    out = agent._answer_from_knowledge("日期格式？", db=object())
    assert out is None


def test_kb_no_db_returns_none():
    """没有 db（如某些内部调用）时安全返回 None。"""
    assert agent._answer_from_knowledge("日期格式？", db=None) is None
