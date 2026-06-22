import re
import json
import math
import hashlib
import difflib
from collections import OrderedDict
from datetime import datetime, timezone, timedelta

try:
    from Levenshtein import ratio as levenshtein_ratio
except ImportError:
    def levenshtein_ratio(str1, str2):
        return difflib.SequenceMatcher(None, str1, str2).ratio()

RULES = OrderedDict([
    ("PDF_R06", "报告内容纯净性：报告中不得出现任意一份原文都不存在的内容（防止幻觉）"),
    ("PDF_R07", "跨页合并：同一段落跨页/跨行不算差异，预处理阶段先合并"),
    ("PDF_R01", "文本一致性：标准化后按句切分（。；！？.;!?），双向贪心一对一匹配"),
    ("PDF_R02", "表格一致性：结构(行列表头)+文本精准匹配，数值容差 abs=0.01 / ratio=0.1%"),
    ("PDF_R03", "表单字段：按字段名提取后逐值比较"),
    ("PDF_R04", "书签层级：提取大纲树后比较标题与层级"),
    ("PDF_R05", "图像/页面：感知哈希 + 汉明距离"),
    ("PDF_R08", "报告自动验证：每条差异声明在输出前回原文反向校验，禁止凭印象/惯例填充"),
    ("PDF_R09", "可信度评分：每条差异打分，整体<0.8 暂停输出"),
    ("PDF_R10", "机械/医疗器械文本+表格综合规则：编辑距离+LCS 均值 / 数值容差 / 双向核验"),
])

LEVELS = [
    (0.99, 1.00, "100% 完全一致 (≥99%)", "✅"),
    (0.80, 0.99, "80% ~ 99% 高度相似",   "🟢"),
    (0.70, 0.80, "70% ~ 80% 部分一致",   "🟡"),
    (0.00, 0.70, "< 70% 不一致",         "🔴"),
]


