"""实测 Agent 智能度：意图识别准确率 + 参数抽取 + 问答质量。

用真实 AI 分类（DeepSeek），不用 mock。每组给"期望意图"，统计命中率。
"""
import os
import sys
from pathlib import Path

BACKEND = Path(r"C:/Users/caoyuanyuan/WorkBuddy/2026-11-19-15-32-43/smart-doc-platform/backend")
sys.path.insert(0, str(BACKEND))
os.chdir(str(BACKEND))
for line in Path(r"C:/MyFileAudit/smart-doc-platform/backend/.env").read_text(encoding="utf-8-sig", errors="replace").splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

from app.api.agent import _classify, _dispatch, _keyword_intent  # noqa: E402

# (用户话语, 期望意图, 说明)
CASES = [
    # 标准表述
    ("帮我润色这段话", "polish", "标准-润色"),
    ("审核这份文档", "review", "标准-审核"),
    ("对比两个版本", "compare", "标准-对比"),
    ("转成 markdown", "convert", "标准-转换"),
    ("生成一篇使用说明书", "generate", "标准-生成"),
    ("知识库里怎么设置参数", "qa", "标准-问答"),
    # 口语化 / 模糊
    ("这段写得不太顺，能帮我改改吗", "polish", "口语-润色"),
    ("这个文档有没有问题", "review", "口语-审核"),
    ("看看这两版哪里不一样", "compare", "口语-对比"),
    ("把它变成 DITA 格式", "convert", "口语-转换"),
    ("写个操作指南出来", "generate", "口语-生成"),
    ("问一下这个试剂怎么保存", "qa", "口语-问答"),
    # 带参数
    ("帮我润色这段话：请在2℃~8℃条件下保存", "polish", "带参数-润色"),
    ("生成一篇测序仪操作指南，中文的", "generate", "带参数-生成"),
    # 寒暄 / 能力咨询
    ("你好", "chat", "寒暄"),
    ("你能做什么", "chat", "能力咨询"),
    ("谢谢", "chat", "致谢"),
]

print("=" * 70)
print("Agent 意图识别实测（DeepSeek 真实调用）")
print("=" * 70)

hit = 0
results = []
for text, expected, label in CASES:
    classified = _classify(text, None)
    got = classified["intent"]
    ok = got == expected
    hit += ok
    results.append((label, text, expected, got, ok, classified))

for label, text, expected, got, ok, cls in results:
    mark = "OK " if ok else "MISS"
    print(f"[{mark}] {label:12s} 期望={expected:8s} 实际={got:8s} | {text[:28]}")
    if cls.get("text") or cls.get("topic"):
        print(f"        抽取: text={cls.get('text','')[:30]!r} topic={cls.get('topic','')[:30]!r}")

print()
print(f"意图识别准确率: {hit}/{len(CASES)} = {hit/len(CASES):.1%}")

# 关键词兜底对比（不调 AI，看纯关键词能到多少）
kw_hit = sum(1 for text, expected, _ in CASES if _keyword_intent(text) == expected)
print(f"关键词兜底准确率: {kw_hit}/{len(CASES)} = {kw_hit/len(CASES):.1%}")

# 参数抽取检查（带参数的用例）
print()
print("--- 参数抽取检查 ---")
for label, text, expected, got, ok, cls in results:
    if label.startswith("带参数"):
        print(f"{label}: text={cls.get('text','')!r} topic={cls.get('topic','')!r} doc_type={cls.get('doc_type','')!r}")

# 通用问答质量
print()
print("--- 通用问答质量 ---")
for q in ["Docs 和 IFU 有什么区别？", "2℃~8℃ 保存是什么意思？"]:
    answer = _answer = None
    from app.api.agent import _answer_general
    answer = _answer_general(q)
    print(f"Q: {q}")
    print(f"A: {answer[:150]}")
    print()
