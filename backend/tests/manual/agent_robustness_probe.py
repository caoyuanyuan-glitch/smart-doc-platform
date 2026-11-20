"""Agent 鲁棒性测试：刁钻用例，检验意图识别是否真智能，而非关键词匹配。"""
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

from app.api.agent import _classify, _keyword_intent  # noqa: E402

# 刁钻用例：期望意图 + 说明。部分无标准答案，重点看是否合理。
CASES = [
    ("别审核了", "chat", "否定句-不该触发review"),
    ("不用润色，直接对比两份文档", "compare", "否定+多意图"),
    ("我想看看能不能生成，哦不，还是润色吧", "polish", "自我纠正"),
    ("审一下这个稿子", "review", "简称"),
    ("把这个 md 换成 dita", "convert", "缩写别名"),
    ("测序仪说明书里 Barcode 是什么", "qa", "领域知识问题"),
    ("帮我写一份 DNBelab C4 单细胞建库说明书", "generate", "带产品型号"),
    ("两段文字，前者改错字后者润色，先做哪个", "chat", "多任务询问"),
    ("asdfghjkl", "chat", "乱码"),
    ("", "chat", "空字符串"),
    ("审核并润色这个文档", "review", "多意图并列-取主"),
]

print("=" * 72)
print("Agent 鲁棒性实测（刁钻用例）")
print("=" * 72)
hit = 0
for text, expected, label in CASES:
    got = _classify(text, None)["intent"]
    kw = _keyword_intent(text)
    ok = got == expected
    hit += ok
    print(f"[{'OK ' if ok else 'MISS'}] {label:22s} 期望={expected:8s} AI={got:8s} 关键词={kw:8s} | {text[:26]}")

print()
print(f"AI 准确率: {hit}/{len(CASES)} = {hit/len(CASES):.1%}")
kw_hit = sum(1 for text, exp, _ in CASES if _keyword_intent(text) == exp)
print(f"关键词兜底: {kw_hit}/{len(CASES)} = {kw_hit/len(CASES):.1%}")
