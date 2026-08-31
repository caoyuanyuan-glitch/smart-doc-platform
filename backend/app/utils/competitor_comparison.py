"""竞品文档多文档对比引擎。

定位（用户 2026-08-24 反馈）：单文档分析不是竞品分析。本引擎聚合 2-5 个
已完成分析任务的结构化结果，产出：
- 维度分数矩阵 + 每维度最优标注
- 综合排名（含「我方基线」角色标记）
- 差距洞察：有基线时输出「我方 vs 最强竞品」逐维度差距与行动建议；
  无基线时输出维度离散度（竞品间分化点）

不做重复分析：直接消费 CompetitorTask 表中的 readability / tool_analysis JSON。
趋势对比（同产品跨版本）属 Phase C，届时复用本引擎的矩阵构建能力。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from app.utils.competitor_report import _md_escape

MIN_DOCS = 2
MAX_DOCS = 5

_DIM_ORDER = ["sentence_length", "term_density", "passive_ratio", "paragraph_length", "modifier_stack"]
_DIM_LABELS = {
    "sentence_length": "平均句长",
    "term_density": "术语密度",
    "passive_ratio": "被动句比例",
    "paragraph_length": "段落长度",
    "modifier_stack": "修饰词堆叠",
}
_DIM_ACTIONS = {
    "sentence_length": "单句控制在 40 字/20 词以内",
    "term_density": "术语首次出现处给出解释",
    "passive_ratio": "操作步骤使用主动语态",
    "paragraph_length": "按单一主题分段",
    "modifier_stack": "精简定语层级",
}
# 差距阈值：|Δ| ≥ 8 分视为显著差距（满分 100 的 5 维加权体系下足够稳健）
_GAP_THRESHOLD = 8.0
# 离散度阈值：无基线时，极差 ≥ 15 分的维度视为竞品间分化点
_SPREAD_THRESHOLD = 15.0

_LEVEL_ZH = {"excellent": "优秀", "good": "良好", "fair": "一般", "poor": "较差", "insufficient": "样本不足"}


def _rank_key(d: dict):
    """综合排名排序键（None 安全）：样本不足（insufficient，score=None）排最后。

    v1.1 样本量三档使已完成任务的 overall_score 可为 None，直接按分数排序会
    对 None 抛 TypeError（交叉审查 P1）：以 (has_score, score) 元组配合
    reverse=True 排序——有分数的任务元组更大（True）排在前面，None 的
    (False, 0) 自然落到最后。
    """
    s = d.get("overall_score")
    return (s is not None, s if isinstance(s, (int, float)) else 0)


def load_task_payloads(tasks: List) -> List[dict]:
    """把 ORM 任务行解析为 {task_id, name, readability, tool_analysis}（异常 JSON 跳过）。"""
    payloads = []
    for t in tasks:
        try:
            readability = json.loads(t.readability) if t.readability else {}
            tool_analysis = json.loads(t.tool_analysis) if t.tool_analysis else {}
        except (ValueError, TypeError):
            continue
        payloads.append({
            "task_id": t.id,
            "name": t.file_name,
            "readability": readability,
            "tool_analysis": tool_analysis,
            "warnings": readability.get("warnings") or [],
        })
    return payloads


def _primary_tool_short(tool_analysis: Dict) -> str:
    summary = str(tool_analysis.get("summary") or "")
    if "：" in summary:
        summary = summary.split("：", 1)[1]
    return summary[:40] if summary else "未识别"


def build_comparison(payloads: List[dict], baseline_task_id: Optional[int] = None) -> Tuple[dict, List[dict]]:
    """构建对比结果（纯计算，不落库）。

    返回 (result, insights)：
    - result: 前端雷达图/矩阵直接消费的结构（documents / dimension_matrix /
      dimension_winners / overall_ranking / gaps）
    - insights: 复用洞察引擎结构 [{priority, area, action, evidence}]
    """
    if not (MIN_DOCS <= len(payloads) <= MAX_DOCS):
        raise ValueError(f"参与对比的任务数须在 {MIN_DOCS}-{MAX_DOCS} 之间")
    if baseline_task_id is not None and baseline_task_id not in {p["task_id"] for p in payloads}:
        raise ValueError("基线任务必须在参与对比的任务列表中")

    documents = []
    for p in payloads:
        read = p["readability"]
        documents.append({
            "task_id": p["task_id"],
            "name": p["name"],
            "is_baseline": p["task_id"] == baseline_task_id,
            "overall_score": read.get("overall_score", 0),
            "level": read.get("level", ""),
            "level_zh": _LEVEL_ZH.get(read.get("level", ""), read.get("level", "未知")),
            "language": "中文" if read.get("language") == "zh" else "英文",
            "tool": _primary_tool_short(p["tool_analysis"]),
        })

    # 维度矩阵：{dim_key: {task_id: score}}
    dimension_matrix = {}
    for key in _DIM_ORDER:
        scores = {}
        for p in payloads:
            dim = (p["readability"].get("dimensions") or {}).get(key) or {}
            score = dim.get("score")
            scores[p["task_id"]] = round(float(score), 1) if isinstance(score, (int, float)) else None
        dimension_matrix[key] = scores

    # 每维度最优（并列取先出现者；None 不参与）
    dimension_winners = {}
    for key, scores in dimension_matrix.items():
        valid = {tid: s for tid, s in scores.items() if s is not None}
        dimension_winners[key] = max(valid, key=valid.get) if valid else None

    overall_ranking = sorted(documents, key=_rank_key, reverse=True)

    gaps, insights = _build_gaps(documents, dimension_matrix, baseline_task_id)

    result = {
        "documents": documents,
        "dimension_matrix": dimension_matrix,
        "dimension_labels": _DIM_LABELS,
        "dimension_winners": dimension_winners,
        "overall_ranking": [d["task_id"] for d in overall_ranking],
        "gaps": gaps,
    }
    return result, insights


def _build_gaps(documents: List[dict], dimension_matrix: Dict, baseline_task_id: Optional[int]) -> Tuple[List[dict], List[dict]]:
    """差距分析：有基线 → 我方 vs 最强竞品；无基线 → 竞品间分化维度。"""
    gaps = []
    insights = []
    by_id = {d["task_id"]: d for d in documents}

    if baseline_task_id is not None:
        baseline = by_id[baseline_task_id]
        competitors = [d for d in documents if not d["is_baseline"]]
        for key in _DIM_ORDER:
            base_score = dimension_matrix[key].get(baseline_task_id)
            comp_scores = {d["task_id"]: dimension_matrix[key][d["task_id"]] for d in competitors}
            valid = {tid: s for tid, s in comp_scores.items() if s is not None}
            if base_score is None or not valid:
                continue
            best_tid = max(valid, key=valid.get)
            best_score = valid[best_tid]
            delta = round(best_score - base_score, 1)
            if delta >= _GAP_THRESHOLD:
                gaps.append({
                    "dimension": key,
                    "dimension_label": _DIM_LABELS[key],
                    "baseline_score": base_score,
                    "best_task_id": best_tid,
                    "best_name": by_id[best_tid]["name"],
                    "best_score": best_score,
                    "delta": delta,
                    "direction": "behind",
                })
                insights.append({
                    "priority": "P1",
                    "area": f"对比 · {_DIM_LABELS[key]}",
                    "action": (
                        f"竞品「{by_id[best_tid]['name'][:24]}」在{_DIM_LABELS[key]}维度领先我方基线 {delta} 分，"
                        f"建议优先改进：{_DIM_ACTIONS[key]}。"
                    ),
                    "evidence": f"我方 {base_score} vs 竞品最优 {best_score}",
                })
            elif base_score - best_score >= _GAP_THRESHOLD:
                gaps.append({
                    "dimension": key,
                    "dimension_label": _DIM_LABELS[key],
                    "baseline_score": base_score,
                    "best_task_id": best_tid,
                    "best_name": by_id[best_tid]["name"],
                    "best_score": best_score,
                    "delta": round(base_score - best_score, 1),
                    "direction": "ahead",
                })
                insights.append({
                    "priority": "P2",
                    "area": f"对比 · {_DIM_LABELS[key]}",
                    "action": f"我方基线在{_DIM_LABELS[key]}维度领先最优竞品 {round(base_score - best_score, 1)} 分，保持现有编写规范即可。",
                    "evidence": f"我方 {base_score} vs 竞品最优 {best_score}",
                })
    else:
        for key in _DIM_ORDER:
            valid = {tid: s for tid, s in dimension_matrix[key].items() if s is not None}
            if len(valid) < 2:
                continue
            spread = round(max(valid.values()) - min(valid.values()), 1)
            if spread >= _SPREAD_THRESHOLD:
                best_tid = max(valid, key=valid.get)
                worst_tid = min(valid, key=valid.get)
                gaps.append({
                    "dimension": key,
                    "dimension_label": _DIM_LABELS[key],
                    "best_task_id": best_tid,
                    "best_name": by_id[best_tid]["name"],
                    "best_score": valid[best_tid],
                    "worst_task_id": worst_tid,
                    "worst_name": by_id[worst_tid]["name"],
                    "worst_score": valid[worst_tid],
                    "delta": spread,
                    "direction": "spread",
                })
                insights.append({
                    "priority": "P2",
                    "area": f"对比 · {_DIM_LABELS[key]}",
                    "action": (
                        f"竞品间在{_DIM_LABELS[key]}维度分化明显（极差 {spread} 分）："
                        f"「{by_id[best_tid]['name'][:24]}」最佳实践可作为行业标杆，{_DIM_ACTIONS[key]}。"
                    ),
                    "evidence": f"最高 {valid[best_tid]} / 最低 {valid[worst_tid]}",
                })

    # 综合排名洞察：基线非第一 → P1；第一 → P2（样本不足任务 None 安全）
    if documents:
        ranking = sorted(documents, key=_rank_key, reverse=True)
        top = ranking[0]
        if top.get("overall_score") is None:
            insights.append({
                "priority": "P2",
                "area": "对比 · 综合",
                "action": "参与对比的任务综合评分均为空（样本不足未评分），综合排名不具参考性；建议补充正文后重新分析再对比。",
                "evidence": "综合评分全部为 None（insufficient）",
            })
        elif baseline_task_id is not None:
            base = by_id[baseline_task_id]
            if base.get("overall_score") is None:
                pass  # 基线样本不足：不给综合结论（分维度差距已在 None 保护下逐项跳过）
            elif top["is_baseline"]:
                runner_up = ranking[1]["overall_score"] if len(ranking) > 1 and ranking[1].get("overall_score") is not None else "-"
                insights.append({
                    "priority": "P2",
                    "area": "对比 · 综合",
                    "action": f"我方基线综合评分排名第一（{top['overall_score']} 分），整体编写质量具备竞争优势，保持现有规范。",
                    "evidence": f"综合评分 {top['overall_score']} vs 最优竞品 {runner_up}",
                })
            else:
                gap_total = round(top["overall_score"] - base["overall_score"], 1)
                insights.append({
                    "priority": "P1",
                    "area": "对比 · 综合",
                    "action": f"竞品「{top['name'][:24]}」综合评分领先我方基线 {gap_total} 分，建议按下方分维度差距逐项制定改进计划。",
                    "evidence": f"竞品 {top['overall_score']} vs 我方 {base['overall_score']}",
                })
    insights.sort(key=lambda i: 0 if i.get("priority") == "P1" else 1)
    return gaps, insights


def render_comparison_report(title: str, result: Dict, insights: List[dict],
                             warnings: Optional[List[str]] = None) -> str:
    """渲染对比 Markdown 报告。"""
    now = datetime.now()
    documents = result["documents"]
    by_id = {d["task_id"]: d for d in documents}

    lines = [
        "# 竞品文档对比报告",
        "",
        f"- **标题**：{_md_escape(title)}",
        f"- **参与文档**：{len(documents)} 份　**生成时间**：{now:%Y-%m-%d %H:%M}",
        "",
    ]
    for w in warnings or []:
        lines.append(f"> ⚠ {_md_escape(w)}")
        lines.append("")

    # 参与文档总览
    lines.append("## 一、参与文档")
    lines.append("")
    lines.append("| 文档 | 角色 | 语言 | 综合评分 | 评级 | 主编辑工具 |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for d in sorted(documents, key=lambda x: x["overall_score"], reverse=True):
        role = "我方基线" if d["is_baseline"] else "竞品"
        lines.append(
            f"| {_md_escape(d['name'])} | {role} | {d['language']} | {d['overall_score']} | "
            f"{d['level_zh']} | {_md_escape(d['tool'])} |"
        )
    lines.append("")

    # 维度矩阵
    lines.append("## 二、维度分数矩阵")
    lines.append("")
    # 截断在转义之前进行，避免把转义序列（如 \|）截断成孤立反斜杠
    header = "| 维度 | " + " | ".join(
        (_md_escape(by_id[d]['name'][:20]) + ("（我方）" if by_id[d]['is_baseline'] else ""))
        for d in result["overall_ranking"]
    ) + " |"
    lines.append(header)
    lines.append("| --- | " + " | ".join(["---"] * len(documents)) + " |")
    for key in _DIM_ORDER:
        scores = result["dimension_matrix"][key]
        valid = [s for s in scores.values() if s is not None]
        max_score = max(valid) if valid else None
        row = []
        for tid in result["overall_ranking"]:
            s = scores.get(tid)
            if s is None:
                row.append("-")
            elif max_score is not None and s == max_score and len(documents) > 1:
                row.append(f"**{s}** ▲")  # 并列最高分均标记
            else:
                row.append(f"{s}")
        lines.append(f"| {_DIM_LABELS[key]} | " + " | ".join(row) + " |")
    lines.append("")
    lines.append("> ▲ 标记为该维度最高分（含并列）。")
    lines.append("")

    # 差距分析
    lines.append("## 三、差距分析")
    lines.append("")
    gaps = result.get("gaps") or []
    if not gaps:
        has_baseline = any(d.get("is_baseline") for d in documents)
        threshold_txt = "8 分" if has_baseline else "15 分（极差）"
        lines.append(f"> 参与文档各维度差距均在阈值内（<{threshold_txt}），整体水平接近。")
        lines.append("")
    else:
        lines.append("| 维度 | 对比双方 | 分差 | 方向 |")
        lines.append("| --- | --- | --- | --- |")
        for g in gaps:
            direction = {"behind": "竞品领先", "ahead": "我方领先", "spread": "竞品间分化"}.get(g["direction"], g["direction"])
            if g["direction"] == "spread":
                pair = f"{g['best_name'][:16]} vs {g['worst_name'][:16]}"
            else:
                pair = f"我方基线 vs {g['best_name'][:16]}"
            lines.append(f"| {g['dimension_label']} | {_md_escape(pair)} | {g['delta']} | {direction} |")
        lines.append("")

    # 洞察
    lines.append("## 四、行动建议（对本司的启示）")
    lines.append("")
    if insights:
        for i in insights:
            lines.append(f"- **[{i['priority']}] {_md_escape(i['area'])}**：{_md_escape(i['action'])}")
            lines.append(f"  - 依据：{_md_escape(i['evidence'])}")
    else:
        lines.append("- 各文档维度接近，暂无显著差距项。")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("> 本报告由智能技术文档平台自动生成（规则引擎），雷达图请在平台对比页查看。")
    lines.append("")
    return "\n".join(lines)
