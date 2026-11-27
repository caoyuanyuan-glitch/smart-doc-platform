"""Benchmark legacy vs optimized translation-memory matching on a large memory library.

Run from the backend directory:
    python benchmark_memory_matching.py
"""

import importlib
import os
import random
import subprocess
import sys
import time
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.api import translation as optimized  # noqa: E402

# Materialize the pre-optimization version from git so the comparison is reproducible
# without keeping a duplicate 5000-line module in the repository.
LEGACY_MODULE = "app.api._benchmark_legacy_translation"
LEGACY_PATH = BACKEND_ROOT / "app" / "api" / "_benchmark_legacy_translation.py"
_legacy_created = False
if not LEGACY_PATH.exists():
    source = subprocess.run(
        ["git", "show", "62002fd:backend/app/api/translation.py"],
        cwd=str(REPO_ROOT), capture_output=True, text=True, check=True,
    ).stdout
    LEGACY_PATH.write_text(source, encoding="utf-8")
    _legacy_created = True
legacy = importlib.import_module(LEGACY_MODULE)


TOPICS = [
    "温控模块采集温度数据并记录日志",
    "测序仪完成一轮扫描后自动生成报告",
    "样本制备卡在界面上显示下一步按钮",
    "用户点击确认参数后系统开始运行",
    "冷却控制板检测到风扇转速异常",
    " gene sequencer outputs a structured result file ",
    "系统升级完成后需要重新启动服务",
    "校准流程要求在开机前执行自检",
]


def build_memory(size: int):
    entries = []
    for index in range(size):
        topic = TOPICS[index % len(TOPICS)]
        entries.append({
            "source_text": f"章节{index:05d} {topic} 编号{index * 7 % 100000}",
            "translated_text": f"Section {index:05d}: translated {topic.strip()} ref {index * 7 % 100000}",
        })
    return entries


def build_queries(count: int, size: int):
    queries = []
    for index in range(count):
        target = random.randrange(size) if index % 2 == 0 else None
        if target is not None:
            topic = TOPICS[target % len(TOPICS)]
            queries.append(f"章节{target:05d} {topic} 编号{target * 7 % 100000}")
        else:
            queries.append(f"无关查询{index:05d} 用户正在查阅全新的帮助文档主题{index % 97}")
    return queries


def run(module, entries, queries, label):
    started = time.perf_counter()
    bundle = module._build_memory_candidate_bundle(entries)
    build_ms = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    hits = 0
    for query in queries:
        if module._match_memory_candidates(query, bundle, threshold=0.8):
            hits += 1
    match_ms = (time.perf_counter() - started) * 1000
    print(f"{label:12s} bundle={build_ms:8.1f} ms  match={match_ms:9.1f} ms  hits={hits}/{len(queries)}")
    return build_ms + match_ms


def main():
    random.seed(20261126)
    size = int(os.getenv("BENCH_MEMORY_ENTRIES", "5000"))
    query_count = int(os.getenv("BENCH_QUERIES", "200"))
    entries = build_memory(size)
    queries = build_queries(query_count, size)
    print(f"memory entries={size}, queries={query_count}\n")

    legacy_ms = run(legacy, entries, queries, "legacy")
    optimized_ms = run(optimized, entries, queries, "optimized")
    print(f"\nspeedup: {legacy_ms / max(optimized_ms, 0.001):.1f}x")
    if _legacy_created:
        LEGACY_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
