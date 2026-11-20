"""审核准确率升级能力（opt-in，默认全关，零回归）。

三项能力，对应"为什么平台不如人工直接审"的三个结构性根因：
  1. 全页几何疑点提示（C3 合规：只产 needs_human_review / confidence<85，绝不产高置信 TP）
  2. 全文一致性 pass（跨分块术语/引用索引，给 AI 全文视图）
  3. 一刀切过滤器降权保留（is_noise / value_score 不静默删除，改为标记待人工）

设计原则（务必保留）：
- 全部由环境变量开关，默认关闭；不设开关时行为与原流水线完全一致。
- 几何信号遵守 C3：只能提示人工复核，置信度 <85，不得当高置信问题报出。
- 不碰用户已裁定误报（图标提取伪影、弯直引号、过程档高亮等）——本模块不新增任何
  "图标/按钮缺失"类判定，只处理拥挤/粗线/图片偏离中心这三类纯几何信号。
- 全文 pass 只做一致性/交叉引用两类的候选收集，输出仍走主流水线去重与过滤。
"""

from __future__ import annotations

import os
from typing import Any, Iterable


def _env_flag(name: str, default: str = "0") -> bool:
    return str(os.getenv(name, default) or "").strip().lower() in {"1", "true", "yes", "on"}


def fullpage_geometry_enabled() -> bool:
    return _env_flag("REVIEW_FULLPAGE_GEOMETRY_HINTS")


def fulltext_consistency_enabled() -> bool:
    return _env_flag("REVIEW_FULLTEXT_CONSISTENCY_PASS")


def keep_downgraded_enabled() -> bool:
    return _env_flag("REVIEW_KEEP_DOWNGRADED_ISSUES")


# ── 能力 1：全页几何疑点提示 ───────────────────────────────────────────

# 只保留三类纯几何信号，且必须达到阈值；不碰"图标/按钮缺失"（用户已裁定为提取伪影）。
_GEOMETRY_REASON_THRESHOLDS = {
    "crowded_lines": ("crowding_score", 0.75),
    "thick_rules": ("thick_line_ratio", 0.35),
    "image_off_center": ("image_offset_ratio", 0.28),
}


def geometry_hint_issues(suspicious_pages: dict | None, existing_pages: Iterable[int] = ()) -> list[dict]:
    """把全页几何异常转成待人工复核 issue（C3 合规）。

    与现有 6+6 页视觉复核互补：这里覆盖所有页，只发低置信提示，不烧视觉模型 key。
    已由视觉链覆盖的页跳过，避免重复。
    """
    if not fullpage_geometry_enabled() or not suspicious_pages:
        return []
    covered = {int(p) for p in existing_pages if p}
    issues = []
    for candidate in suspicious_pages.get("candidates") or []:
        page = int(candidate.get("page_number") or 0)
        if page <= 0 or page in covered:
            continue
        reasons = {str(r) for r in (candidate.get("reasons") or [])}
        signals = candidate.get("layout_signals") or {}
        hits = []
        for reason, (signal_key, threshold) in _GEOMETRY_REASON_THRESHOLDS.items():
            if reason in reasons and float(signals.get(signal_key) or 0) >= threshold:
                hits.append((reason, float(signals.get(signal_key))))
        if not hits:
            continue
        reason_text = "、".join(f"{r}={v:.2f}" for r, v in hits)
        issues.append({
            "severity": "suggestion",
            "category": "表格/版式",
            "rule": "PDF-GEOM-HINT-001",
            "chapter": f"第{page}页",
            "original_text": candidate.get("text_preview") or "",
            "context": candidate.get("text_preview") or "",
            "suggestion": "请人工复核该页版面（行距过密/表格线过粗/图片偏离居中）",
            "description": f"全页几何扫描提示待人工复核：{reason_text}。几何信号不作为自动判错依据。",
            "audit_basis": "PDF 全页几何扫描（纯 fitz，未调用视觉模型）",
            "confidence": 68,  # C3: <85
            "source": "rule",
            "needs_human_review": True,
            "page_number": page,
        })
    return issues


