"""自主学习链路测试：候选规则默认禁用、人工确认后作为审核依据注入。

安全约束：
  - 学习规则 regex 恒为 (?!)，不产生任何正则检出；
  - 只有 description 带 [已启用] 前缀才作为审核依据 section；
  - 注入的是抽象检测要点，不含具体文档错误原文。
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.rule import Rule
from app.review_engine import learned_rules as lr


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = session_local()
    try:
        yield db
    finally:
        db.close()


def test_rule_no_is_stable_and_prefixed():
    a = lr.make_rule_no("cn", "单位前缺空格", "40℃")
    b = lr.make_rule_no("cn", "单位前缺空格", "40℃")
    assert a == b
    assert a.startswith("LR-")


def test_disabled_by_default():
    assert lr.DISABLED_REGEX == r"(?!)"
    assert not lr.is_enabled("数字与单位间保留空格")
    assert lr.is_enabled("[已启用]数字与单位间保留空格")
    assert lr.strip_enabled_prefix("[已启用]数字与单位间保留空格") == "数字与单位间保留空格"


def test_enable_disable_roundtrip(db_session):
    """模拟 convert -> enable -> disable 的状态变化（直接操作模型，验证约定成立）。"""
    rule = Rule(
        rule_no=lr.make_rule_no("cn", "测试意见", "测试原文"),
        category="单位/空格",
        description=lr.abstract_hint("单位/空格"),
        regex=lr.DISABLED_REGEX,
        severity="general",
        language="cn",
    )
    db_session.add(rule)
    db_session.commit()
    assert not lr.is_enabled(rule.description)
    assert rule.regex == r"(?!)"

    rule.description = lr.ENABLED_PREFIX + rule.description
    db_session.commit()
    assert lr.is_enabled(rule.description)

    sections = lr.load_enabled_sections(db_session)
    assert any(s.get("basis_type") == "learned_rule" for s in sections)

    rule.description = lr.strip_enabled_prefix(rule.description)
    db_session.commit()
    assert not any(
        s.get("label", "").startswith("人工学习规则")
        and "数字" in s.get("label", "")
        for s in lr.load_enabled_sections(db_session)
    )


def test_abstract_hint_has_no_specific_error():
    """抽象要点不得含具体文档错误（防照搬臆造）。"""
    for category, hint in lr.CATEGORY_HINT.items():
        assert "步骤3" not in hint
        assert "H-020" not in hint
