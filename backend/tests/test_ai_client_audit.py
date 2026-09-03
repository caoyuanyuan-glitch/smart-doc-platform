from app.utils import ai_client as ai_client_module
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
    client.default_provider = "qwen"
    client.disabled_providers = set()
    client.qwen_client = object()
    client.kimi_client = None
    client.deepseek_client = object()
    client.arkclaw_client = None
    client.mcai_proxy_client = None
    client.proxy_client = None

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


def test_audit_document_falls_back_to_kimi_when_qwen_returns_no_issues(monkeypatch):
    client = AIClient.__new__(AIClient)
    client.default_provider = "qwen"
    client.disabled_providers = set()
    client.qwen_client = object()
    client.kimi_client = object()
    client.deepseek_client = None
    client.arkclaw_client = None
    client.mcai_proxy_client = None
    client.proxy_client = None

    calls = []

    def fake_run_provider_audit(provider_key, messages, content, request_label=None, review_id=None):
        calls.append((provider_key, request_label, review_id, content))
        if provider_key == "qwen":
            return []
        return [{
            "severity": "general",
            "category": "语法表达",
            "rule": "AI-GRAMMAR",
            "chapter": "章节1",
            "original_text": "如操作不当或不避免",
            "context": "如操作不当或不避免",
            "suggestion": "如未按照说明进行操作",
            "description": "搭配不通顺",
            "audit_basis": "审核依据",
            "confidence": 91,
            "source": "ai",
            "position": "1-10",
            "source_models": [provider_key],
            "consensus_score": 91,
        }]

    monkeypatch.setattr("app.utils.ai_client.build_system_prompt", lambda: "BASE")
    monkeypatch.setattr(client, "_run_provider_audit", fake_run_provider_audit)

    result = client.audit_document("如操作不当或不避免", language="cn", audit_basis="basis", review_id=10)

    assert [call[0] for call in calls] == ["qwen", "kimi"]
    assert result["issues"][0]["source_models"] == ["kimi"]


def test_run_provider_audit_uses_configurable_max_tokens(monkeypatch):
    client = AIClient.__new__(AIClient)
    captured = {}

    def fake_call_qwen(messages, max_tokens=2048, temperature=0.3, request_label=None, review_id=None):
        captured["max_tokens"] = max_tokens
        return '{"issues": []}'

    monkeypatch.setenv("AI_AUDIT_MAX_TOKENS", "512")
    monkeypatch.setattr(client, "call_qwen", fake_call_qwen)

    result = client._run_provider_audit("qwen", [], "text")

    assert result == []
    assert captured["max_tokens"] == 512


def test_qwen3_request_disables_thinking_by_default(monkeypatch):
    client = AIClient.__new__(AIClient)
    client.qwen_model = "qwen3.7-flash"
    client.qwen_enable_thinking = False

    monkeypatch.delenv("QWEN_ENABLE_THINKING", raising=False)

    payload = client._build_qwen_request_kwargs(model=client.qwen_model, messages=[])

    assert payload["extra_body"]["enable_thinking"] is False


def test_qwen_request_respects_enable_thinking_env(monkeypatch):
    client = AIClient.__new__(AIClient)
    client.qwen_model = "qwen-max"
    client.qwen_enable_thinking = True

    monkeypatch.setenv("QWEN_ENABLE_THINKING", "true")

    payload = client._build_qwen_request_kwargs(model=client.qwen_model, messages=[])

    assert payload["extra_body"]["enable_thinking"] is True


def test_build_audit_prompt_payload_english_skips_chinese_base_prompt(monkeypatch):
    client = AIClient.__new__(AIClient)

    monkeypatch.setattr("app.utils.ai_client.build_system_prompt", lambda: "中文静态规则")
    monkeypatch.setattr("app.utils.ai_client.PROMPT_BUILDER_FALLBACK_ACTIVE", False)

    payload = client.build_audit_prompt_payload(
        "Reviewing parameters",
        language="en",
        audit_basis="basis",
        chapter_context={"document_name": "demo.pdf"},
    )

    assert "中文静态规则" not in payload["system_prompt"]
    assert "Unicode-equivalent character differences" in payload["system_prompt"]
    assert "severity=suggestion" in payload["system_prompt"]
    assert "observations" in payload["user_prompt"]


def test_audit_document_does_not_rechunk_large_content(monkeypatch):
    client = AIClient.__new__(AIClient)
    client.default_provider = "qwen"
    client.disabled_providers = set()
    client.qwen_client = object()
    client.kimi_client = None
    client.deepseek_client = None
    client.arkclaw_client = None
    client.mcai_proxy_client = None
    client.proxy_client = None

    captured = []

    def fake_run_provider_audit(provider_key, messages, content, request_label=None, review_id=None):
        captured.append((provider_key, len(content), request_label, review_id))
        return []

    monkeypatch.setattr(
        client,
        "build_audit_prompt_payload",
        lambda content, language=None, audit_basis="", chapter_context=None, snippet_review=False, **kwargs: {
            "system_prompt": "SYS",
            "user_prompt": f"USER:{len(content)}",
        },
    )
    monkeypatch.setattr(client, "_run_provider_audit", fake_run_provider_audit)

    result = client.audit_document("A" * 9000, language="en", audit_basis="basis", review_id=7)

    assert result["issues"] == []
    assert result["observations"] == []
    assert captured == [("qwen", 9000, "review.audit_chunk", 7)]


def test_provider_limits_default_to_single_retry_and_45s_read_timeout(monkeypatch):
    monkeypatch.delenv("AI_PROVIDER_MAX_ATTEMPTS", raising=False)
    monkeypatch.delenv("AI_PROVIDER_READ_TIMEOUT", raising=False)

    timeout = ai_client_module._provider_http_timeout()

    assert ai_client_module._provider_max_attempts() == 2
    assert timeout.read == 45.0


def test_provider_limits_can_be_overridden(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER_MAX_ATTEMPTS", "4")
    monkeypatch.setenv("AI_PROVIDER_READ_TIMEOUT", "20")

    timeout = ai_client_module._provider_http_timeout()

    assert ai_client_module._provider_max_attempts() == 4
    assert timeout.read == 20.0


def test_normalize_audit_issues_keeps_mid_confidence_for_human_review():
    client = AIClient.__new__(AIClient)
    issues = client.normalize_audit_issues(
        [{
            "original": "Buffer A",
            "expected": "Buffer B",
            "description": "术语可能不一致",
            "confidence": 62,
            "severity": "general",
            "category": "术语一致性",
        }],
        "Use Buffer A before mixing.",
    )
    assert len(issues) == 1
    assert issues[0]["needs_human_review"] is True


def test_normalize_audit_observations_dedupes_by_title():
    client = AIClient.__new__(AIClient)
    observations = client.normalize_audit_observations([
        {"title": "占位符过多", "description": "低置信", "confidence": 55, "category": "格式排版"},
        {"title": "占位符过多", "description": "高置信", "confidence": 88, "category": "格式排版"},
        {"title": "引用断裂", "description": "见图 3", "confidence": 70, "category": "编号引用"},
    ])
    assert len(observations) == 2
    first = next(item for item in observations if item["title"] == "占位符过多")
    assert first["confidence"] == 88
    assert first["description"] == "高置信"
