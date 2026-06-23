"""
DITA 数据包对比 HTML 报告生成器
完全匹配一致性对比总结报告.html模板格式
"""
import os
import html
from datetime import datetime, timezone, timedelta


def _bar(pct, color):
    return (
        f'<div class="bar"><div class="fill" style="width:{pct*100:.1f}%;background:{color}"></div>'
        f'<span>{pct*100:.1f}%</span></div>'
    )


def _diff_html(diff):
    a = diff.get("a_html") or html.escape(diff.get("text_a", "") or "")
    b = diff.get("b_html") or html.escape(diff.get("text_b", "") or "")

    diff_label = diff.get("diff_label", "")
    severity = diff.get("severity", "")

    # 严重程度标记
    sev_icon = ""
    if severity == "critical":
        sev_icon = "🔴 "
    elif severity == "high":
        sev_icon = "🟠 "
    elif severity == "low":
        sev_icon = "🟢 "

    if diff["type"] == "modify":
        tag = diff_label if diff_label else ("A → B")
        tag_html = f'{sev_icon}{html.escape(tag)}' if sev_icon else html.escape(tag)
        return (
            f'<div class="diff-row changed">'
            f'<span class="tag-c">{tag_html}</span>'
            f'<div class="text">'
            f'<div class="side-a">{a}</div>'
            f'<div class="side-b">{b}</div>'
            f'</div></div>'
        )
    elif diff["type"] == "only_a":
        icon = "🟠" if severity == "critical" else ("🟡" if severity == "high" else "🔵")
        return (
            f'<div class="diff-row changed">'
            f'<span class="tag-c">{icon} A 独有</span>'
            f'<div class="text">'
            f'<div class="side-a">{a}</div>'
            f'</div></div>'
        )
    elif diff["type"] == "only_b":
        icon = "🟠" if severity == "critical" else ("🟡" if severity == "high" else "🔵")
        return (
            f'<div class="diff-row changed">'
            f'<span class="tag-c">{icon} B 独有</span>'
            f'<div class="text">'
            f'<div class="side-b">{b}</div>'
            f'</div></div>'
        )
    return ""


