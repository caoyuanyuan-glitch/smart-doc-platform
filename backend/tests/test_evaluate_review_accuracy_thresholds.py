"""准确率阈值卡口测试（TDD）。

对应《代码修订指令》改动 1。这些用例在改动落地前会失败，属于预期行为；
改动完成后应全部通过。

覆盖三点：
1. recall / precision 达标 -> 判通过
2. precision 低于阈值 -> 判不通过
3. 配了阈值但没给 gold set -> 必须判不通过（杜绝"没测就算过"）
"""

import json

from scripts import evaluate_review


def _write_suite(tmp_path, thresholds, documents):
    path = tmp_path / "suite.json"
    path.write_text(
        json.dumps({"documents": documents, "thresholds": thresholds}, ensure_ascii=False),
        encoding="utf-8",
    )
    return str(path)


def _fake_result(human_baseline=None):
    result = {
        "total": 10,
        "noop_suggestions": 0,
        "numeric_changed": 0,
        "protected_meaning_changed": 0,
        "effectiveness": {"high_value_rate": 0.5},
    }
    if human_baseline is not None:
        result["human_baseline"] = human_baseline
    return result


def _run(tmp_path, monkeypatch, fake, thresholds):
    monkeypatch.setattr(
        evaluate_review,
        "evaluate_suite_document",
        lambda doc_cfg, markers: fake,
    )
    cfg = _write_suite(tmp_path, thresholds, [{"name": "doc-1", "review_id": 1}])
    return evaluate_review.batch_evaluate_from_config(cfg, [])


def test_recall_and_precision_meeting_threshold_pass(tmp_path, monkeypatch):
    fake = _fake_result({
        "recall": 0.92,
        "precision": 0.90,
        "strict_recall": 0.91,
        "strict_precision": 0.89,
        "f1": 0.90,
    })
    result = _run(tmp_path, monkeypatch, fake, {"min_recall": 0.88, "min_precision": 0.88})

    assert result["summary"]["passed"] == 1
    assert result["summary"]["failed"] == 0
    doc = result["results"][0]
    # 主口径应取严格版
    assert doc["metrics"]["recall"] == 0.91
    assert doc["metrics"]["precision"] == 0.89
    assert doc["checks"]["recall_ok"] is True
    assert doc["checks"]["precision_ok"] is True


def test_precision_below_threshold_fails(tmp_path, monkeypatch):
    """准确率不足时，即使其它质量项全绿也必须判失败。"""
    fake = _fake_result({
        "recall": 0.95,
        "precision": 0.80,
        "strict_recall": 0.95,
        "strict_precision": 0.80,
        "f1": 0.87,
    })
    result = _run(tmp_path, monkeypatch, fake, {"min_recall": 0.88, "min_precision": 0.88})

    assert result["summary"]["passed"] == 0
    assert result["summary"]["regressions"] == 1
    assert result["results"][0]["checks"]["precision_ok"] is False


def test_recall_below_threshold_fails(tmp_path, monkeypatch):
    fake = _fake_result({
        "recall": 0.75,
        "precision": 0.98,
        "strict_recall": 0.75,
        "strict_precision": 0.98,
    })
    result = _run(tmp_path, monkeypatch, fake, {"min_recall": 0.88, "min_precision": 0.88})

    assert result["summary"]["passed"] == 0
    assert result["results"][0]["checks"]["recall_ok"] is False


def test_missing_gold_set_fails_when_thresholds_configured(tmp_path, monkeypatch):
    """配了准确率阈值却没挂 gold set：必须判不通过，不能"没测就算过"。"""
    fake = _fake_result(human_baseline=None)
    result = _run(tmp_path, monkeypatch, fake, {"min_recall": 0.88, "min_precision": 0.88})

    assert result["summary"]["passed"] == 0
    assert result["results"][0]["checks"]["recall_ok"] is False
    assert result["results"][0]["checks"]["precision_ok"] is False
    assert result["results"][0]["metrics"]["has_gold_set"] is False


def test_no_thresholds_configured_keeps_legacy_behaviour(tmp_path, monkeypatch):
    """未配准确率阈值时保持既有行为，不引入回归。"""
    fake = _fake_result({
        "recall": 0.10,
        "precision": 0.10,
        "strict_recall": 0.10,
        "strict_precision": 0.10,
    })
    result = _run(tmp_path, monkeypatch, fake, {"max_noop_rate": 0.05})

    assert result["summary"]["passed"] == 1
    assert "recall_ok" not in result["results"][0]["checks"]


def test_per_document_metrics_and_summary_aggregate(tmp_path, monkeypatch):
    """改动 3：多文档场景需输出每份文档的 recall/precision 与聚合值。

    用「一份高分 + 一份低分」验证聚合不会掩盖单份不达标。
    """
    docs = {
        1: {"recall": 0.99, "precision": 0.99, "strict_recall": 0.99, "strict_precision": 0.99},
        2: {"recall": 0.60, "precision": 0.99, "strict_recall": 0.60, "strict_precision": 0.99},
    }

    def fake_eval(doc_cfg, markers):
        return _fake_result(docs[doc_cfg["review_id"]])

    monkeypatch.setattr(evaluate_review, "evaluate_suite_document", fake_eval)
    cfg = _write_suite(
        tmp_path,
        {"min_recall": 0.88, "min_precision": 0.88},
        [{"name": "good", "review_id": 1}, {"name": "bad", "review_id": 2}],
    )
    result = evaluate_review.batch_evaluate_from_config(cfg, [])

    summary = result["summary"]
    assert summary["total"] == 2
    assert summary["passed"] == 1
    assert summary["failed"] == 1
    assert summary["all_documents_meet"] is False
    # 均值会被高分拉高，因此必须靠 all_documents_meet 兜底
    assert summary["mean_recall"] > 0.7
    assert {m["name"]: m["recall"] for m in summary["per_document"]} == {"good": 0.99, "bad": 0.6}
