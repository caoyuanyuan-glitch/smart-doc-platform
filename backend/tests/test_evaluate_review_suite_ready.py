"""准确率套件应按 baseline 定位，缺记录时明确报"未就绪"。

回归背景：套件原先硬绑本地 `review_id`，换机器 / CI / 重建库即失效；
`evaluate_review.py` 对缺失记录静默产出 `recall = 0.0` + `recall_ok = False`，
会被误读成"准确率不达标"。
"""

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.document import Document
from app.models.review import Review
from scripts import evaluate_review


@pytest.fixture
def in_memory_session(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(evaluate_review, "SessionLocal", session_factory)
    try:
        yield session_factory
    finally:
        Base.metadata.drop_all(bind=engine)


def test_resolve_suite_document_reports_not_ready_when_db_empty(in_memory_session):
    """库中无对应记录时必须返回 suite_not_ready，而不是编造一个 review_id。"""
    cfg = {
        "name": "gospatial_v2_24_en",
        "review_id": 20,
        "baseline": "goldset/human_baseline_gospatial_v2_24.md",
    }

    assert evaluate_review.resolve_suite_document(cfg) == (None, "suite_not_ready")


def test_resolve_suite_document_matches_by_baseline_filename(in_memory_session):
    """review_id 不存在时，退回按 baseline 文件名匹配库中文档。"""
    db = in_memory_session()
    document = Document(filename="H-020-000999-gospatial_v2_24_manual.pdf", status="completed")
    db.add(document)
    db.commit()
    db.refresh(document)
    review = Review(document_id=document.id, status="completed", mode="full")
    db.add(review)
    db.commit()
    db.refresh(review)
    db.close()

    cfg = {
        "name": "gospatial_v2_24_en",
        "review_id": 99999,
        "baseline": "goldset/human_baseline_gospatial_v2_24.md",
    }

    assert evaluate_review.resolve_suite_document(cfg) == (review.id, "ok")


def test_resolve_suite_document_ignores_mismatched_review_id(in_memory_session):
    """review_id 存在但指向别的文档时，不得错配成该文档的审核结果。"""
    db = in_memory_session()
    document = Document(filename="unrelated-manual.pdf", status="completed")
    db.add(document)
    db.commit()
    db.refresh(document)
    review = Review(document_id=document.id, status="completed", mode="full")
    db.add(review)
    db.commit()
    db.refresh(review)
    db.close()

    cfg = {
        "name": "gospatial_v2_24_en",
        "review_id": review.id,
        "baseline": "goldset/human_baseline_gospatial_v2_24.md",
    }

    assert evaluate_review.resolve_suite_document(cfg) == (None, "suite_not_ready")


def test_resolve_suite_document_accepts_review_id_without_baseline(in_memory_session):
    """未提供 baseline 时无法校验，review_id 回退为唯一定位手段。"""
    db = in_memory_session()
    document = Document(filename="anything.pdf", status="completed")
    db.add(document)
    db.commit()
    db.refresh(document)
    review = Review(document_id=document.id, status="completed", mode="full")
    db.add(review)
    db.commit()
    db.refresh(review)
    db.close()

    assert evaluate_review.resolve_suite_document({"review_id": review.id}) == (review.id, "ok")


def test_batch_marks_documents_suite_not_ready_without_recall_checks(in_memory_session, tmp_path):
    """缺记录时输出 suite_not_ready，且不得产出 recall_ok=false 之类的"不达标"误导。"""
    config = {
        "documents": [
            {
                "name": "gospatial_v2_24_en",
                "review_id": 20,
                "baseline": "goldset/human_baseline_gospatial_v2_24.md",
            },
            {
                "name": "e25rs_cn",
                "review_id": 21,
                "baseline": "goldset/human_baseline_e25rs_cn.json",
            },
        ],
        "thresholds": {"min_recall": 0.88, "min_precision": 0.88},
    }
    config_path = tmp_path / "suite.json"
    config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

    result = evaluate_review.batch_evaluate_from_config(str(config_path), ["marker"])

    summary = result["summary"]
    assert summary["suite_not_ready"] == 2
    assert summary["regressions"] == 0
    assert summary["all_documents_ready"] is False
    assert summary["all_documents_meet"] is False
    for item in result["results"]:
        assert item["status"] == "suite_not_ready"
        assert item["passed"] is False
        # 关键：不得出现"准确率不达标"的判据
        assert "recall_ok" not in item["checks"]
        assert "precision_ok" not in item["checks"]
