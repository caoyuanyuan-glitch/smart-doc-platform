"""
通用文档对比 HTML 报告生成器
支持 Word / PDF / Markdown / TXT 格式对比
使用与 DITA 报告完全相同的样式
"""
import html
from datetime import datetime, timezone, timedelta


def render_doc_html_report(compare_result: dict, name_a: str, name_b: str) -> str:
    """
    生成通用文档对比 HTML 报告
    复用 DITA 报告的 CSS 样式和结构
    """
    results = compare_result.get("results", [])
    stats = compare_result.get("stats", {})
    type_a = compare_result.get("type_a", "unknown")
    type_b = compare_result.get("type_b", "unknown")

    n_full = stats.get("n_full", 0)
    n_high = stats.get("n_high", 0)
    n_partial = stats.get("n_partial", 0)
    n_low = stats.get("n_low", 0)
    n_only_a = stats.get("n_only_a", 0)
    n_only_b = stats.get("n_only_b", 0)
    n_matched = stats.get("n_matched", 0)
    overall_sim = stats.get("overall_sim", 0.0)
    # 计算匹配平均（匹配上的章节的平均相似度）
    matched_avg = overall_sim  # 如果没有单独的 matched_avg，使用 overall_sim

    # 判定结果
    if overall_sim >= 0.80:
        verdict_icon = "✅"
        verdict_text = "自动通过（≥80%）"
        verdict_class = "ok"
    elif overall_sim >= 0.60:
        verdict_icon = "⚠️"
        verdict_text = "建议复核（60% ~ 80%）"
        verdict_class = "warn"
    else:
        verdict_icon = "🟥"
        verdict_text = "强制人工复核（<60%，不可互换）"
        verdict_class = "danger"

    ts = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")

    # 格式类型映射
    type_map = {
        "docx": "Word (.docx)",
        "doc": "Word (.doc)",
        "pdf": "PDF",
        "md": "Markdown",
        "text": "纯文本"
    }
    type_a_display = type_map.get(type_a, type_a.upper())
    type_b_display = type_map.get(type_b, type_b.upper())

    # 复用 DITA 报告的 CSS
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

    def get_row_class(status):
        if status == "完全一致":
            return "ok-row"
        elif status == "高度相似":
            return "high-row"
        elif status == "部分相似":
            return "mid-row"
        else:
            return "low-row"

    def compute_word_diff(text_a, text_b):
        """计算词级 diff"""
        if not text_a or not text_b:
            return {"a_html": html.escape(text_a or ""), "b_html": html.escape(text_b or "")}
        from difflib import SequenceMatcher
        sm = SequenceMatcher(None, text_a, text_b)
        a_parts = []
        b_parts = []
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            a_seg = text_a[i1:i2]
            b_seg = text_b[j1:j2]
            if tag == "equal":
                if a_seg:
                    a_parts.append(a_seg)
                if b_seg:
                    b_parts.append(b_seg)
            elif tag == "delete":
                if a_seg:
                    a_parts.append(f'<span class="del">{a_seg}</span>')
            elif tag == "insert":
                if b_seg:
                    b_parts.append(f'<span class="ins">{b_seg}</span>')
            elif tag == "replace":
                if a_seg:
                    a_parts.append(f'<span class="del">{a_seg}</span>')
                if b_seg:
                    b_parts.append(f'<span class="ins">{b_seg}</span>')
        return {"a_html": "".join(a_parts), "b_html": "".join(b_parts)}

    rows_html = []
    for idx, r in enumerate(results):
        diff_id = f"d{idx}"
        heading = html.escape(r.get("heading", "") or "")
        status = r.get("status", "")
        sim = r.get("similarity", 0.0)
        consistency_label = get_consistency_label(sim)
        row_class = get_row_class(status)

        # 状态显示
        if status == "仅在A中":
            status_display = "仅在 A"
            row_class = "only-a-row"
        elif status == "仅在B中":
            status_display = "仅在 B"
            row_class = "only-b-row"
        else:
            status_display = status

        # 差异说明（添加颜色标签）
        if status in ("仅在A中", "仅在B中"):
            diff_explain = f"🔵 {status}"
        elif status == "完全一致":
            diff_explain = "🟢 内容完全一致"
        elif status == "高度相似":
            diff_explain = "🟢 措辞调整"
        elif status == "部分相似":
            diff_explain = "🟠 内容变更"
        else:
            diff_explain = "🔴 差异较大"

        row_main = (
            f"<tr class='{row_class} row-main' data-target='{diff_id}'>"
            f"<td>{idx+1}</td>"
            f"<td>{heading}</td>"
            f"<td>{diff_explain}</td>"
            f"<td>{consistency_label}</td>"
            f"</tr>"
        )

        # 差异详情（添加颜色标签）
        diffs_content = ""
        if status in ("仅在A中", "仅在B中"):
            content = r.get("content_a") or r.get("content_b") or ""
            diffs_content = f"<div class='diff-empty'>✓ {status}，无对比内容</div>"
        elif r.get("diffs"):
            diffs = []
            for d in r.get("diffs", [])[:15]:
                d_html = compute_word_diff(d.get("a", ""), d.get("b", ""))
                # 根据相似度添加颜色标签
                score = d.get("score", 0.0)
                if score >= 0.95:
                    tag_icon = "🟢"
                elif score >= 0.70:
                    tag_icon = "🟠"
                else:
                    tag_icon = "🔴"
                tag_type = d.get("type", "fuzzy")
                diffs.append(
                    f'<div class="diff-row changed">'
                    f'<span class="tag-c">{tag_icon} {tag_type}</span>'
                    f'<div class="text">'
                    f'<div class="side-a">{d_html["a_html"]}</div>'
                    f'<div class="side-b">{d_html["b_html"]}</div>'
                    f'</div></div>'
                )
            diffs_content = "\n".join(diffs)
        else:
            diffs_content = "<div class='diff-empty'>✓ 该章节内容完全一致，无差异</div>"

        row_diff = (
            f"<tr class='row-diff' id='{diff_id}'>"
            f"<td colspan='4'><div class='diffs'>{diffs_content}</div></td>"
            f"</tr>"
        )

        rows_html.append(row_main + row_diff)

    rows_str = "\n".join(rows_html) if rows_html else "<tr><td colspan='4' style='text-align:center;padding:40px;color:#888'>无章节数据</td></tr>"

    table_html = f"""
<h2>章节对比明细</h2>
<table class='summary'>
  <thead>
    <tr>
      <th>序号</th>
      <th>章节标题</th>
      <th>差异说明</th>
      <th>一致性</th>
    </tr>
  </thead>
  <tbody>
    {rows_str}
  </tbody>
</table>
"""

    # 结论与建议（根据实际数据生成）
    low_chapters = [r for r in results if r.get("similarity", 0) < 0.70 and r.get("status") not in ("仅在A中", "仅在B中")]
    partial_chapters = [r for r in results if 0.70 <= r.get("similarity", 0) < 0.95 and r.get("status") not in ("仅在A中", "仅在B中")]
    high_chapters = [r for r in results if 0.95 <= r.get("similarity", 0) and r.get("status") not in ("仅在A中", "仅在B中")]

    review_focus = []
    if low_chapters:
        review_focus.append(f"<li><b>差异较大章节（&lt;70%）</b>：{', '.join(html.escape(r.get('heading', '') or '') for r in low_chapters[:5])}</li>")
    if partial_chapters:
        review_focus.append(f"<li><b>部分相似章节（70%~95%）</b>：{', '.join(html.escape(r.get('heading', '') or '') for r in partial_chapters[:5])}</li>")
    if n_only_a > 0:
        review_focus.append(f"<li><b>仅在 A 的章节（{n_only_a} 个）</b>：需确认是否需要迁移到 B 文档</li>")
    if n_only_b > 0:
        review_focus.append(f"<li><b>仅在 B 的章节（{n_only_b} 个）</b>：需确认是否为新增内容</li>")

    # 如果没有复核重点，显示正面结果
    if not review_focus:
        review_focus.append("<li><b>✓ 所有章节内容高度一致</b>，本次对比结果良好</li>")

    # 根据实际数据生成复核建议
    suggestions = []
    if low_chapters:
        suggestions.append("<li>建议优先复核差异较大章节，确认内容变更是否符合预期</li>")
    if partial_chapters:
        suggestions.append("<li>部分相似章节需确认措辞调整是否影响技术含义</li>")
    # 检查是否有安全相关章节
    safety_keywords = ['安全', '电气', '警告', '注意', '危险', 'safety', 'warning', 'caution', 'danger']
    safety_chapters = [r for r in results if any(kw in (r.get('heading', '') or '').lower() for kw in safety_keywords)]
    if safety_chapters:
        suggestions.append("<li>安全相关章节（" + ', '.join(html.escape(r.get('heading', '') or '') for r in safety_chapters[:3]) + "）应重点确认</li>")
    # 检查是否有参数/数值相关章节
    param_keywords = ['参数', '规格', '数值', '电压', '温度', '速度', 'parameter', 'spec', 'value', 'voltage', 'temperature']
    param_chapters = [r for r in results if any(kw in (r.get('heading', '') or '').lower() for kw in param_keywords)]
    if param_chapters and any(r.get('similarity', 0) < 0.95 for r in param_chapters):
        suggestions.append("<li>参数/数值相关章节有变更，需核对技术规格是否同步</li>")
    if n_only_a > 0 or n_only_b > 0:
        suggestions.append("<li>仅在 A 或仅在 B 的章节需确认是否需同步或归档</li>")
    # 如果没有特殊建议，显示通用建议
    if not suggestions:
        suggestions.append("<li>本次对比结果良好，建议归档保存对比记录</li>")

    conclusion_html = f"""
<h2>结论与建议</h2>
<div class="file-info">
  <h3>判定</h3>
  <div class="file-info-grid">
    <div class="label">整体一致性</div>
    <div class="value">{overall_sim*100:.1f}%</div>
    <div class="label">判定结果</div>
    <div class="value">{verdict_icon} {html.escape(verdict_text)}</div>
  </div>

  <h3>复核重点</h3>
  <ul>
    {"".join(review_focus)}
  </ul>

  <h3>复核建议</h3>
  <ul>
    {"".join(suggestions)}
  </ul>
</div>
"""

    full_html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>文档对比报告</title>
