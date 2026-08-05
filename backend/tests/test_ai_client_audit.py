from app.utils.ai_client import AIClient


def test_merge_audit_issue_sets_boosts_consensus_for_matched_items():
    client = AIClient.__new__(AIClient)

    primary = [{
        "severity": "serious",
        "category": "术语",
        "rule": "AI-TERM",
        "chapter": "章节1",
        "original_text": "Buffer A",
        "context": "Buffer A should stay consistent",
        "suggestion": "Buffer A",
        "description": "术语需保持一致",
        "audit_basis": "术语规则",
        "confidence": 82,
        "source": "ai",
        "position": "10-18",
    }]
    secondary = [{
        "severity": "general",
        "category": "术语",
        "rule": "AI-TERM",
        "chapter": "章节1",
        "original_text": "Buffer A",
        "context": "Buffer A should stay consistent",
        "suggestion": "Buffer A",
        "description": "同一术语需要统一",
        "audit_basis": "术语规则",
        "confidence": 90,
        "source": "ai",
        "position": "10-18",
    }]

    merged = client._merge_audit_issue_sets(primary, secondary, "qwen", "deepseek")

    assert len(merged) == 1
    assert merged[0]["source_models"] == ["qwen", "deepseek"]
    assert merged[0]["consensus_score"] >= 98
    assert merged[0]["severity"] == "serious"


def test_merge_audit_issue_sets_downgrades_low_confidence_single_model_issue():
    client = AIClient.__new__(AIClient)

    primary = [{
        "severity": "serious",
        "category": "信息完整性",
        "rule": "AI-MISS",
        "chapter": "章节2",
        "original_text": "sample",
        "context": "sample text",
        "suggestion": "补充说明",
        "description": "信息可能缺失",
        "audit_basis": "完整性规则",
        "confidence": 78,
        "source": "ai",
        "position": "20-26",
    }]

    merged = client._merge_audit_issue_sets(primary, [], "qwen", "deepseek")

    assert len(merged) == 1
    assert merged[0]["source_models"] == ["qwen"]
    assert merged[0]["severity"] == "general"


def test_audit_document_runs_qwen_then_deepseek(monkeypatch):
    client = AIClient.__new__(AIClient)
    client.qwen_client = object()
    client.deepseek_client = object()

    calls = []

    def fake_run_provider_audit(provider_key, messages, content, request_label=None, review_id=None):
        calls.append((provider_key, request_label, review_id, content))
        if provider_key == "qwen":
            return [{
                "severity": "serious",
                "category": "术语",
                "rule": "AI-TERM",
                "chapter": "术语",
                "original_text": "Buffer A",
                "context": "Buffer A mismatch",
                "suggestion": "Buffer B",
                "description": "术语不一致",
                "audit_basis": "术语规则",
                "confidence": 84,
                "source": "ai",
                "position": "1-8",
                "source_models": ["qwen"],
                "consensus_score": 84,
            }]
        return [{
            "severity": "general",
            "category": "术语",
            "rule": "AI-TERM",
            "chapter": "术语",
            "original_text": "Buffer A",
            "context": "Buffer A mismatch",
            "suggestion": "Buffer B",
            "description": "术语不一致",
            "audit_basis": "术语规则",
            "confidence": 88,
            "source": "ai",
            "position": "1-8",
            "source_models": ["deepseek"],
            "consensus_score": 88,
        }]

    monkeypatch.setattr("app.utils.ai_client.build_system_prompt", lambda: "BASE")
    monkeypatch.setattr(client, "_run_provider_audit", fake_run_provider_audit)

    result = client.audit_document("This is Buffer A mismatch.", language="en", audit_basis="basis", review_id=9)

    assert [call[0] for call in calls] == ["qwen", "deepseek"]
    assert calls[1][1] == "review.audit_chunk.deepseek"
    assert result["issues"][0]["source_models"] == ["qwen", "deepseek"]
    assert result["issues"][0]["consensus_score"] >= 92
