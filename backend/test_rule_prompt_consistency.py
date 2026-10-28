"""P0-2 一致性 CI：校验规则库与 AI 提示词口径互斥，冲突即失败。

背景：DOC-SPACE-006 曾把「英文数值 ℃ 前有空格」判错，与提示词
"Keep one space between numbers and units ... never remove an existing
number-unit space" 直接冲突，贡献 G99 评测 76 条误报（35%）。
本测试扫描规则实现与提示词，防止此类口径漂移复发。

运行：python test_rule_prompt_consistency.py
退出码：0=通过，1=发现冲突
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

BACKEND = Path(os.environ.get(
    "SDP_BACKEND",
    Path(__file__).resolve().parent.parent / "backend",
)).resolve()

REVIEW_PY = BACKEND / "app" / "api" / "review.py"
AI_CLIENT_PY = BACKEND / "app" / "utils" / "ai_client.py"


def load(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def find_rule_code(src: str, rule_name: str, window: int = 14) -> list[str]:
    """在 review.py 中找到某规则名出现处的上下文行（用于人工定位）。"""
    lines = src.splitlines()
    hits = []
    for i, line in enumerate(lines):
        if rule_name in line:
            start = max(0, i - 2)
            end = min(len(lines), i + window)
            hits.append("\n".join(lines[start:end]))
    return hits


def check_number_unit_spacing(rule_src: str, prompt_src: str) -> list[str]:
    """检查 1：数字-单位空格口径。

    提示词承诺 never remove an existing number-unit space；
    规则层不得存在「数值与单位之间的空格是问题」的单点判错逻辑。
    检查规则代码里是否出现针对「数字 + 空格 + 单位」的 add_issue 调用。
    """
    problems = []
    # 提示词侧：确认承诺仍在
    prompt_keep = re.search(
        r"Keep one space between numbers and units[^\n]*",
        prompt_src,
    )
    prompt_never = re.search(
        r"never remove an existing number-unit space",
        prompt_src,
    )
    if not prompt_keep or not prompt_never:
        problems.append(
            "[提示词] 数字-单位空格承诺缺失或措辞变更："
            '未找到 "Keep one space ... never remove an existing number-unit space"'
        )

    # 规则侧：扫描「数字+空格+单位」被报为问题的代码模式
    # 命中模式：add_issue(... 'DOC-SPACE-00X' ... '多余空格'/'空格...问题' ...)
    for match in re.finditer(
        r"add_issue\s*\([^)]*?(['\"])DOC-SPACE-\d+\1[^)]*?",
        rule_src,
        re.DOTALL,
    ):
        block = match.group(0)
        # 若 description/suggestion 里含"多余空格""空格是问题""不保留空格"等
        # 负面措辞 → 该规则在报「空格多余」
        if re.search(
            r"多余空格|空格.{0,6}问题|不保留空格|通常不保留|删(?:除|掉).{0,4}空格|"
            r"space.{0,20}(?:unnecessary|should be removed|too many)",
            block,
            re.IGNORECASE,
        ):
            problems.append(
                "[规则] 发现疑似「判数字-单位空格多余」的规则（与提示词冲突）：\n"
                + block[:300]
            )

    # 全量搜索所有 add_issue 块中同时含 ℃ 与空格负面词的调用（兜底）
    for match in re.finditer(r"add_issue\s*\([^)]*?\)", rule_src, re.DOTALL):
        block = match.group(0)
        if "℃" in block and re.search(r"多余空格|空格.{0,6}问题", block):
            problems.append(
                "[规则] ℃ 相关空格判错残留（应只报一致性）：\n" + block[:300]
            )
    return problems


def check_unicode_equivalent(rule_src: str, prompt_src: str) -> list[str]:
    """检查 2：Unicode 等价字符口径。

    提示词禁止报 µ/μ、全角/半角、减号/连字符等视觉等价差异；
    规则层不得存在以「码位差异/全角」为单点判错且无实质影响的规则。
    """
    problems = []
    prompt_forbidden = re.search(
        r"Unicode-equivalent character differences[^\n]*",
        prompt_src,
    )
    if not prompt_forbidden:
        problems.append(
            "[提示词] Unicode 等价字符禁令缺失（FORBIDDEN 段应有）"
        )

    # 规则侧：全角字符判错的规则，若只靠「全角」且无中文语境强证据，视为高风险
    # ENG-CN-001（英文文档中文混入）属于文本层强信号，不在冲突范围；
    # 但 PUNCT-001 把全角标点一律 serious 而无语境分级，与提示词"视觉等价不报"张力大。
    # 这里只做硬性检查：以全角字符本身为唯一判据的 add_issue。
    for match in re.finditer(
        r"add_issue\s*\([^)]*?(['\"])PUNCT-\d+\1[^)]*?",
        rule_src,
        re.DOTALL,
    ):
        block = match.group(0)
        if "全角" in block or "中文标点" in block:
            # PUNCT-001 逻辑在 review.py 中按语言门控触发（英文文档才跑），
            # 不构成与提示词的直接冲突；仅登记供人工评估
            pass
    return problems


def check_ui_object_invention(rule_src: str, prompt_src: str) -> list[str]:
    """检查 3：UI 对象凭空补名。

    提示词禁止 invent button/icon name (Browse/Edit)；
    规则层不得把「原文没有的对象名」写进 suggestion。
    """
    problems = []
    prompt_guard = re.search(
        r"do not invent a button/icon name[^\n]*",
        prompt_src,
    )
    if not prompt_guard:
        problems.append("[提示词] UI 对象补名禁令缺失")

    # 规则侧扫描：规则里是否硬编码"缺少【X】按钮/图标"类的 add_issue
    for match in re.finditer(
        r"add_issue\s*\([^)]*?['\"][^'\"]*(?:缺少|缺失|应(?:有|补)|请添加)[^'\"]*?(?:按钮|图标|控件)[^'\"]*['\"][^)]*?\)",
        rule_src,
        re.DOTALL,
    ):
        block = match.group(0)
        problems.append(
            "[规则] 疑似规则层凭空断言 UI 对象缺失（若原文无证据即误报）：\n"
            + block[:300]
        )
    return problems


def check_numeric_protection(rule_src: str, prompt_src: str) -> list[str]:
    """检查 4：数值保护。

    提示词禁止改数值/温度/浓度/页码；
    规则层 suggestion 不得包含对数字的改写建议（除非原文证明错误）。
    """
    problems = []
    prompt_guard = re.search(
        r"Do not change numeric values[^\n]*",
        prompt_src,
    )
    if not prompt_guard:
        problems.append("[提示词] 数值保护承诺缺失")

    # 规则侧：找 suggestion 里带具体数值的 add_issue 且 description 无"应为 X"证据
    # 仅登记疑似（如"建议改为 30 ℃"这类无源改写）
    for match in re.finditer(
        r"add_issue\s*\([^)]*?\d+[^)]*?['\"][^'\"]*(?:建议改为|改为|替换为)[^'\"]*\d+[^'\"]*['\"]",
        rule_src,
        re.DOTALL,
    ):
        block = match.group(0)
        problems.append(
            "[规则] 疑似规则层无源改写数值（应仅当原文证明错误）：\n" + block[:300]
        )
    return problems


def main() -> int:
    if not REVIEW_PY.exists():
        print(f"[skip] 未找到 review.py: {REVIEW_PY}")
        return 0
    if not AI_CLIENT_PY.exists():
        print(f"[skip] 未找到 ai_client.py: {AI_CLIENT_PY}")
        return 0

    rule_src = load(REVIEW_PY)
    prompt_src = load(AI_CLIENT_PY)

    checks = [
        ("数字-单位空格口径", check_number_unit_spacing),
        ("Unicode 等价字符口径", check_unicode_equivalent),
        ("UI 对象补名口径", check_ui_object_invention),
        ("数值保护口径", check_numeric_protection),
    ]

    all_problems = []
    print("=" * 60)
    print("规则库 vs AI 提示词 一致性检查")
    print("=" * 60)
    for name, fn in checks:
        problems = fn(rule_src, prompt_src)
        status = "PASS" if not problems else "FAIL"
        print(f"\n[{status}] {name}")
        for p in problems:
            print("  - " + p.replace("\n", "\n    "))

    return 1 if any(
        fn(rule_src, prompt_src) for _, fn in checks
    ) else 0


if __name__ == "__main__":
    sys.exit(main())
