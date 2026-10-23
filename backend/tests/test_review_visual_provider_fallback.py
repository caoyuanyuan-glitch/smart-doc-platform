# -*- coding: utf-8 -*-
"""视觉链回归守卫（任务 4 + 任务 5）。

历史缺陷：
1) map_visual_status 把 401 / 超时等 provider 故障判成 failed，
   而回退链只在 provider_unavailable 时继续，导致 kimi 一失败就无人接管；
2) review.py 的 _verify_review_issue_visually 里有 `if provider != "kimi": continue`，
   即使 qwen 客户端已就绪也会被无条件跳过 —— qwen 被结构性短路。
"""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.review_engine.visual import (  # noqa: E402
    map_visual_status,
    visual_provider_chain,
)

PROVIDER_FAULT_CASES = [
    "401 invalid api key",
    "HTTP 401 Unauthorized",
    "403 rate limit exceeded",
    "429 Too Many Requests",
    "connection reset by peer",
    "Request timed out after 40s",
    "503 service unavailable",
    "insufficient balance",
]

RENDER_FAILURE_CASES = [
    "render_failed: page rasterization error",
    "render error: empty pixmap",
]


def test_provider_faults_map_to_provider_unavailable():
    """provider 侧故障必须归 provider_unavailable，否则回退链中止。"""
    for reason in PROVIDER_FAULT_CASES:
        assert map_visual_status("error", reason) == "provider_unavailable", reason
        assert map_visual_status("failed", reason) == "provider_unavailable", reason


def test_render_failures_stay_failed():
    """渲染失败必须仍是 failed，与 provider 故障保持可区分。"""
    for reason in RENDER_FAILURE_CASES:
        assert map_visual_status("failed", reason) == "failed", reason
        assert map_visual_status("error", reason) == "failed", reason


def test_provider_fault_preferred_over_generic_error():
    """decision=error 且 reason 含 provider 信号时，优先判 provider 故障。"""
    assert map_visual_status("error", "401 invalid api key") == "provider_unavailable"


def test_existing_status_mapping_unchanged():
    """既有映射语义不得被本次修改破坏。"""
    assert map_visual_status("confirm", "") == "verified"
    assert map_visual_status("reject", "") == "rejected"
    assert map_visual_status("not_required", "") == "not_required"
    assert map_visual_status("skipped", "") == "skipped"
    assert map_visual_status("provider_unavailable", "") == "provider_unavailable"
    assert map_visual_status("verified", "") == "verified"


def test_provider_chain_keeps_all_configured_providers():
    """qwen 必须仍在视觉链中（产品要求保留 qwen/kimi/deepseek 三选一）。"""
    chain = visual_provider_chain()
    assert "qwen" in chain, f"qwen 被移出视觉链：{chain}"
    assert len(chain) == len(set(chain)), f"视觉链存在重复：{chain}"


def test_review_visual_verifier_has_no_provider_hardcode():
    """回退链里不得再出现 `if provider != "kimi": continue` 式短路。"""
    source = (BACKEND / "app" / "api" / "review.py").read_text(encoding="utf-8")
    # 只看真实代码行，排除注释（注释里会引用旧写法以便对照）。
    code_lines = [
        line for line in source.splitlines()
        if not line.lstrip().startswith("#")
    ]
    code = "\n".join(code_lines)
    assert 'provider != "kimi"' not in code, "视觉回退链仍硬编码跳过非 kimi provider"
    assert "vision_adapter_missing" not in code, "旧的 qwen 跳过标记仍在"


def test_visual_client_dispatch_supports_multiple_providers():
    """视觉核验函数必须支持 provider 分派，且按 provider 透传。"""
    source = (BACKEND / "app" / "utils" / "ai_client.py").read_text(encoding="utf-8")
    assert "def _visual_client_for" in source
    assert "def _visual_model_for" in source
    assert 'provider="kimi"' in source, "verify_review_issue_from_image 未暴露 provider 参数"


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