<style>{css}</style>
</head>
<body>
<div class="wrap">
  <h1>文档对比报告</h1>
  <div class="meta">生成时间: {ts} &nbsp;|&nbsp; {html.escape(name_a)} &harr; {html.escape(name_b)} &nbsp;|&nbsp; <span style="color:#888">点击下方明细行可展开/收起差异详情</span></div>

  <div class="cards">
    <div class='card primary'>
      <div class='num'>{overall_sim*100:.1f}%</div>
      <div class='lbl'>整体一致性</div>
    </div>
    <div class='card '>
      <div class='num'>{matched_avg*100:.1f}%</div>
      <div class='lbl'>匹配平均</div>
    </div>
    <div class='card '>
      <div class='num'>{n_matched}</div>
      <div class='lbl'>匹配章节</div>
    </div>
    <div class='card '>
      <div class='num'>{n_full}</div>
      <div class='lbl'>完全一致</div>
    </div>
    <div class='card '>
      <div class='num'>{n_high}</div>
      <div class='lbl'>高度相似</div>
    </div>
    <div class='card '>
      <div class='num'>{n_partial}</div>
      <div class='lbl'>部分相似</div>
    </div>
    <div class='card '>
      <div class='num'>{n_low}</div>
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
      <div class="label">文件1</div>
      <div class="value">{html.escape(name_a)}</div>
      <div class="label">文件2</div>
      <div class="value">{html.escape(name_b)}</div>
      <div class="label">文件1格式</div>
      <div class="value">{type_a_display}</div>
      <div class="label">文件2格式</div>
      <div class="value">{type_b_display}</div>
    </div>
  </div>

  <div class="explain">
    <b>文档对比算法: 章节标题匹配 + 句子级模糊 Jaccard</b><br>
    按章节标题对齐两文档，对齐后按句子级对比计算相似度。<br>
    <span style="color:#888">判定：{verdict_icon} {html.escape(verdict_text)}</span>
  </div>

  {table_html}
  {conclusion_html}
</div>
<script>{js}</script>
</body>
</html>"""
    return full_html
