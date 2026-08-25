"""竞品文档分析报告渲染（Markdown）。

输入：analyze_document() 产出的结构化结果（tool_analysis / readability / access / findability / usability）。
输出：可直接预览与导出的 Markdown 报告全文。
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Dict, Optional

# Markdown 结构字符（用户可控字段需转义，防止表格破坏 / 标题注入 / 链接注入）
_MD_ESCAPE_RE = re.compile(r"([\\`*_{}\[\]()#+!|>~-])")


def _md_escape(value) -> str:
    """转义用户可控文本中的 Markdown 特殊字符与换行，防报告注入。"""
    text = str(value or "")
    text = text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    return _MD_ESCAPE_RE.sub(r"\\\1", text)


_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")


def markdown_to_text(md: str) -> str:
    """将 Markdown 报告轻量转为纯文本（供 format=text 输出）。"""
    lines = []
    for raw in md.splitlines():
        line = raw.rstrip()
        if _TABLE_SEP_RE.match(line) and "|" in line:
            continue  # 跳过表格分隔行 | --- | --- |
        line = re.sub(r"^#{1,6}\s*", "", line)        # 标题
        line = re.sub(r"^\s*>\s?", "", line)          # 引用
        line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)  # 粗体
        line = re.sub(r"\*([^*]+?)\*", r"\1", line)   # 斜体
        line = re.sub(r"`([^`]+)`", r"\1", line)      # 行内代码
        line = line.strip(" |")
        lines.append(line)
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text.replace("\\|", "|")


def _fmt_time(ts) -> str:
    try:
        return ts.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(ts)


def _fmt_sample_list(samples, max_items: int = 3) -> str:
    """将样本例句列表渲染为缩进列表；无样本时返回空串。"""
    lines = []
    for s in samples[:max_items]:
        page = s.get("page") or 0
        text = str(s.get("text") or "").strip()
        if not text:
            continue
        loc = f"（第 {page} 页）" if page else ""
        escaped = _md_escape(text[:100])
        lines.append(f"  - 「{escaped}{'…' if len(text) > 100 else ''}」{loc}")
    return "\n".join(lines)


def _render_tool_section(tool_analysis: Dict) -> str:
    meta = tool_analysis.get("meta", {})
    tools = tool_analysis.get("tools", [])
    font_signals = tool_analysis.get("font_signals", [])

    lines = ["## 一、编辑工具识别", ""]
    lines.append(f"- **结论**：{_md_escape(tool_analysis.get('summary', '未知'))}")
    lines.append(f"- **文档格式**：{_md_escape(meta.get('format', '未知'))}（共 {_md_escape(meta.get('pages', 0))} 页）")
    if meta.get("producer"):
        lines.append(f"- **Producer 元数据**：{_md_escape(meta['producer'])}")
    if meta.get("creator"):
        lines.append(f"- **Creator 元数据**：{_md_escape(meta['creator'])}")
    if meta.get("source_url"):
        lines.append(f"- **来源链接**：{_md_escape(meta['source_url'])}")
    lines.append("")

    if tools:
        lines.append("| 识别工具 | 类别 | 置信度 | 依据 |")
        lines.append("| --- | --- | --- | --- |")
        for t in tools:
            lines.append(
                f"| {_md_escape(t.get('name', ''))} | {_md_escape(t.get('category', ''))} | "
                f"{_md_escape(t.get('confidence', ''))} | {_md_escape(t.get('source', ''))} |"
            )
        lines.append("")
    else:
        lines.append("> 未识别到明确的编辑工具。可能是扫描件或使用未知工具生成。")
        lines.append("")

    if font_signals:
        lines.append("### 字体信号（佐证）")
        lines.append("")
        for fs in font_signals:
            embed = "嵌入" if fs.get("embedded") else "未嵌入"
            lines.append(f"- {_md_escape(fs.get('hint', ''))}（{embed}，字体「{_md_escape(fs.get('name', ''))}」）")
        lines.append("")
    html_evidence = tool_analysis.get("html_evidence") or []
    if html_evidence:
        lines.append("**识别证据**")
        lines.append("")
        for item in html_evidence:
            lines.append(f"- {_md_escape(item)}")
        lines.append("")
    return "\n".join(lines)


def _render_structure_section(readability: Dict) -> str:
    stats = readability.get("structure_stats") or {}
    lines = ["## 二、结构统计（客观指标）", ""]
    lines.append("| 指标 | 数值 | 口径说明 |")
    lines.append("| --- | --- | --- |")
    lines.append(f"| 页数 | {stats.get('pages', 0)} | 文档总页数 |")
    lines.append(f"| 章节数 | {stats.get('chapter_count', 0)} | 标题行启发式识别，近似值 |")
    lines.append(f"| 图片数 | {stats.get('image_count', 0)} | HTML `<img>` 或 PDF 嵌入图统计 |")
    lines.append(f"| 表格数 | {stats.get('table_count', 0)} | HTML `<table>` 或 PDF 表格统计 |")
    lines.append(f"| 安全警告数 | {stats.get('warning_count', 0)} | 行首 WARNING/CAUTION/DANGER/NOTICE/警告/注意/危险 |")
    lines.append("")
    for item in stats.get("cautions") or []:
        lines.append(f"> {_md_escape(item)}")
        lines.append("")
    return "\n".join(lines)


def _render_readability_section(readability: Dict) -> str:
    dims = readability.get("dimensions", {})
    stats = readability.get("stats", {})
    suggestions = readability.get("suggestions", [])
    language_label = "中文" if readability.get("language") == "zh" else "英文"

    lines = ["## 三、可读性分析", ""]
    lines.append(
        f"- **语言**：{language_label}　**综合评分**：{readability.get('overall_score', 0)} 分　"
        f"**评级**：{readability.get('level', '未知')}"
    )
    lines.append("")
    for item in (readability.get("structure_stats") or {}).get("cautions") or []:
        if "文本样本量有限" in str(item) or "入口页" in str(item) or "封面页" in str(item):
            lines.append(f"> {_md_escape(item)}")
            lines.append("")
    lines.append("| 维度 | 得分 | 权重 | 说明 |")
    lines.append("| --- | --- | --- | --- |")
    weights = {
        "sentence_length": "25%",
        "term_density": "20%",
        "passive_ratio": "20%",
        "paragraph_length": "15%",
        "modifier_stack": "20%",
    }
    dim_labels = {
        "sentence_length": "平均句长",
        "term_density": "术语密度",
        "passive_ratio": "被动句比例",
        "paragraph_length": "段落长度",
        "modifier_stack": "修饰词堆叠",
    }
    for key in ("sentence_length", "term_density", "passive_ratio", "paragraph_length", "modifier_stack"):
        dim = dims.get(key, {})
        lines.append(f"| {dim_labels[key]} | {dim.get('score', 0)} | {weights[key]} | {dim.get('label', '')} |")
    lines.append("")
    lines.append("### 基础统计")
    lines.append("")
    lines.append(f"- 句子总数：{stats.get('sentence_count', 0)}　平均句长：{stats.get('avg_sentence_len', 0)}　"
                 f"平均段落长度：{stats.get('avg_paragraph_len', 0)}")
    lines.append(f"- 术语密度：{stats.get('term_density_pct', 0)}%　被动句比例：{stats.get('passive_ratio_pct', 0)}%")
    lines.append("")

    # 分项问题例句
    has_samples = False
    for key, label in dim_labels.items():
        dim = dims.get(key, {})
        samples = dim.get("samples") or []
        shown = [s for s in samples if s.get("text")]
        if not shown:
            continue
        if not has_samples:
            lines.append("### 典型问题例句")
            lines.append("")
            has_samples = True
        lines.append(f"**{label}**")
        lines.append("")
        lines.append(_fmt_sample_list(shown))
        lines.append("")

    lines.append("### 改进建议")
    lines.append("")
    for s in suggestions:
        lines.append(f"- {s}")
    lines.append("")
    return "\n".join(lines)


def _render_experience_section(title: str, index_label: str, data: Dict, dim_labels: Dict[str, str], note: str) -> str:
    lines = [f"## {index_label}、{title}", ""]
    lines.append(f"> {note}")
    lines.append("")
    lines.append(
        f"- **综合评分**：{data.get('overall_score', 0)} 分　**评级**：{data.get('level', '未知')}"
    )
    lines.append("")
    lines.append("| 维度 | 得分 | 说明 |")
    lines.append("| --- | --- | --- |")
    for key, label in dim_labels.items():
        dim = (data.get("dimensions") or {}).get(key, {})
        lines.append(f"| {label} | {dim.get('score', 'N/A')} | {dim.get('label', '')} |")
    lines.append("")
    na_dimensions = data.get("na_dimensions") or []
    if na_dimensions:
        lines.append(
            f"> 以下维度不适用于当前输入，已置 N/A：{_md_escape('、'.join(str(v) for v in na_dimensions))}"
        )
        lines.append("")
    summary = data.get("summary")
    if summary:
        lines.append(f"- {_md_escape(summary)}")
        lines.append("")
    return "\n".join(lines)


def render_competitor_report(
    file_name: str,
    tool_analysis: Dict,
    readability: Dict,
    access: Optional[Dict] = None,
    findability: Optional[Dict] = None,
    usability: Optional[Dict] = None,
    error: Optional[str] = None,
) -> str:
    """渲染完整 Markdown 报告。error 非空时输出失败说明。"""
    now = datetime.now()
    lines = [
        f"# 竞品文档分析报告",
        "",
        f"- **文档**：{_md_escape(file_name)}",
        f"- **生成时间**：{_fmt_time(now)}",
        "",
    ]
    if error:
        lines += [
            "> 本次分析未能完成，请检查文件是否为受支持的格式（PDF/Word/Markdown）或文件是否损坏。",
            "",
            f"**失败原因**：{_md_escape(error)}",
            "",
        ]
        return "\n".join(lines)
    lines.append(_render_tool_section(tool_analysis))
    lines.append(_render_structure_section(readability))
    lines.append(_render_readability_section(readability))
    if access:
        lines.append(
            _render_experience_section(
                "可获得性分析（Access）",
                "四",
                access,
                {
                    "format_choice": "格式选择",
                    "version_transparency": "版本透明度",
                    "offline_availability": "离线可用性",
                },
                "用户能否拿到文档，以及获取和离线使用体验。",
            )
        )
    if findability:
        lines.append(
            _render_experience_section(
                "易查找性分析（Findability）",
                "五",
                findability,
                {
                    "toc": "目录（TOC）",
                    "index_or_glossary": "索引与术语表",
                },
                "用户能否快速定位所需内容，以及导航与索引支持情况。",
            )
        )
    if usability:
        lines.append(
            _render_experience_section(
                "可用性分析（Usability）",
                "六",
                usability,
                {
                    "task_oriented_titles": "任务导向标题",
                    "step_completeness": "步骤完整性",
                    "error_recovery": "错误恢复信息",
                    "information_consistency": "信息一致性",
                    "link_effectiveness": "链接有效性",
                    "actionability": "可操作指令",
                },
                "用户能否依靠文档顺畅完成任务。",
            )
        )
    lines.append("---")
    lines.append("")
    lines.append("> 本报告由智能技术文档平台自动生成（规则引擎），供竞品文档分析参考。")
    lines.append("")
    return "\n".join(lines)