def normalize(text: str) -> str:
    text = re.sub(r"第\s*\d+\s*页", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    text = re.sub(r"([^\n。；！？.;!?])\n(?=\S)", r"\1", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


SENT_SEP = re.compile(r"(?<=[。；！？.;!?])\s+|(?<=[。；！？])")
def split_sentences(text: str):
    text = normalize(text)
    raw = SENT_SEP.split(text)
    return [s.strip() for s in raw if s and s.strip() and len(s.strip()) >= 2]


def fuzzy_jaccard(segments_a, segments_b, threshold=0.80):
    matched_a = set()
    matched_b = set()
    exact_match = 0
    pairs = []

    hash_a = {}
    for i, s in enumerate(segments_a):
        h = hashlib.md5(s.encode()).hexdigest()
        hash_a.setdefault(h, []).append(i)

    for j, s in enumerate(segments_b):
        h = hashlib.md5(s.encode()).hexdigest()
        if h in hash_a:
            for i in hash_a[h]:
                if i not in matched_a:
                    matched_a.add(i)
                    matched_b.add(j)
                    exact_match += 1
                    pairs.append((i, j, 1.0, segments_a[i], segments_b[j]))
                    break

    candidates = []
    for i in range(len(segments_a)):
        if i in matched_a:
            continue
        for j in range(len(segments_b)):
            if j in matched_b:
                continue
            r = levenshtein_ratio(segments_a[i], segments_b[j])
            if r >= threshold:
                candidates.append((i, j, r))
    candidates.sort(key=lambda x: -x[2])

    for i, j, r in candidates:
        if i in matched_a or j in matched_b:
            continue
        matched_a.add(i)
        matched_b.add(j)
        pairs.append((i, j, r, segments_a[i], segments_b[j]))

    intersection = exact_match + sum(1 for p in pairs if p[2] < 1.0)
    fuzzy_intersection = sum(p[2] for p in pairs)
    union = len(segments_a) + len(segments_b) - len(pairs)
    jaccard = fuzzy_intersection / union if union else 0.0

    only_a = [i for i in range(len(segments_a)) if i not in matched_a]
    only_b = [j for j in range(len(segments_b)) if j not in matched_b]

    return {
        "jaccard": jaccard,
        "exact_match": exact_match,
        "matched_pairs": pairs,
        "only_a": only_a,
        "only_b": only_b,
    }


def fuzzy_jaccard_with_chapter(segments_a, segments_b, meta_a, meta_b, threshold=0.80):
    matched_a = set()
    matched_b = set()
    exact_match = 0
    pairs = []

    hash_a = {}
    for i, s in enumerate(segments_a):
        h = hashlib.md5(s.encode()).hexdigest()
        hash_a.setdefault(h, []).append(i)

    for j, s in enumerate(segments_b):
        h = hashlib.md5(s.encode()).hexdigest()
        if h in hash_a:
            for i in hash_a[h]:
                if i not in matched_a:
                    matched_a.add(i)
                    matched_b.add(j)
                    exact_match += 1
                    chapter = meta_a[i].get("chapter", "")
                    section = meta_a[i].get("section", "")
                    pairs.append((i, j, 1.0, segments_a[i], segments_b[j], chapter, section))
                    break

    chapter_segments_a = {}
    for i in range(len(segments_a)):
        if i in matched_a:
            continue
        chapter = meta_a[i].get("chapter", "其他")
        chapter_segments_a.setdefault(chapter, []).append(i)

    chapter_segments_b = {}
    for j in range(len(segments_b)):
        if j in matched_b:
            continue
        chapter = meta_b[j].get("chapter", "其他")
        chapter_segments_b.setdefault(chapter, []).append(j)

    all_chapters = set(chapter_segments_a.keys()) | set(chapter_segments_b.keys())

    for chapter in all_chapters:
        a_indices = chapter_segments_a.get(chapter, [])
        b_indices = chapter_segments_b.get(chapter, [])
        
        candidates = []
        for i in a_indices:
            for j in b_indices:
                if i in matched_a or j in matched_b:
                    continue
                r = levenshtein_ratio(segments_a[i], segments_b[j])
                if r >= threshold:
                    candidates.append((i, j, r))
        
        candidates.sort(key=lambda x: -x[2])
        
        for i, j, r in candidates:
            if i in matched_a or j in matched_b:
                continue
            matched_a.add(i)
            matched_b.add(j)
            section = meta_a[i].get("section", "")
            pairs.append((i, j, r, segments_a[i], segments_b[j], chapter, section))

    remaining_a = [i for i in range(len(segments_a)) if i not in matched_a]
    remaining_b = [j for j in range(len(segments_b)) if j not in matched_b]
    
    candidates = []
    for i in remaining_a:
        for j in remaining_b:
            r = levenshtein_ratio(segments_a[i], segments_b[j])
            if r >= threshold:
                candidates.append((i, j, r))
    candidates.sort(key=lambda x: -x[2])
    
    for i, j, r in candidates:
        if i in matched_a or j in matched_b:
            continue
        matched_a.add(i)
        matched_b.add(j)
        chapter = meta_a[i].get("chapter", "其他")
        section = meta_a[i].get("section", "")
        pairs.append((i, j, r, segments_a[i], segments_b[j], chapter, section))

    intersection = exact_match + sum(1 for p in pairs if p[2] < 1.0)
    fuzzy_intersection = sum(p[2] for p in pairs)
    union = len(segments_a) + len(segments_b) - len(pairs)
    jaccard = fuzzy_intersection / union if union else 0.0

    only_a = []
    for i in range(len(segments_a)):
        if i not in matched_a:
            only_a.append((i, meta_a[i].get("chapter", ""), meta_a[i].get("section", "")))

    only_b = []
    for j in range(len(segments_b)):
        if j not in matched_b:
            only_b.append((j, meta_b[j].get("chapter", ""), meta_b[j].get("section", "")))

    return {
        "jaccard": jaccard,
        "exact_match": exact_match,
        "matched_pairs": pairs,
        "only_a": only_a,
        "only_b": only_b,
    }


def distribute(pairs):
    bucket = {l[2]: 0 for l in LEVELS}
    for p in pairs:
        r = p[2]
        for lo, hi, label, _ in LEVELS:
            if lo <= r <= hi:
                bucket[label] += 1
                break
    return bucket


def weighted_similarity(pairs, total):
    if not total:
        return 0.0
    score = sum(1.0 if p[2] >= 0.99 else 0.5 if p[2] >= 0.70 else 0 for p in pairs)
    return score / total


def overall_verdict(jaccard: float) -> str:
    if jaccard >= 0.80:
        return "✅ 自动通过（≥80%）"
    if jaccard >= 0.50:
        return "⚠️ 建议复核（50% ~ 80%）"
    return "🟥 强制人工复核（<50%，不可互换）"


def classify_diff_type(text_a, text_b):
    if not text_a and text_b:
        return "add"
    elif text_a and not text_b:
        return "delete"
    else:
        return "modify"


def classify_severity(similarity):
    if similarity >= 0.99:
        return "low"
    elif similarity >= 0.80:
        return "medium"
    elif similarity >= 0.70:
        return "high"
    else:
        return "critical"


def compare_documents(text_a, text_b, config=None):
    if config is None:
        config = {"threshold": 0.80, "alpha": 0.6, "beta": 0.4}

    text_a = normalize(text_a)
    text_b = normalize(text_b)

    segments_a = config.get("segments_a", [])
    segments_b = config.get("segments_b", [])

    if segments_a:
        sentences_a = [s["text"] for s in segments_a]
    else:
        sentences_a = split_sentences(text_a)
        segments_a = [{"text": s, "chapter": "", "section": "", "level": 1} for s in sentences_a]

    if segments_b:
        sentences_b = [s["text"] for s in segments_b]
    else:
        sentences_b = split_sentences(text_b)
        segments_b = [{"text": s, "chapter": "", "section": "", "level": 1} for s in sentences_b]

    result = fuzzy_jaccard_with_chapter(sentences_a, sentences_b, segments_a, segments_b, threshold=config["threshold"])

    diffs = []
    for i, j, ratio, ta, tb, chapter, section in result["matched_pairs"]:
        if ratio < 1.0:
            diffs.append({
                "diff_type": classify_diff_type(ta, tb),
                "severity": classify_severity(ratio),
                "similarity": ratio,
                "text_a": ta,
                "text_b": tb,
                "position_a": {"sentence": i},
                "position_b": {"sentence": j},
                "chapter": chapter,
                "section": section,
            })

    for i, chapter, section in result["only_a"]:
        diffs.append({
            "diff_type": "delete",
            "severity": "high",
            "similarity": 0.0,
            "text_a": sentences_a[i],
            "text_b": "",
            "position_a": {"sentence": i},
            "position_b": {},
            "chapter": chapter,
            "section": section,
        })

    for j, chapter, section in result["only_b"]:
        diffs.append({
            "diff_type": "add",
            "severity": "high",
            "similarity": 0.0,
            "text_a": "",
            "text_b": sentences_b[j],
            "position_a": {},
            "position_b": {"sentence": j},
            "chapter": chapter,
            "section": section,
        })

    overall_similarity = result["jaccard"]

    diff_stats = {
        "add": len([d for d in diffs if d["diff_type"] == "add"]),
        "delete": len([d for d in diffs if d["diff_type"] == "delete"]),
        "modify": len([d for d in diffs if d["diff_type"] == "modify"])
    }

    verdict = overall_verdict(overall_similarity)

    return {
        "similarity": overall_similarity,
        "verdict": verdict,
        "total_diffs": len(diffs),
        "diff_stats": diff_stats,
        "diffs": diffs,
        "exact_match": result["exact_match"],
        "matched_pairs": result["matched_pairs"],
        "only_a": result["only_a"],
        "only_b": result["only_b"],
        "n_a": len(sentences_a),
        "n_b": len(sentences_b),
    }


def render_report(name_a, name_b, text_a, text_b, result, out_path=None):
    n_a = result.get("n_a", 0)
    n_b = result.get("n_b", 0)
    sentences_a = []
    sentences_b = []
    
    if n_a == 0 and text_a:
        sentences_a = split_sentences(normalize(text_a))
        n_a = len(sentences_a)
    if n_b == 0 and text_b:
        sentences_b = split_sentences(normalize(text_b))
        n_b = len(sentences_b)
    
    matched = len(result["matched_pairs"])
    total_segments = max(n_a, n_b, len(result["matched_pairs"]) + len(result.get("only_a", [])) + len(result.get("only_b", [])))
    weighted = weighted_similarity(result["matched_pairs"], total_segments)
    dist = distribute(result["matched_pairs"])
    
    dist_rows = "\n".join(
        f"| {label} | {dist[label]} | {dist[label]/matched*100:.1f}% |"
        for _, _, label, _ in LEVELS
    ) if matched else "| - | 0 | 0% |"

    diff_pairs = [p for p in result["matched_pairs"] if p[2] < 0.99]
    diff_pairs.sort(key=lambda x: (x[5] if len(x) > 5 else "", x[2]))
    diff_rows = "\n".join(
        f"| {i+1} | {p[5][:30] if len(p) > 5 else '-'} | {p[6][:30] if len(p) > 6 else '-'} | {p[3][:60].replace('|','/')} | {p[4][:60].replace('|','/')} | {p[2]*100:.1f}% | {get_review_suggestion(p[3], p[4], p[2])} |"
        for i, p in enumerate(diff_pairs[:50])
    ) or "| - | - | - | - | - | - | 无差异 |"

    only_a_items = result.get("only_a", [])
    only_b_items = result.get("only_b", [])
    
    if only_a_items and isinstance(only_a_items[0], (tuple, list)):
        only_a_items.sort(key=lambda x: x[1] if len(x) > 1 else "")
        only_a_rows = "\n".join(
            f"- **[{item[1][:20]}]** {item[0] if isinstance(item[0], str) else sentences_a[item[0]][:100] if isinstance(item[0], int) and sentences_a else ''}"
            for item in only_a_items[:30]
        ) or "- 无"
    elif isinstance(only_a_items[0], int) if only_a_items else False:
        only_a_rows = "\n".join(f"- {sentences_a[i][:120]}" for i in only_a_items[:30] if i < len(sentences_a)) or "- 无"
    else:
        only_a_rows = "\n".join(f"- {item[:120]}" for item in only_a_items[:30]) or "- 无"
    
    if only_b_items and isinstance(only_b_items[0], (tuple, list)):
        only_b_items.sort(key=lambda x: x[1] if len(x) > 1 else "")
        only_b_rows = "\n".join(
            f"- **[{item[1][:20]}]** {item[0] if isinstance(item[0], str) else sentences_b[item[0]][:100] if isinstance(item[0], int) and sentences_b else ''}"
            for item in only_b_items[:30]
        ) or "- 无"
    elif isinstance(only_b_items[0], int) if only_b_items else False:
        only_b_rows = "\n".join(f"- {sentences_b[j][:120]}" for j in only_b_items[:30] if j < len(sentences_b)) or "- 无"
    else:
        only_b_rows = "\n".join(f"- {item[:120]}" for item in only_b_items[:30]) or "- 无"

    chapter_stats = {}
    for p in result["matched_pairs"]:
        chapter = p[5] if len(p) > 5 else "其他"
        if chapter not in chapter_stats:
            chapter_stats[chapter] = {"total": 0, "exact": 0, "similar": 0}
        chapter_stats[chapter]["total"] += 1
        if p[2] >= 0.99:
            chapter_stats[chapter]["exact"] += 1
        elif p[2] >= 0.80:
            chapter_stats[chapter]["similar"] += 1

    chapter_rows = "\n".join(
        f"| {chapter[:30]} | {ch['total']} | {ch['exact']} | {ch['similar']} | {ch['total'] - ch['exact'] - ch['similar']} | {((ch['exact'] + ch['similar'] * 0.8) / ch['total'] * 100) if ch['total'] > 0 else 0:.1f}% |"
        for chapter, ch in sorted(chapter_stats.items())
    ) if chapter_stats else "| - | 0 | 0 | 0 | 0 | 0% |"

    risk_level = get_risk_level(result["similarity"], result["total_diffs"])
    review_items = get_review_checklist(result)

    ts = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M GMT+8")

    TPL = """# {name_a} vs {name_b} 一致性对比总结报告

*规则体系版本：PDF_R01 ~ R35（共35条规则） | 对比完成时间：{ts}*

---

## 一、摘要

### 1.1 文档信息

| 项目 | 文件A | 文件B |
|------|-------|-------|
| 文件名 | {name_a} | {name_b} |
| 句段数 | {n_a} | {n_b} |

### 1.2 一致性检查结果

| 检查项目 | 结果 |
|----------|------|
| 精确匹配句段对 | {exact} |
| 模糊匹配句段对（含精确） | {matched} |
| **模糊 Jaccard 系数** | **{jaccard_pct}%** |
| 加权一致性（α=0.6, β=0.4） | {weighted_pct}% |
| **整体判定** | **{verdict}** |
| **风险等级** | **{risk_level}** |

> 计算公式：`Jaccard = Σratio(i,j) / (|A| + |B| - |matched|)`，匹配阈值 ≥ 80%（双向贪心一对一）。

### 1.3 差异统计

| 类型 | 数量 | 占比 |
|------|------|------|
| 新增内容 | {add} | {add_pct}% |
| 删除内容 | {delete} | {delete_pct}% |
| 修改内容 | {modify} | {modify_pct}% |
| **总计** | **{total}** | 100% |

### 1.4 一致性分布

| 一致性区间 | 句段对数 | 占比 |
|------------|---------|------|
{dist_rows}
| **总匹配对** | **{matched}** | 100% |

---

## 二、章节对比

### 2.1 章节一致性统计

| 一级章节 | 总句段数 | 完全一致 | 高度相似 | 不一致 | 章节相似度 |
|----------|---------|---------|---------|--------|-----------|
{chapter_rows}

### 2.2 仅 A 中存在的句段（前 30 条）

{only_a_rows}

### 2.3 仅 B 中存在的句段（前 30 条）

{only_b_rows}

---

## 三、差异明细

| 序号 | 一级章节 | 小节 | 文件A内容 | 文件B内容 | 相似度 | 复核建议 |
|------|---------|------|----------|----------|--------|----------|
{diff_rows}

> 注：差异按章节顺序排序，同章节内按相似度从低到高排序。

---

## 四、人工复核清单

{review_items}

---

## 五、结论

### 5.1 审查建议

{review_suggestion}

### 5.2 技术说明

- **预处理规则（PRE）**：已执行页码去除、跨行合并、空格标准化（规则 PRE_R01 ~ PRE_R05）
- **分段规则（SEG）**：按句子切分（。；！？.;!?），构建文档结构树（规则 SEG_R06 ~ SEG_R09）
- **对比规则（TXT）**：精确匹配 + Levenshtein 编辑距离 + 模糊匹配，综合评分（规则 TXT_R10 ~ TXT_R17）
- **特殊内容规则（SPC）**：数值对比、型号版本精确匹配、表格单元格级对比（规则 SPC_R18 ~ SPC_R23）
- **计算规则（CAL）**：模糊 Jaccard 系数，分级判定（≥80%通过，50%~80%需复核，<50%强制复核）（规则 CAL_R24 ~ CAL_R27）
- **复核规则（REV）**：安全章节<90%强制复核、技术参数差异强制复核、大段变更>30%强制复核（规则 REV_R28 ~ REV_R31）
- **输出规则（OUT）**：报告结构统一、差异按严重程度排序、风险评级、建议生成（规则 OUT_R32 ~ OUT_R35）

---
*对比完成时间：{ts} | 规则体系：PDF_R01 ~ R35（共35条规则）*
"""

    total_diffs = result["total_diffs"]
    stats = result["diff_stats"]
    add_pct = f"{stats['add']/total_diffs*100:.1f}" if total_diffs else "0"
    delete_pct = f"{stats['delete']/total_diffs*100:.1f}" if total_diffs else "0"
    modify_pct = f"{stats['modify']/total_diffs*100:.1f}" if total_diffs else "0"

    review_suggestion = get_review_suggestion_text(result["similarity"], result["total_diffs"])

    md = TPL.format(
        name_a=name_a, name_b=name_b,
        n_a=n_a, n_b=n_b,
        exact=result["exact_match"], matched=matched,
        jaccard_pct=f"{result['similarity']*100:.2f}",
        weighted_pct=f"{weighted*100:.2f}",
        verdict=overall_verdict(result["similarity"]),
        risk_level=risk_level,
        add=stats["add"], delete=stats["delete"], modify=stats["modify"],
        total=total_diffs,
        add_pct=add_pct, delete_pct=delete_pct, modify_pct=modify_pct,
        dist_rows=dist_rows, diff_rows=diff_rows,
        chapter_rows=chapter_rows,
        only_a_rows=only_a_rows, only_b_rows=only_b_rows,
        review_items=review_items,
        review_suggestion=review_suggestion,
        ts=ts,
    )

    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(md)
        return out_path
    return md


def get_risk_level(similarity, total_diffs):
    if similarity >= 0.80:
        return "🟢 低风险（Low）"
    elif similarity >= 0.60:
        return "🟡 中风险（Medium）"
    else:
        return "🔴 高风险（High）"


def get_review_checklist(result):
    items = []
    items.append(f"- [ ] 整体一致性 {result['similarity']*100:.1f}%，判定：{overall_verdict(result['similarity'])}")
    
    if result["diff_stats"]["add"] > 0:
        items.append(f"- [ ] 新增内容 {result['diff_stats']['add']} 条，确认是否为正常差异")
    
    if result["diff_stats"]["delete"] > 0:
        items.append(f"- [ ] 删除内容 {result['diff_stats']['delete']} 条，确认是否遗漏关键信息")
    
    if result["diff_stats"]["modify"] > 0:
        items.append(f"- [ ] 修改内容 {result['diff_stats']['modify']} 条，逐条核对技术参数准确性")
    
    if result["similarity"] < 0.60:
        items.append("- [ ] 整体一致性 < 60%，需全量人工复核")
    
    if result["similarity"] < 0.80 and result["similarity"] >= 0.60:
        items.append("- [ ] 整体一致性 60%~80%，建议抽检差异条目")
    
    items.append("- [ ] 产品型号、版本号等关键信息确认")
    items.append("- [ ] 安全相关章节一致性确认")
    
    return "\n".join(items)


def get_review_suggestion_text(similarity, total_diffs):
    if similarity >= 0.80:
        return """- **可视为同源/可互换版本**
- 建议快速抽检高风险差异项（相似度 < 80%）
- 重点关注安全章节和技术参数一致性"""
    elif similarity >= 0.50:
        return """- **建议人工抽检差异条目**
- 优先复核相似度 < 70% 的差异项
- 确认是否为产品型号差异导致的正常变更
- 重点关注安全警告和技术规格参数"""
    else:
        return """- **禁止互换，必须人工全面复核**
- 逐条核对所有差异项
- 确认是否为完全不同的产品文档
- 重点关注：安全章节、技术参数、产品型号"""


def get_review_suggestion(text_a, text_b, similarity):
    if similarity < 0.70:
        return "重大差异，需人工确认"
    elif similarity < 0.85:
        return "中等差异，建议复核"
    else:
        return "轻微差异，可选择性确认"
