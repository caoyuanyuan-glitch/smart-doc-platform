"""误报记忆库回归守卫。

审核人每标记一次「误报」，该问题的签名就沉淀进 `false_positive_memory`（enabled=1）。
已沉淀的误报不得在后续审核中复现，否则代表 precision 下限被突破。

本文件包含两类用例：
- 真实库守卫：遍历当前库中 status != false_positive 的 Issue，断言没有命中已启用签名。
- 隔离用例：用内存库验证守卫生效（命中会报警）且 enabled=0 的条目不参与拦截。
"""

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.review import _issue_judgment_signature, _issue_judgment_signatures
from app.crud.review import list_false_positive_memory_signatures
from app.database import Base, SessionLocal
from app.models.false_positive_memory import FalsePositiveMemory
from app.models.issue import Issue


def _reappearance_hits(db, signatures):
    """返回当前库中命中已启用误报签名、且自身未被标记为误报的 Issue。"""
    normalized = {str(signature or "").strip().lower() for signature in signatures if str(signature or "").strip()}
    if not normalized:
        return []
    hits = []
    for issue in db.query(Issue).all():
        if str(getattr(issue, "status", "") or "").lower() == "false_positive":
            continue
        matched = {signature.lower() for signature in _issue_judgment_signatures(issue)} & normalized
        if matched:
            hits.append({
                "id": issue.id,
                "rule": str(getattr(issue, "rule", "") or ""),
                "original_text": str(getattr(issue, "original_text", "") or "")[:80],
                "signature": sorted(matched)[0],
            })
    return hits


def test_no_enabled_false_positive_memory_reappears():
    """已沉淀的误报不得在后续审核中复现（precision 下限守卫）。"""
    db = SessionLocal()
    try:
        if not inspect(db.get_bind()).has_table(FalsePositiveMemory.__tablename__):
            pytest.skip("误报记忆表不存在，跳过")
        signatures = list_false_positive_memory_signatures(db)
        if not signatures:
            pytest.skip("误报记忆库为空，跳过")
        hits = _reappearance_hits(db, signatures)
    finally:
        db.close()

    assert not hits, f"已沉淀误报复发：{hits[:10]}"


@pytest.fixture
def memory_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def _seed_issue(db, *, status, rule="R013", category="格式规范", original_text="sample text"):
    issue = Issue(
        review_id=1,
        severity="general",
        category=category,
        rule=rule,
        original_text=original_text,
        status=status,
    )
    db.add(issue)
    db.commit()
    db.refresh(issue)
    return issue


def _seed_memory(db, signature, *, enabled=True):
    db.add(FalsePositiveMemory(
        source_issue_id=0,
        signature=signature,
        rule="R013",
        category="格式规范",
        original_text="sample text",
        enabled=enabled,
    ))
    db.commit()


def test_enabled_memory_hit_is_reported(memory_db):
    """守卫生效性自检：命中已启用签名时必须被检出，否则该用例形同虚设。"""
    issue = _seed_issue(memory_db, status="pending")
    _seed_memory(memory_db, _issue_judgment_signature(issue))

    signatures = list_false_positive_memory_signatures(memory_db)
    hits = _reappearance_hits(memory_db, signatures)

    assert len(signatures) == 1
    assert [hit["id"] for hit in hits] == [issue.id]


def test_disabled_memory_is_not_enforced(memory_db):
    """enabled=0 的条目已撤销，不参与拦截，避免误伤。"""
    issue = _seed_issue(memory_db, status="pending")
    _seed_memory(memory_db, _issue_judgment_signature(issue), enabled=False)

    signatures = list_false_positive_memory_signatures(memory_db)

    assert signatures == set()
    assert _reappearance_hits(memory_db, signatures) == []


def test_false_positive_issue_itself_is_not_a_reappearance(memory_db):
    """被标记为误报的源问题不应被算作复发。"""
    issue = _seed_issue(memory_db, status="false_positive")
    _seed_memory(memory_db, _issue_judgment_signature(issue))

    signatures = list_false_positive_memory_signatures(memory_db)

    assert _reappearance_hits(memory_db, signatures) == []
