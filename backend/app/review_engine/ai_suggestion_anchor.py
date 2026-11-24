"""AI 建议方向锚定守卫（确定性后置复核）。

背景（T7+RS 中文实测，PR #193 之后）：CN 侧 system prompt 的主写法锚定
指令（review_rules 10a）对 AI 不够硬——AI 仍建议统一到全文 0 处的少数派
形式（阔口吸头→宽口吸头[宽口 0 处]、DualBarcode→Dual Barcode[带空格 0 处]、
试剂槽上盖→测序试剂槽上盖[1 处 vs 多数 3 处]）。

EN 侧同类指令实测有效、CN 侧无效，且 prompt 约束无法保证，故在规则层兜底：
对 AI 的「统一写法/格式写法」类建议做全文计数复核，只拦两类可证明的误报——
  A. 建议目标形式全文 0 处（统一到一个不存在的形式，无依据）；
  B. 建议目标形式全文计数 < 原文形式计数（把多数派改成少数派，
     与 DET 系列的少数派样式口径一致）。

两类都要求原文形式在全文出现 ≥2 次（多数派已确立）——原文只出现 1 次时
无从谈多数派，不拦（保护 Qubit ssDNA #1standard 这类真实缺空格命中：
全文 1 处、正确形式 0 处）。

不碰的类别：可读性/语法/操作步骤/结构完整等改写类建议（本来就是重述，
不是「统一到某个既有形式」，计数比较无意义）。
"""

from __future__ import annotations

import difflib
import re
from typing import Any


def _val(issue: Any, key: str) -> str:
    if isinstance(issue, dict):
        return str(issue.get(key, "") or "")
    return str(getattr(issue, key, "") or "")


_ANCHOR_CATEGORIES = {
    "术语一致性", "一致性", "术语写法", "数值与单位写法", "数字与单位格式",
    "格式排版", "中英文混用", "格式一致性",
}

# 最小多数派门槛：原文形式全文出现次数达到该值才参与多数派比较
_MINORITY_MIN_SOURCE_COUNT = 2


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "").lower()


def _has_cjk_or_alpha(seg: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fffA-Za-z]", seg))


def should_drop_minority_target_issue(issue: Any, full_text: str) -> bool:
    """AI「统一写法」类建议的目标形式在全文中不存在或为少数派时返回 True。"""
    if _val(issue, "source").strip().lower() != "ai":
        return False
    if _val(issue, "category").strip() not in _ANCHOR_CATEGORIES:
        return False
    original = _val(issue, "original_text").strip()
    suggestion = _val(issue, "suggestion").strip()
    if not original or not suggestion or original == suggestion:
        return False

    norm_text = _norm(full_text)
    raw_text = re.sub(r"\s+", " ", full_text or "")

    # ── 空格差异型：去掉空白后两边相同，只是空格排布不同 ─────────────
    # 例：DualBarcode → Dual Barcode、1× dsDNA → 1 × dsDNA、h~ 24 → h~24。
    # 用原始（带空格）形式分别计数比较。
    if _norm(original) == _norm(suggestion):
        orig_raw = original.strip()
        sug_raw = suggestion.strip()
        orig_count = raw_text.count(orig_raw)
        sug_count = raw_text.count(sug_raw)
        if orig_count == sug_count:
            # 计数受排版差异影响时退化到无空格基形（如 Orig "A×2" vs doc "A ×2"）
            return False
        if orig_count >= _MINORITY_MIN_SOURCE_COUNT and sug_count < orig_count:
            return True
        return False

    # ── 替换/插入型：difflib 找出建议侧新增的词段 ────────────────────
    # 字符级 opcode 会把「阔口吸头→宽口吸头」拆成单字替换（阔→宽），
    # 短段过滤会漏；把相隔 ≤2 字符等值段的非等值 opcode 合并成差异区再判。
    orig_n = _norm(original)
    sug_n = _norm(suggestion)
    sm = difflib.SequenceMatcher(None, orig_n, sug_n, autojunk=False)
    regions: list[tuple[str, str]] = []  # (src_region, tgt_region)
    pending_src, pending_tgt = "", ""
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            eq = orig_n[i1:i2]
            if pending_src or pending_tgt:
                if len(eq) <= 2:
                    # 等值段太短，视为差异区内部噪声，继续合并
                    pending_src += eq
                    pending_tgt += eq
                    continue
                regions.append((pending_src, pending_tgt))
                pending_src = pending_tgt = ""
            continue
        pending_src += orig_n[i1:i2]
        pending_tgt += sug_n[j1:j2]
    if pending_src or pending_tgt:
        regions.append((pending_src, pending_tgt))

    for src_r, tgt_r in regions:
        if len(tgt_r) < 2 or not _has_cjk_or_alpha(tgt_r):
            continue
        tgt_count = norm_text.count(tgt_r)
        src_count = norm_text.count(src_r) if src_r else 0
        if len(tgt_r) >= 4 and len(src_r) >= 4:
            # 语义级比较：目标形式不存在 / 把多数派改写成少数派
            if tgt_count == 0 and src_count >= _MINORITY_MIN_SOURCE_COUNT:
                return True
            if src_count >= _MINORITY_MIN_SOURCE_COUNT and tgt_count < src_count:
                return True
        elif len(tgt_r) <= 3:
            # 短差异区（2-3 字）：仅目标形式完全不存在且原文形式高频时拦，
            # 避免「文件/类型」「请/勿」这类通用词的计数噪声
            if tgt_count == 0 and src_count >= 5:
                return True

    # 短纯中文词对整词比较：字符级 difflib 会把「阔口吸头→宽口吸头」
    # 拆成单字替换（阔→宽）而逃过长段过滤；≤12 字纯中文对按整词计数。
    if (
        len(orig_n) <= 12
        and len(sug_n) <= 12
        and re.fullmatch(r"[\u4e00-\u9fff]+", orig_n)
        and re.fullmatch(r"[\u4e00-\u9fff]+", sug_n)
    ):
        src_count = norm_text.count(orig_n)
        tgt_count = norm_text.count(sug_n)
        if src_count >= _MINORITY_MIN_SOURCE_COUNT and tgt_count < src_count:
            return True
    return False