# ── 能力 2：全文一致性 pass ────────────────────────────────────────────

# 已知的中文术语易混写法对（人工常见批注类型）。以"共同上下文 + 不同写法"成组统计。
_KNOWN_TERM_VARIANT_PAIRS = (
    ("存储", "储存"), ("其它", "其他"), ("帐号", "账号"), ("联接", "连接"),
    ("缺省", "默认"), ("液位", "液面"), ("按顺序依次", "依次"),
)


def build_fulltext_index(content: str) -> dict:
    """从全文抽取术语/引用的出现形态，供一致性 pass 使用。

    纯文本启发式：只统计"已知易混写法对"或"同一英文缩写/全称"在全文的并存情况。
    不做语义判断，只提供候选，最终由 AI 或人工裁定。
    """
    import re

    if not fulltext_consistency_enabled() or not content:
        return {}
    inconsistent: dict[str, dict[str, int]] = {}
    for left, right in _KNOWN_TERM_VARIANT_PAIRS:
        lc, rc = content.count(left), content.count(right)
        if lc and rc:
            inconsistent[f"{left}/{right}"] = {left: lc, right: rc}

    # 英文缩写与全称并存（如 "Catalog Number" 与 "Cat. No."）
    abbreviation_pairs = (
        ("Catalog Number", r"\bCatalog\s+Number\b", r"\bCat\.?\s*No\.?"),
        ("Deoxyribonucleic acid/DNA", r"\bDeoxyribonucleic\s+acid\b", r"\bDNA\b"),
        ("Polymerase Chain Reaction/PCR", r"\bPolymerase\s+Chain\s+Reaction\b", r"\bPCR\b"),
    )
    for label, full_pattern, abbr_pattern in abbreviation_pairs:
        fc = len(re.findall(full_pattern, content, re.IGNORECASE))
        ac = len(re.findall(abbr_pattern, content, re.IGNORECASE))
        if fc and ac:
            inconsistent[label] = {"full": fc, "abbr": ac}
    return {"total_terms": 0, "inconsistent_candidates": inconsistent}


def build_fulltext_consistency_basis(content: str, max_terms: int = 60) -> str:
    """生成'全文术语写法索引'作为审核依据注入各分块 prompt。

    目的：让单块审核也能看到全文范围的同术语不同写法（跨块一致性），
    这是人工直审靠前后翻页才能发现、而分块审核先天看不到的信息。
    不额外调用 AI、不烧 token；只把候选索引作为提示，是否报由主审核链裁定。
    """
    index = build_fulltext_index(content)
    candidates = index.get("inconsistent_candidates") or {}
    if not candidates:
        return ""
    lines = ["【全文术语写法索引（跨章节一致性候选，仅供比对，非结论）】"]
    for key, variants in list(candidates.items())[:max_terms]:
        forms = " / ".join(f"{form}({count})" for form, count in variants.items())
        lines.append(f"- {key}: {forms}")
    lines.append("说明：同一术语出现多种写法时，请结合所在章节判断是否属于术语不一致；仅当证据充分时报告。")
    return "\n".join(lines)


# ── 能力 3：一刀切过滤器降权保留 ───────────────────────────────────────

def downgrade_instead_of_drop(issue: Any, drop_reason: str) -> Any:
    """把本要静默删除的 issue 降权标记后保留（opt-in）。

    只在 keep_downgraded_enabled() 为真时生效；调用方仍需保证这类 issue
    在展示层与高置信问题区分（needs_human_review / confidence<50）。
    """
    if not keep_downgraded_enabled():
        return None

    def _set(obj, key, value):
        if isinstance(obj, dict):
            obj[key] = value
        else:
            setattr(obj, key, value)

    _set(issue, "confidence", 40)
    _set(issue, "needs_human_review", True)
    _set(issue, "possible_false_positive", True)
    _set(issue, "downgrade_reason", drop_reason)
    return issue
