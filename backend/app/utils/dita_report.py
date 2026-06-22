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

    if diff["type"] == "modify":
        return (
            f'<div class="diff-row changed">'
            f'<span class="tag-c">A → B</span>'
            f'<div class="text">'
            f'<div class="side-a">{a}</div>'
            f'<div class="side-b">{b}</div>'
            f'</div></div>'
        )
    elif diff["type"] == "only_a":
        return (
            f'<div class="diff-row changed">'
            f'<span class="tag-c">A 独有</span>'
            f'<div class="text">'
            f'<div class="side-a">{a}</div>'
            f'</div></div>'
        )
    elif diff["type"] == "only_b":
        return (
            f'<div class="diff-row changed">'
            f'<span class="tag-c">B 独有</span>'
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
    full = cr.get("stat_full_match", 0)
    high = cr.get("stat_high", 0)
    partial = cr.get("stat_partial", 0)
    low = cr.get("stat_low", 0)
    jaccard = cr.get("overall_jaccard", 0.0)
    weighted = cr.get("weighted_sim", 0.0)
    avg_match = cr.get("avg_match", 0.0)
    n_sent_a = cr.get("n_sentences_a", 0)
    n_sent_b = cr.get("n_sentences_b", 0)
    n_pairs = cr.get("n_matched_pairs", 0)

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
        elif sim >= 0.80:
            return "80%~95%"
        elif sim >= 0.70:
            return "70%~80%"
        elif sim >= 0.60:
            return "60%~70%"
        else:
            return "<60%"

    def get_diff_explanation(tr):
        diffs = tr.get("diffs", [])
        sim = tr.get("topic_sim", 0.0)
        
        if not diffs:
            return "内容一致，无差异"

        type_counts = {"modify": 0, "only_a": 0, "only_b": 0}
        for d in diffs:
            t = d.get("type", "")
            if t in type_counts:
                type_counts[t] += 1

        if sim >= 0.95:
            return "微小差异：主要为型号、编号、日期、个别措辞或短句调整，正文结构基本一致"
        elif sim >= 0.80:
            return "部分差异：章节主题一致，但参数、步骤、部件名称或局部条款存在调整"
        else:
            return "差异较大：章节内容、结构、参数或操作程序存在明显差异，需展开明细复核"

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
            f"<td>—</td>"
            f"<td>—</td>"
            f"<td>{html.escape(get_diff_explanation(tr))}</td>"
            f"<td>{consistency_label}</td>"
            f"</tr>"
        )

        diffs = tr.get("diffs", [])
        if diffs:
            diffs_content = "\n".join(_diff_html(d) for d in diffs[:15])
            row_diff = (
                f"<tr class='row-diff' id='{diff_id}'>"
                f"<td colspan='7'><div class='diffs'>{diffs_content}</div></td>"
                f"</tr>"
            )
        else:
            row_diff = (
                f"<tr class='row-diff' id='{diff_id}'>"
                f"<td colspan='7'><div class='diff-empty'>✓ 该 topic 句段全部完全一致，无差异</div></td>"
                f"</tr>"
            )

        rows_html.append(row_main + row_diff)

    rows_str = "\n".join(rows_html) if rows_html else "<tr><td colspan='7' style='text-align:center;padding:40px;color:#888'>无 topic 数据</td></tr>"

    table_html = f"""
<h2>差异点汇总 (按 ditamap 中 topic 顺序)</h2>
<table class='summary'>
  <thead>
    <tr>
      <th>序号</th>
      <th>一级章节</th>
      <th>小节 (按 A 包 ditamap 顺序)</th>
      <th>文件1 PDF 页码</th>
      <th>文件2 PDF 页码</th>
      <th>差异说明</th>
      <th>一致性</th>
    </tr>
  </thead>
  <tbody>
    {rows_str}
  </tbody>
</table>
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
</div>
<script>{js}</script>
</body>
</html>"""
    return full_html
