"""Agent 接入平台知识库 · 实测探针（真实 DeepSeek 调用，非 mock）。

说明：本沙箱环境无法写入 ~/.smart-doc-platform/knowledge/（Permission denied），
导致 seed 复制的文件为空。因此这里直接从 seed 源文件读取真实内容构造 documents，
模拟"知识库已正常加载"的状态，验证 RAG 检索→组装→作答链路本身是否正确。
"""
import sys, os
from pathlib import Path

BACKEND = Path(r"C:/Users/caoyuanyuan/WorkBuddy/2026-11-19-15-32-43/smart-doc-platform/backend")
sys.path.insert(0, str(BACKEND))

# 注入 DeepSeek key
for line in Path(r"C:/MyFileAudit/smart-doc-platform/backend/.env").read_text(encoding="utf-8-sig", errors="replace").splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

import app.main  # noqa: F401  触发模型注册
from app.api.qa import (
    _extract_file_content, _rank_document_chunks,
    _build_context_from_sources, _call_ai_qa, _needs_clarification,
)

SEED = BACKEND / "seed" / "knowledge"

# 构造真实 documents（跳过 agent KB 目录，与 _load_qa_documents 的 scope 一致）
documents = []
for p in SEED.rglob("*"):
    if not p.is_file() or p.name.startswith(".") or "AI agent知识库" in str(p):
        continue
    if p.suffix.lower() not in {".md", ".txt", ".docx"}:
        continue
    content = _extract_file_content(str(p), p.suffix.lower().lstrip("."))
    if content and len(content) > 200:
        documents.append({
            "document_id": p.name, "title": p.stem,
            "content": content, "folder_path": str(p.parent.relative_to(SEED)),
        })

print(f"真实知识文档数: {len(documents)}")
print("=" * 70)

QUESTIONS = [
    "测序仪操作手册的图片有什么要求？",
    "技术文档里日期和时间用什么格式？",
    "说明书中危险和警告类提示应该怎么写？",
    "全角标点在术语里怎么用？",          # 期望命中：术语库/全角术语
    "今天天气怎么样？",                   # 期望：知识库无命中 → 应回退
]

for q in QUESTIONS:
    ranked = _rank_document_chunks(q, documents, limit=8)
    clarify = _needs_clarification(q, ranked) if ranked else True
    print(f"\n问题: {q}")
    print(f"  检索命中: {len(ranked)} 条, top_score={ranked[0]['score'] if ranked else 0:.2f}, 需澄清={clarify}")
    if ranked:
        print(f"  最高相关: {ranked[0]['title'][:50]}")
    if not ranked or clarify:
        print("  → 判定: 知识库无有效命中，应回退通用知识")
        continue
    context, sources = _build_context_from_sources(ranked)
    result = _call_ai_qa(q, context, [s["title"] for s in sources])
    ans = (result or {}).get("answer", "")
    print(f"  → RAG 回答: {ans[:220].replace(chr(10), ' ')}")
    print(f"  → 来源数: {len(sources)}, 首条: {sources[0]['title'][:40] if sources else 'N/A'}")

print("\n" + "=" * 70)
print("探针完成")