def render_dita_html_report(compare_result: dict, name_a: str, name_b: str) -> str:
    cr = compare_result
    topics = cr.get("topics", [])

    n_a = cr.get("n_topics_a", 0)
    n_b = cr.get("n_topics_b", 0)
    n_matched = cr.get("n_matched_topics", 0)
    n_only_a = cr.get("n_only_a", 0)
    n_only_b = cr.get("n_only_b", 0)
    weighted = cr.get("weighted_sim", 0.0)
    avg_match = cr.get("avg_match", 0.0)
    n_sent_a = cr.get("n_sentences_a", 0)
    n_sent_b = cr.get("n_sentences_b", 0)
    n_pairs = cr.get("n_matched_pairs", 0)

    # 从明细表（topics）实际判定结果重新统计汇总卡片数据
    # 与明细表判定逻辑完全对齐（get_consistency_label）
    # 仅统计匹配上的 topic（type=matched），only_a/only_b 单独统计
    real_full = 0      # 100%
    real_high = 0      # 95%~99%
    real_eighty = 0    # 85%~95%
    real_seventy = 0   # 70%~85%
    real_sixty = 0     # 50%~70%
    real_low = 0       # <50%

    for tr in topics:
        # 跳过仅 A 或仅 B 的 topic，它们不在一致性统计范围内
        ttype = tr.get("type", "")
        if ttype in ("only_a", "only_b"):
            continue
        sim = tr.get("topic_sim", 0.0)
        if sim >= 0.99:
            real_full += 1
        elif sim >= 0.95:
            real_high += 1
        elif sim >= 0.85:
            real_eighty += 1
        elif sim >= 0.70:
            real_seventy += 1
        elif sim >= 0.50:
            real_sixty += 1
        else:
            real_low += 1

    # 汇总卡片使用实际统计
    full = real_full
    high = real_high
    partial = real_seventy + real_eighty  # 70-95% 算部分相似
    low = real_sixty + real_low            # <70% 算差异较大

    # 整体一致性：以明细表为准重新计算模糊 Jaccard
    jaccard = cr.get("overall_jaccard", 0.0)
    # 如果传入了 n_sentences 和 n_pairs，使用明细数据计算
    if n_sent_a > 0 and n_sent_b > 0:
        union = n_sent_a + n_sent_b - n_pairs
        if union > 0:
            jaccard = n_pairs / union

    if jaccard >= 0.80:
        verdict_icon = "✅"
        verdict_text = "自动通过（≥80%）"
        verdict_class = "ok"
    elif jaccard >= 0.60:
        verdict_icon = "⚠️"
        verdict_text = "建议复核（60% ~ 80%）"
        verdict_class = "warn"
    else:
        verdict_icon = "🟥"
        verdict_text = "强制人工复核（<60%，不可互换）"
        verdict_class = "danger"

    ts = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")

    css = """
body { font-family:-apple-system,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;margin:0;background:#f5f6f8;color:#1a1a1a; }
.wrap { max-width:1180px;margin:0 auto;padding:32px 24px; }
h1 { font-size:26px;margin:0 0 4px; }
.meta { color:#666;font-size:13px;margin-bottom:24px; }
.cards { display:flex;gap:16px;flex-wrap:wrap;margin-bottom:28px; }
.card { background:#fff;border-radius:10px;padding:18px 22px;box-shadow:0 1px 3px rgba(0,0,0,.08);min-width:140px; }
.card.primary { background:linear-gradient(135deg,#1976d2,#2c3e50);color:#fff;min-width:180px; }
.card.primary .lbl { color:rgba(255,255,255,.85); }
.card.primary .num { font-size:32px; }
.card .num { font-size:28px;font-weight:700; }
.card .lbl { color:#777;font-size:13px;margin-top:4px; }
.explain { background:#fffbea;border-left:4px solid #f9a825;padding:12px 16px;border-radius:6px;font-size:13px;line-height:1.7;color:#444;margin-bottom:22px; }
.file-info { background:#fff;border-radius:10px;box-shadow:0 1px 3px rgba(0,0,0,.08);padding:16px 18px;margin:0 0 22px; }
.file-info h2 { margin:0 0 12px;font-size:18px; }
.file-info-grid { display:grid;grid-template-columns:120px 1fr;gap:8px 12px;font-size:13px;line-height:1.7; }
.file-info-grid .label { color:#666;font-weight:600; }
.file-info-grid .value { word-break:break-word;overflow-wrap:anywhere; }
table { width:100%;border-collapse:collapse;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.08);table-layout:fixed; }
th,td { padding:10px 12px;text-align:left;font-size:13px;border-bottom:1px solid #eee;vertical-align:top;word-break:break-word;overflow-wrap:anywhere; }
th { background:#2c3e50;color:#fff;font-weight:600;white-space:normal; }
tr:hover { background:#f9fafb; }
code { background:#eef1f4;padding:1px 6px;border-radius:4px;font-size:12px; }
.tag { background:#e3f2fd;color:#1565c0;padding:2px 8px;border-radius:12px;font-size:11px; }
.bar { position:relative;background:#eee;border-radius:10px;height:18px;width:100%;min-width:80px;overflow:hidden; }
.bar .fill { height:100%; }
.bar span { position:absolute;left:0;right:0;top:0;line-height:18px;text-align:center;font-size:11px;color:#000; }
h2 { margin-top:32px;font-size:18px; }
.row-main { cursor:pointer; }
.row-main:hover { background:#f0f4f9; }
.row-main .diff-cell { color:#c62828;font-weight:600; }
.row-diff { display:none; }
.row-diff.open { display:table-row; }
.row-diff > td { background:#fafbfc;padding:0; }
.diffs { padding:12px 16px; }
.diff-empty { padding:14px 16px;color:#2e7d32;font-size:13px;background:#eaf6ec;border-radius:6px; }
.diff-row { display:flex;align-items:flex-start;gap:10px;padding:8px 10px;margin:6px 0;border-radius:6px;font-size:13px;line-height:1.6; }
.diff-row.changed { background:#fff8e1;border-left:3px solid #f9a825; }
.diff-row .text { flex:1;word-break:break-word; }
.diff-row .side-a,.diff-row .side-b { padding:4px 0; }
.diff-row .side-a::before { content:"A: ";color:#c62828;font-weight:600; }
.diff-row .side-b::before { content:"B: ";color:#2e7d32;font-weight:600; }
.tag-c { font-size:11px;padding:2px 8px;border-radius:10px;white-space:nowrap;font-weight:600;background:#f9a825;color:#fff; }
.del { background:#ffd6d6;text-decoration:line-through;color:#a31515;padding:0 2px;border-radius:2px; }
.ins { background:#d6f5d6;color:#1a5e1a;padding:0 2px;border-radius:2px; }
table.summary td { vertical-align:top;font-size:13px;line-height:1.55; }
table.summary td:nth-child(1) { width:48px;text-align:center;color:#666; }
table.summary td:nth-child(2), table.summary td:nth-child(3) { font-weight:600; }
table.summary td:nth-child(4), table.summary td:nth-child(5) { width:70px;text-align:center;color:#888; }
table.summary td:nth-child(7) { width:90px;text-align:center;font-weight:600; }
tr.ok-row td:nth-child(7) { color:#2e7d32; }
tr.high-row td:nth-child(7) { color:#558b2f; }
tr.mid-row td:nth-child(7) { color:#ef6c00; }
tr.low-row td:nth-child(7) { color:#c62828; }
tr.only-a-row { background:#fff4f4; }
tr.only-b-row { background:#f4faf4; }
tr.only-a-row td:nth-child(7), tr.only-b-row td:nth-child(7) { color:#666; }
.small { color:#888;font-size:12px; }
"""

    js = """
document.addEventListener('DOMContentLoaded', function() {
  document.querySelectorAll('.row-main').forEach(function(row) {
    row.addEventListener('click', function() {
      var target = this.getAttribute('data-target');
      if (target) {
        var diff = document.getElementById(target);
        if (diff) {
          diff.classList.toggle('open');
        }
      }
    });
  });
});
"""

    def get_consistency_label(sim):
        if sim >= 0.99:
            return "100%"
        elif sim >= 0.95:
            return "95%~99%"
        elif sim >= 0.85:
            return "85%~95%"
        elif sim >= 0.70:
            return "70%~85%"
        elif sim >= 0.50:
            return "50%~70%"
        else:
            return "<50%"

    def _extract_diff_keywords(diffs):
        """
        从 diffs 中提取实际差异关键字，返回差异类型。
        差异类型：型号/编号差异、措辞调整、结构重组、参数变更、新增/删除安全警告、操作流程重写、内容完全不同
        """
        if not diffs:
            return []

        types_found = []
        has_safety = False
        has_param = False
        has_model = False
        has_step = False
        has_wording = False
        has_wipe = False

        for d in diffs:
            text_a = d.get("text_a", "") or ""
            text_b = d.get("text_b", "") or ""
            combined = text_a + " " + text_b

            # 检测安全警告相关
            safety_keywords = ["警告", "注意", "危险", "warning", "caution", "danger", "安全", "must not", "do not", "shall", "不得", "禁止", "严禁"]
            if any(kw in combined.lower() for kw in safety_keywords):
                has_safety = True

            # 检测参数变更
            import re
            param_pattern = re.compile(
                r'\d+\.?\d*\s*[kW℃°MLVVAΩHzkVkgcm]|'
                r'\d+\s*[Vv]|[0-9]+(?:\.[0-9]+)?\s*(?:mm|cm|m|kg|g|L|ml|Hz|kHz|MHz|nm|μm|W|kW|A|mA|μA|V|kV|°C|°F|%|rpm)',
                re.IGNORECASE
            )
            if param_pattern.search(text_a) or param_pattern.search(text_b):
                has_param = True

            # 检测型号/编号差异
            model_pattern = re.compile(r'[A-Z]{2,}[-\s]?\d+|[A-Z]\d{2,}')
            models_a = set(model_pattern.findall(text_a))
            models_b = set(model_pattern.findall(text_b))
            if models_a != models_b:
                has_model = True

            # 检测操作流程
            step_keywords = ["步骤", "操作", "流程", "点击", "选择", "输入", "启动", "停止", "step", "click", "first", "then", "next", "press", "select"]
            if any(kw in combined.lower() for kw in step_keywords):
                has_step = True

            # 措辞调整（同时有 text_a 和 text_b，差异不大）
            if text_a and text_b and len(text_a) > 5 and len(text_b) > 5:
                # 计算差异比例
                set_a = set(text_a.lower().split())
                set_b = set(text_b.lower().split())
                if set_a and set_b:
                    inter = len(set_a & set_b)
                    union = len(set_a | set_b)
                    if union > 0 and inter / union >= 0.7:
                        has_wording = True

            # 内容完全不同
            if text_a and text_b:
                set_a = set(text_a.lower().split())
                set_b = set(text_b.lower().split())
                if set_a and set_b:
                    inter = len(set_a & set_b)
                    union = len(set_a | set_b)
                    if union > 0 and inter / union < 0.3:
                        has_wipe = True

        if has_safety:
            types_found.append("⚠️ 安全警告变更")
        if has_param:
            types_found.append("参数变更")
        if has_model:
            types_found.append("型号/编号差异")
        if has_step:
            types_found.append("操作流程变更")
        if has_wipe:
            types_found.append("内容完全不同")
        if has_wording and not types_found:
            types_found.append("措辞调整")

        return types_found if types_found else []

    def get_diff_explanation(tr):
        diffs = tr.get("diffs", [])
        sim = tr.get("topic_sim", 0.0)

        if not diffs:
            return "内容一致，无差异"

        # 基于实际差异内容生成说明
        diff_types = _extract_diff_keywords(diffs)
        type_counts = {"modify": 0, "only_a": 0, "only_b": 0}
        n_merged = 0  # 合并的 diff 组数
        for d in diffs:
            t = d.get("type", "")
            if t in type_counts:
                type_counts[t] += 1
            if d.get("merged_count", 0) > 1:
                n_merged += 1

        n_modify = type_counts["modify"]
        n_only_a = type_counts["only_a"]
        n_only_b = type_counts["only_b"]

        # 主体描述（按实际差异类型）
        if diff_types:
            main = "、".join(diff_types)
        elif n_merged > 0 and n_modify > 0:
            main = "措辞调整"
        else:
            if sim >= 0.99:
                main = "内容完全一致"
            elif n_modify > 0 and n_only_a == 0 and n_only_b == 0:
                main = "内容调整"
            elif n_only_a > 0 and n_only_b == 0:
                main = "A 独有内容"
            elif n_only_b > 0 and n_only_a == 0:
                main = "B 独有内容"
            else:
                main = "内容变更"

        # 数量补充（考虑合并）
        count_parts = []
        if n_modify > 0:
            count_parts.append(f"修改 {n_modify} 处")
        if n_only_a > 0:
            count_parts.append(f"A 独有 {n_only_a} 处")
        if n_only_b > 0:
            count_parts.append(f"B 独有 {n_only_b} 处")
        count_str = "（" + "，".join(count_parts) + "）" if count_parts else ""

        return f"{main}{count_str}"

    rows_html = []
    for idx, tr in enumerate(topics):
        diff_id = f"d{idx}"
        navtitle = html.escape(tr.get("navtitle", "") or "")
        chapter = html.escape(tr.get("chapter_a", "") or tr.get("chapter_b", "") or "—")
        sim = tr.get("topic_sim", 0.0)
        consistency_label = get_consistency_label(sim)

        row_class = tr.get("row_class", "")

        row_main = (
            f"<tr class='{row_class} row-main' data-target='{diff_id}'>"
            f"<td>{idx+1}</td>"
            f"<td>{chapter}</td>"
            f"<td>{navtitle}</td>"
            f"<td>{html.escape(get_diff_explanation(tr))}</td>"
            f"<td>{consistency_label}</td>"
            f"</tr>"
        )

        diffs = tr.get("diffs", [])
        if diffs:
            diffs_content = "\n".join(_diff_html(d) for d in diffs[:15])
            row_diff = (
                f"<tr class='row-diff' id='{diff_id}'>"
                f"<td colspan='5'><div class='diffs'>{diffs_content}</div></td>"
                f"</tr>"
            )
        else:
            row_diff = (
                f"<tr class='row-diff' id='{diff_id}'>"
                f"<td colspan='5'><div class='diff-empty'>✓ 该 topic 句段全部完全一致，无差异</div></td>"
                f"</tr>"
            )

        rows_html.append(row_main + row_diff)

    rows_str = "\n".join(rows_html) if rows_html else "<tr><td colspan='5' style='text-align:center;padding:40px;color:#888'>无 topic 数据</td></tr>"

    table_html = f"""
<h2>差异点汇总 (按 ditamap 中 topic 顺序)</h2>
<table class='summary'>
  <thead>
    <tr>
      <th>序号</th>
      <th>一级章节</th>
      <th>小节 (按 A 包 ditamap 顺序)</th>
      <th>差异说明</th>
      <th>一致性</th>
    </tr>
  </thead>
  <tbody>
    {rows_str}
  </tbody>
</table>
"""

    # 构建章节级统计
    chapter_stats = {}
    for tr in topics:
        chapter = tr.get("chapter_a", "") or tr.get("chapter_b", "") or "其他"
        if chapter not in chapter_stats:
            chapter_stats[chapter] = {
                "total": 0, "full": 0, "high": 0, "partial": 0, "low": 0, "only_a": 0, "only_b": 0
            }
        chapter_stats[chapter]["total"] += 1
        sim = tr.get("topic_sim", 0.0)
        ttype = tr.get("type", "")
        if ttype == "only_a":
            chapter_stats[chapter]["only_a"] += 1
        elif ttype == "only_b":
            chapter_stats[chapter]["only_b"] += 1
        else:
            if sim >= 0.99:
                chapter_stats[chapter]["full"] += 1
            elif sim >= 0.95:
                chapter_stats[chapter]["high"] += 1
            elif sim >= 0.70:
                chapter_stats[chapter]["partial"] += 1
            else:
                chapter_stats[chapter]["low"] += 1

    # 生成章节统计表 HTML
    chapter_rows = []
    for chapter, stats in chapter_stats.items():
        ch_total = stats["total"]
        ch_full = stats["full"]
        ch_high = stats["high"]
        ch_partial = stats["partial"]
        ch_low = stats["low"]
        if ch_total > 0:
            chapter_sim = (ch_full * 1.0 + ch_high * 0.97 + ch_partial * 0.80 + ch_low * 0.40) / ch_total
        else:
            chapter_sim = 0
        chapter_rows.append(
            f"<tr>"
            f"<td>{html.escape(chapter)}</td>"
            f"<td style='text-align:center'>{ch_total}</td>"
            f"<td style='text-align:center'>{ch_full}</td>"
            f"<td style='text-align:center'>{ch_high}</td>"
            f"<td style='text-align:center'>{ch_partial}</td>"
            f"<td style='text-align:center'>{ch_low}</td>"
            f"<td style='text-align:center;font-weight:600'>{chapter_sim*100:.1f}%</td>"
            f"</tr>"
        )
    chapter_stats_html = ""
    if chapter_rows:
        chapter_stats_html = f"""
<h2>章节一致性统计</h2>
<table class='summary'>
  <thead>
    <tr>
      <th>一级章节</th>
      <th style='text-align:center'>topic数</th>
      <th style='text-align:center'>完全一致</th>
      <th style='text-align:center'>高度相似</th>
      <th style='text-align:center'>部分相似</th>
      <th style='text-align:center'>差异较大</th>
      <th style='text-align:center'>章节一致性</th>
    </tr>
  </thead>
  <tbody>
    {"".join(chapter_rows)}
  </tbody>
</table>
"""

    # 构建复核重点和建议
    critical_topics = [tr for tr in topics if tr.get("topic_sim", 0.0) < 0.50]
    low_sim_topics = [tr for tr in topics if 0.50 <= tr.get("topic_sim", 0.0) < 0.70]

    review_focus = []
    if critical_topics:
        review_focus.append(f"<li><b>差异较大章节（&lt;50%）</b>：{', '.join(html.escape(tr.get('navtitle', '') or '') for tr in critical_topics[:5])}</li>")
    if low_sim_topics:
        review_focus.append(f"<li><b>较大差异章节（50-70%）</b>：{', '.join(html.escape(tr.get('navtitle', '') or '') for tr in low_sim_topics[:5])}</li>")

    conclusion_html = ""
    if review_focus or n_only_a > 0 or n_only_b > 0:
        conclusion_html = f"""
<h2>结论与建议</h2>
<div class="file-info">
  <h3>判定</h3>
  <div class="file-info-grid">
    <div class="label">整体一致性</div>
    <div class="value">{jaccard*100:.1f}%</div>
    <div class="label">判定结果</div>
    <div class="value">{verdict_icon} {html.escape(verdict_text)}</div>
  </div>

  <h3>复核重点</h3>
  <ul>
    {"".join(review_focus)}
    {"".join([f"<li><b>仅在 A 的 topic（{n_only_a} 个）</b>：需确认是否需要迁移到 B 包</li>"] if n_only_a > 0 else [])}
    {"".join([f"<li><b>仅在 B 的 topic（{n_only_b} 个）</b>：需确认是否为新增内容</li>"] if n_only_b > 0 else [])}
  </ul>

  <h3>复核建议</h3>
  <ul>
    <li>建议优先复核一致性低于 70% 的章节，确认内容变更是否符合预期</li>
    <li>安全相关章节（warning/caution/danger）应重点确认</li>
    <li>参数/数值变更需核对技术规格是否同步</li>
    <li>仅在 A 或仅在 B 的 topic 需确认是否需同步或归档</li>
  </ul>
</div>
"""

    full_html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>DITA 数据包对比报告</title>
