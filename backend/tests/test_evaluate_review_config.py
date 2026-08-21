import json

from app.review_engine.annotation_baseline import HumanAnnotation
from scripts import evaluate_review


def test_as_list_wraps_scalar_values():
    assert evaluate_review._as_list("baseline.md") == ["baseline.md"]
    assert evaluate_review._as_list(["a", "b"]) == ["a", "b"]


def test_evaluate_annotation_filters_supports_allowed_misses_and_false_positives():
    annotations = [
        HumanAnnotation(
            file="doc-a.md",
            page="1",
            annotation_type="批注",
            author="Tina",
            comment="建议优化表达",
            selected_text="原句",
            context="上下文",
            category="表达与句式",
            layer="ai_assisted",
            expected_rule="AI-STYLE-001",
        )
    ]

    kept, ignored = evaluate_review._evaluate_annotation_filters(annotations, ["AI-STYLE-001"], ["R029"])

    assert kept == []
    assert ignored == [
        {
            "file": "doc-a.md",
            "page": "1",
            "annotation_type": "批注",
            "author": "Tina",
            "comment": "建议优化表达",
            "selected_text": "原句",
            "context": "上下文",
            "category": "表达与句式",
            "layer": "ai_assisted",
            "expected_rule": "AI-STYLE-001",
        }
    ]


def test_batch_evaluate_from_config_preserves_suite_fields(tmp_path, monkeypatch):
    config = {
        "documents": [
            {
                "name": "doc-a",
                "review_id": 101,
                "standard_answers": ["baseline-a.md", "baseline-b.md"],
                "allowed_misses": ["AI-STYLE-001"],
                "explicit_false_positives": ["R029"],
            },
            {
                "name": "doc-b",
                "review_id": 202,
                "standard_answers": ["baseline-c.md"],
            },
        ],
        "thresholds": {
            "max_noop_rate": 0.1,
            "max_numeric_change_rate": 0.0,
            "max_protected_change_rate": 0.0,
            "min_high_value_rate": 0.2,
        },
    }
    config_path = tmp_path / "review-suite.json"
    config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

    seen = []

    def fake_evaluate_suite_document(doc_cfg, markers):
        seen.append(doc_cfg)
        return {
            "review_id": doc_cfg["review_id"],
            "total": 1,
            "noop_suggestions": 0,
            "numeric_changed": 0,
            "protected_meaning_changed": 0,
            "effectiveness": {
                "high_value_rate": 0.5,
                "high_value_items": [],
                "low_value_noise_items": [],
            },
            "marker_hits": {},
            "config": doc_cfg,
            "suite_filters": {},
        }

    monkeypatch.setattr(evaluate_review, "evaluate_suite_document", fake_evaluate_suite_document)

    result = evaluate_review.batch_evaluate_from_config(str(config_path), ["marker"])

    assert result["summary"] == {"total": 2, "passed": 2, "failed": 0, "regressions": 0}
    assert seen[0]["standard_answers"] == ["baseline-a.md", "baseline-b.md"]
    assert seen[0]["allowed_misses"] == ["AI-STYLE-001"]
    assert seen[0]["explicit_false_positives"] == ["R029"]
    assert result["results"][0]["config"]["standard_answers"] == ["baseline-a.md", "baseline-b.md"]