<style>{css}</style>
</head>
<body>
<div class="wrap">
  <h1>DITA 数据包对比报告</h1>
  <div class="meta">生成时间: {ts} &nbsp;|&nbsp; {html.escape(name_a)} &harr; {html.escape(name_b)} &nbsp;|&nbsp; <span style="color:#888">点击下方明细行可展开/收起差异详情</span></div>

  <div class="cards">
    <div class='card primary'>
      <div class='num'>{jaccard*100:.1f}%</div>
      <div class='lbl'>整体一致性 · 模糊 Jaccard</div>
    </div>
    <div class='card '>
      <div class='num'>{avg_match*100:.1f}%</div>
      <div class='lbl'>匹配平均</div>
    </div>
    <div class='card '>
      <div class='num'>{n_matched}</div>
      <div class='lbl'>匹配 topic</div>
    </div>
    <div class='card '>
      <div class='num'>{full}</div>
      <div class='lbl'>完全一致</div>
    </div>
    <div class='card '>
      <div class='num'>{high}</div>
      <div class='lbl'>高度相似</div>
    </div>
    <div class='card '>
      <div class='num'>{partial}</div>
      <div class='lbl'>部分相似</div>
    </div>
    <div class='card '>
      <div class='num'>{low}</div>
      <div class='lbl'>差异较大</div>
    </div>
    <div class='card '>
      <div class='num'>{n_only_a}/{n_only_b}</div>
      <div class='lbl'>仅在 A / 仅在 B</div>
    </div>
  </div>

  <div class="file-info">
    <h2>文件基本信息</h2>
    <div class="file-info-grid">
      <div class="label">文件1包名称</div>
      <div class="value">{html.escape(name_a)}</div>
      <div class="label">文件2包名称</div>
      <div class="value">{html.escape(name_b)}</div>
      <div class="label">文件1统计</div>
      <div class="value">{n_sent_a} 句段 / {n_a} topics</div>
      <div class="label">文件2统计</div>
      <div class="value">{n_sent_b} 句段 / {n_b} topics</div>
    </div>
  </div>

  <div class="explain">
    <b>当前算法: 全量句段模糊 Jaccard（方案 2）</b><br>
    句段总数覆盖全部 topic，包括仅在 A / 仅在 B 的孤儿 topic；Jaccard = 匹配句段对数 /（A 全部句段数 + B 全部句段数 - 匹配句段对数）。<br>
    本次 A={n_sent_a} 句段，B={n_sent_b} 句段，匹配句段对={n_pairs}，并集={n_sent_a + n_sent_b - n_pairs}，整体一致性={jaccard*100:.2f}%。作为对照，加权一致性为 <b>{weighted*100:.2f}%</b>。<br>
    <span style="color:#888">判定：{verdict_icon} {html.escape(verdict_text)}</span>
  </div>

  {table_html}
  {chapter_stats_html}
  {conclusion_html}
</div>
<script>{js}</script>
</body>
</html>"""
    return full_html
