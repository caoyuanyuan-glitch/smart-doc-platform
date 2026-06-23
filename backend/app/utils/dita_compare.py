"""
DITA 数据包对比核心算法
按 ditamap topic 对齐 + 句段级模糊 Jaccard + topic 级一致性聚合

设计参考 dita_jaccard.py（comparison_package 内）：
- 解析 ditamap，按 navtitle 标准化匹配 topic
- 对每个匹配上的 topic 抽出纯文本句段，跑模糊 Jaccard
- 汇总 topic 级一致性、未匹配 topic 清单、词级 diff
"""
import re
import os
import json
import hashlib
from difflib import SequenceMatcher
from xml.etree import ElementTree as ET

try:
    from Levenshtein import ratio as levenshtein_ratio
except ImportError:
    def levenshtein_ratio(s1, s2):
        return SequenceMatcher(None, s1, s2).ratio()


def strip_ns(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def normalize_text(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"\s+", " ", s).strip()
    return s


def tokenize_sentences(text: str):
    """按 . ! ? 。 ！ ？ ; ； 切分句段"""
    if not text:
        return []
    text = normalize_text(text)
    parts = re.split(r"(?<=[.!?。！？;；])\s+", text)
    return [p.strip() for p in parts if p and len(p.strip()) >= 2]


# 标准化 navtitle 用于匹配
def normalize_navtitle(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"\s+", " ", s).strip().lower()
    s = re.sub(r"[^\w\s]", "", s)
    return s


def extract_topic_text(dita_path: str) -> dict:
    """
    从 .dita 文件提取文本：title, 句段
    返回 {"topic_id", "title", "sentences": [...], "raw_text": "..."}
    统一句段切分规则（根据优化指令）：
    - 表格按行拆分（每行一个句段，合并所有单元格文本）
    - 列表按项拆分（每项一个句段）
    - 提取文本标签：p、li、entry、note、title、shortdesc、step、cmd 等
    - 过滤空句段和纯空格句段
    - 过滤纯 XML 标签内容（如 ph、b、i、u 等内联标签不单独成句段）
    """
    result = {"topic_id": "", "title": "", "sentences": [], "raw_text": ""}
    try:
        tree = ET.parse(dita_path)
        root = tree.getroot()
    except Exception:
        try:
            with open(dita_path, "r", encoding="utf-8", errors="ignore") as f:
                result["raw_text"] = f.read()
                result["sentences"] = tokenize_sentences(result["raw_text"])
        except Exception:
            pass
        return result

    result["topic_id"] = root.attrib.get("id", "")

    title_el = root.find(".//title")
    if title_el is not None and title_el.text:
        result["title"] = normalize_text(title_el.text)

    text_parts = []
    if result["title"]:
        text_parts.append(result["title"])

    # 需要处理的文本标签
    block_tags = {"p", "li", "note", "step", "shortdesc", "cmd", "entry", 
                  "dt", "dd", "stentry", "refsyn", "conbodydiv",
                  "section", "paragraph"}
    
    # 内联标签（不单独成句段）
    inline_tags = {"ph", "b", "i", "u", "strong", "em", "tt", "codeph",
                   "keyword", "tm", "sup", "sub", "xref", "linktext"}
    
    def get_text(elem, include_tail=True):
        """递归获取元素的文本内容，包括 tail"""
        parts = []
        if elem.text:
            parts.append(elem.text)
        for child in elem:
            if strip_ns(child.tag) not in inline_tags:
                parts.append(get_text(child))
            else:
                if child.text:
                    parts.append(child.text)
                if include_tail and child.tail:
                    parts.append(child.tail)
        if include_tail and elem.tail:
            parts.append(elem.tail)
        return "".join(parts).strip()
    
    def process_table(table_elem):
        """处理表格，按行拆分"""
        rows = table_elem.findall(".//tr")
        for row in rows:
            cells = row.findall(".//entry")
            if cells:
                cell_texts = []
                for cell in cells:
                    cell_text = get_text(cell)
                    if cell_text:
                        cell_texts.append(cell_text)
                if cell_texts:
                    row_text = " | ".join(cell_texts)
                    if row_text.strip():
                        text_parts.append(row_text)
    
    def process_list(list_elem, list_type="ul"):
        """处理列表，按项拆分"""
        items = list_elem.findall(f"./{list_type}/li") or list_elem.findall(".//li")
        for item in items:
            item_text = get_text(item)
            if item_text.strip():
                text_parts.append(item_text)
    
    def walk_elem(elem):
        """遍历元素并提取文本"""
        tag = strip_ns(elem.tag)
        
        # 处理表格
        if tag in ("table", "simpletable"):
            process_table(elem)
            return
        
        # 处理列表
        if tag in ("ul", "ol", "sl"):
            process_list(elem, tag)
            return
        
        # 处理块级标签
        if tag in block_tags:
            text = get_text(elem)
            if text:
                text_parts.append(text)
        
        # 处理图片
        if tag == "fig":
            caption_el = elem.find(".//title")
            if caption_el is not None and caption_el.text:
                text_parts.append(f"[图] {normalize_text(caption_el.text)}")
        
        # 递归处理子元素
        for child in elem:
            walk_elem(child)
    
    # 从 topic 或 concept/mainbody 开始遍历
    main_body = root.find(".//topic") or root.find(".//concept") or root.find(".//task") or root
    walk_elem(main_body)
    
    # 过滤空句段和纯空格句段
    text_parts = [t for t in text_parts if t.strip()]
    
    # 去重，相邻重复的句段只保留一个
    deduped = []
    prev_text = None
    for t in text_parts:
        if t != prev_text:
            deduped.append(t)
            prev_text = t

    full_text = " ".join(deduped)
    result["raw_text"] = full_text
    result["sentences"] = tokenize_sentences(full_text)
    return result


def parse_ditamap(ditamap_path: str):
    """
    解析 ditamap，按文档顺序提取 topic 列表。
    支持单行 XML 格式（用 > 拼接的 topicref）。
    """
    topics = []
    try:
        tree = ET.parse(ditamap_path)
        root = tree.getroot()
    except Exception:
        return topics

    def walk(node, ancestors):
        tag = strip_ns(node.tag)
        nav = (node.attrib.get("navtitle") or
               node.attrib.get("{http://www.w3.org/ime/cms}title") or "")
        href = node.attrib.get("href", "")
        keys = node.attrib.get("keys", "")
        level_attr = node.attrib.get("level", "")
        type_attr = (node.attrib.get("{http://www.w3.org/ime/cms}type") or
                     node.attrib.get("type", ""))

        path = ancestors + [nav] if nav else list(ancestors)

        if href and href.endswith(".dita"):
            topics.append({
                "tag": tag,
                "navtitle": nav,
                "href": href,
                "path": path,
                "level": int(level_attr) if level_attr.isdigit() else len(path),
                "topic_type": type_attr or tag,
                "keys": keys,
            })

        for child in node:
            walk(child, path)

    walk(root, [])
    return topics


def match_topics_by_navtitle(topics_a, topics_b):
    """
    按 navtitle 标准化匹配 A 和 B 的 topic。
    返回 (matched, only_a, only_b)：
    - matched: [(a_topic, b_topic, sim)]
    - only_a: [a_topic]
    - only_b: [b_topic]
    """
    norm_a = [(t, normalize_navtitle(t["navtitle"])) for t in topics_a]
    norm_b = [(t, normalize_navtitle(t["navtitle"])) for t in topics_b]

    matched = []
    used_b = set()

    for i, (ta, na) in enumerate(norm_a):
        if not na:
            continue
        best_j = -1
        best_sim = 0.0
        for j, (tb, nb) in enumerate(norm_b):
            if j in used_b or not nb:
                continue
            # 精确匹配优先
            if na == nb:
                best_sim = 1.0
                best_j = j
                break
            sim = levenshtein_ratio(na, nb)
            if sim > best_sim:
                best_sim = sim
                best_j = j
        if best_j >= 0 and best_sim >= 0.85:
            matched.append((ta, norm_b[best_j][0], best_sim))
            used_b.add(best_j)

    only_a = [t for (t, _) in norm_a if t not in [m[0] for m in matched]]
    only_b = [tb for (tb, _) in norm_b if tb not in [m[1] for m in matched]]
    return matched, only_a, only_b


def fuzzy_match_sentences(sentences_a, sentences_b, threshold=0.70):
    """
    对同一 topic 内的句段做模糊匹配（精确 + Levenshtein）。
    根据优化指令，匹配阈值从 ≥80% 调整为 ≥70%，使匹配对数量更合理。
    返回 (matched_pairs, only_a_indices, only_b_indices, exact_match_count)
    - matched_pairs: [(i, j, sim, ta, tb)]
    """
    matched_a = set()
    matched_b = set()
    pairs = []
    exact_match = 0

    # 精确匹配
    hash_a = {}
    for i, s in enumerate(sentences_a):
        h = hashlib.md5(s.encode()).hexdigest()
        hash_a.setdefault(h, []).append(i)

    for j, s in enumerate(sentences_b):
        h = hashlib.md5(s.encode()).hexdigest()
        if h in hash_a:
            for i in hash_a[h]:
                if i not in matched_a:
                    matched_a.add(i)
                    matched_b.add(j)
                    exact_match += 1
                    pairs.append((i, j, 1.0, sentences_a[i], sentences_b[j]))
                    break

    # 模糊匹配
    candidates = []
    for i in range(len(sentences_a)):
        if i in matched_a:
            continue
        for j in range(len(sentences_b)):
            if j in matched_b:
                continue
            r = levenshtein_ratio(sentences_a[i], sentences_b[j])
            if r >= threshold:
                candidates.append((i, j, r))
    candidates.sort(key=lambda x: -x[2])

    for i, j, r in candidates:
        if i in matched_a or j in matched_b:
            continue
        matched_a.add(i)
        matched_b.add(j)
        pairs.append((i, j, r, sentences_a[i], sentences_b[j]))

    only_a = [i for i in range(len(sentences_a)) if i not in matched_a]
    only_b = [j for j in range(len(sentences_b)) if j not in matched_b]
    return pairs, only_a, only_b, exact_match


def compute_topic_similarity(n_a, n_b, pairs, exact_match):
    """
    计算 topic 内的模糊 Jaccard 一致性。
    Jaccard = sum(sim) / (n_a + n_b - len(pairs))
    """
    if n_a == 0 and n_b == 0:
        return 1.0
    if not pairs:
        return 0.0
    union = n_a + n_b - len(pairs)
    if union <= 0:
        return 1.0
    fuzzy_intersection = sum(p[2] for p in pairs)
    return fuzzy_intersection / union


def classify_consistency(sim):
    """
    分类一致性等级（根据优化指令调整区间）。
    新区间：<50% / 50-70% / 70-85% / 85-95% / 95-99% / 100%
    严格区分"完全一致"（文本完全相同）和"高度相似"（≥95%）
    """
    if sim >= 0.99:
        return ("完全一致", "ok-row", "#2e7d32")
    if sim >= 0.95:
        return ("高度相似", "high-row", "#558b2f")
    if sim >= 0.85:
        return ("基本一致", "mid-row", "#ef6c00")
    if sim >= 0.70:
        return ("部分相似", "low-row", "#f57c00")
    if sim >= 0.50:
        return ("较大差异", "low-row", "#e65100")
    return ("差异较大", "low-row", "#c62828")


def compute_word_diff(text_a, text_b):
    """
    计算两段文本的词级 diff。
    返回 dict {a_html, b_html}，a 中被删除词用 <del> 包裹，b 中新增词用 <ins> 包裹。
    """
    if not text_a or not text_b:
        return {
            "a_html": text_a or "",
            "b_html": text_b or "",
        }

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


def _classify_severity(text_a, text_b, diff_type):
    """
    根据变更类型自动标记严重程度：
    - 安全警告变更 → critical（重大）
    - 参数/数值变更 → high（重要）
    - 措辞/冠词调整 → low（轻微）
    """
    combined = (text_a or "") + " " + (text_b or "")

    # 安全警告相关
    safety_keywords = [
        "warning", "caution", "danger", "警告", "注意", "危险",
        "must not", "do not", "must", "shall", "不得", "禁止", "严禁",
        "personal injury", "death", "electrocution", "人身伤害", "死亡", "触电"
    ]
    if any(kw in combined.lower() for kw in safety_keywords):
        return "critical"

    # 参数/数值变更
    import re
    param_pattern = re.compile(
        r'\d+\.?\d*\s*[kW℃°MLVVAΩHzkVkgcm]|'
        r'\d+\s*[Vv]|[0-9]+(?:\.[0-9]+)?\s*(?:mm|cm|m|kg|g|L|ml|Hz|kHz|MHz|nm|μm|W|kW|A|mA|μA|V|kV|°C|°F|%|rpm)',
        re.IGNORECASE
    )
    if param_pattern.search(text_a or "") or param_pattern.search(text_b or ""):
        return "high"

    # 默认识别为轻微
    return "low"


def _is_minor_modify(text_a, text_b, threshold=0.70):
    """
    判断是否为轻微修改（措辞调整、冠词/代词调整）
    threshold 降低以更好识别措辞调整
    """
    if not text_a or not text_b:
        return False
    # 空格变连字符、标点变化、同义词替换
    norm_a = text_a.replace(" - ", "-").replace(" ", "").replace(",", "").replace(".", "").lower()
    norm_b = text_b.replace(" - ", "-").replace(" ", "").replace(",", "").replace(".", "").lower()
    # 完全相同（去除格式后）视为轻微
    if norm_a == norm_b:
        return True
    # 计算 Jaccard
    set_a = set(text_a.lower().split())
    set_b = set(text_b.lower().split())
    if not set_a or not set_b:
        return False
    inter = len(set_a & set_b)
    union = len(set_a | set_b)
    return inter / union >= threshold


def _deduplicate_diffs(diffs):
    """
    对 diffs 去重：完全相同内容的 diff 只保留一条。
    判断标准：text_a 和 text_b 完全相同即为重复。
    """
    if not diffs:
        return diffs
    seen = set()
    result = []
    for d in diffs:
        key = (d.get("type", ""), d.get("text_a", ""), d.get("text_b", ""))
        if key not in seen:
            seen.add(key)
            result.append(d)
    return result


def _merge_adjacent_diffs(diffs, merge_minor=True, merge_only=True):
    """
    合并相邻的同类差异：
    - merge_minor: 多个连续的轻微修改（severity=low）合并为1条"措辞调整"
    - merge_only: 连续的 only_a / only_b 合并为1条
    """
    if not diffs:
        return diffs

    merged = []
    i = 0
    while i < len(diffs):
        d = diffs[i]

        # 尝试合并多个连续的轻微修改
        if merge_minor and d["type"] == "modify" and d.get("severity") == "low":
            # 收集所有连续的 severity=low 的 modify diff
            minor_group = [d]
            j = i + 1
            while j < len(diffs) and diffs[j]["type"] == "modify" and diffs[j].get("severity") == "low":
                if _is_minor_modify(diffs[j].get("text_a", ""), diffs[j].get("text_b", ""), threshold=0.70):
                    minor_group.append(diffs[j])
                    j += 1
                else:
                    break

            if len(minor_group) > 1:
                # 合并为一条
                first = minor_group[0]
                merged_texts_a = [first.get("text_a", "")]
                merged_texts_b = [first.get("text_b", "")]
                for m in minor_group[1:]:
                    merged_texts_a.append(m.get("text_a", ""))
                    merged_texts_b.append(m.get("text_b", ""))
                merged.append({
                    "type": "modify",
                    "text_a": " | ".join(merged_texts_a),
                    "text_b": " | ".join(merged_texts_b),
                    "a_html": " | ".join([m.get("a_html", "") for m in minor_group]),
                    "b_html": " | ".join([m.get("b_html", "") for m in minor_group]),
                    "similarity": min(m.get("similarity", 1.0) for m in minor_group),
                    "severity": "low",
                    "merged_count": len(minor_group),
                    "diff_label": "措辞调整",
                })
                i = j
                continue

        # 同类型的 only_a/only_b 合并
        if merge_only and d["type"] in ("only_a", "only_b"):
            if merged and merged[-1]["type"] == d["type"]:
                # 合并到上一条
                if d["type"] == "only_a":
                    prev_text = merged[-1].get("text_a", "")
                    merged[-1]["text_a"] = (prev_text + " " + d.get("text_a", "")).strip()
                    merged[-1]["a_html"] = (merged[-1].get("a_html", "") + " " + d.get("a_html", "")).strip()
                else:
                    prev_text = merged[-1].get("text_b", "")
                    merged[-1]["text_b"] = (prev_text + " " + d.get("text_b", "")).strip()
                    merged[-1]["b_html"] = (merged[-1].get("b_html", "") + " " + d.get("b_html", "")).strip()
                merged[-1]["merged_count"] = merged[-1].get("merged_count", 1) + 1
                i += 1
                continue

        merged.append(diffs[i])
        i += 1

    return merged


def build_topic_diff_details(topic_a_text, topic_b_text, threshold=0.80, max_diffs=10):
    """
    对单个 topic 内的句段对比，生成差异详情列表。
    每条 diff: {text_a, text_b, similarity, diff_html, severity, type}
    """
    pairs, only_a, only_b, exact = fuzzy_match_sentences(
        topic_a_text["sentences"], topic_b_text["sentences"], threshold
    )

    diffs = []
    # 修改的（< 0.99 相似度）
    for i, j, sim, ta, tb in pairs:
        if sim < 0.99:
            diff_html = compute_word_diff(ta, tb)
            severity = _classify_severity(ta, tb, "modify")
            diffs.append({
                "type": "modify",
                "text_a": ta,
                "text_b": tb,
                "similarity": sim,
                "a_html": diff_html["a_html"],
                "b_html": diff_html["b_html"],
                "severity": severity,
            })

    # 仅 A
    for i in only_a[:max_diffs]:
        text_a = topic_a_text["sentences"][i] if i < len(topic_a_text["sentences"]) else ""
        severity = _classify_severity(text_a, "", "only_a")
        diffs.append({
            "type": "only_a",
            "text_a": text_a,
            "text_b": "",
            "similarity": 0.0,
            "a_html": text_a,
            "b_html": "",
            "severity": severity,
        })

    # 仅 B
    for j in only_b[:max_diffs]:
        text_b = topic_b_text["sentences"][j] if j < len(topic_b_text["sentences"]) else ""
        severity = _classify_severity("", text_b, "only_b")
        diffs.append({
            "type": "only_b",
            "text_a": "",
            "text_b": text_b,
            "similarity": 0.0,
            "a_html": "",
            "b_html": text_b,
            "severity": severity,
        })

    # 合并相邻同类差异
    diffs = _merge_adjacent_diffs(diffs, merge_minor=True, merge_only=True)
    # 去重：完全相同的 diff 只保留一条
    diffs = _deduplicate_diffs(diffs)

    return diffs, len(pairs), exact, len(only_a), len(only_b)


def compare_dita_packages(dir_a: str, dir_b: str, threshold: float = 0.80) -> dict:
    """
    主对比入口。
    输入：两个 DITA 包解压后的目录
    输出：完整对比结果（含 topic 级 + 句段级数据 + 摘要）
    """
    # 1. 找 ditamap
    def find_ditamap(d):
        for root_dir, _, files in os.walk(d):
            for fn in files:
                if fn.lower().endswith(".ditamap"):
                    return os.path.join(root_dir, fn)
        return None

    map_a = find_ditamap(dir_a)
    map_b = find_ditamap(dir_b)

    if not map_a or not map_b:
        return {"error": "未找到 .ditamap 文件"}

    # 2. 解析 topic 列表
    raw_a = parse_ditamap(map_a)
    raw_b = parse_ditamap(map_b)

    base_a = os.path.dirname(map_a)
    base_b = os.path.dirname(map_b)

    # 3. 按 navtitle 匹配 topic
    matched, only_a_topics, only_b_topics = match_topics_by_navtitle(raw_a, raw_b)

    # 4. 对每个匹配的 topic 抽取文本并句段对比
    topic_results = []
    total_sentences_a = 0
    total_sentences_b = 0
    total_matched_pairs = 0
    total_exact = 0

    # 统计分类（与 classify_consistency 阈值对齐）
    # 新区间：<50% / 50-70% / 70-85% / 85-95% / 95-99% / 100%
    stat_full_match = 0      # 完全一致 (≥99%)
    stat_high = 0            # 高度相似 (95-99%)
    stat_mid = 0             # 基本一致 (85-95%)
    stat_partial = 0         # 部分相似 (70-85%)
    stat_low = 0              # 差异较大 (50-70%)
    stat_very_low = 0        # 差异很大 (<50%)

    for ta, tb, nav_sim in matched:
        path_a = os.path.join(base_a, ta["href"])
        path_b = os.path.join(base_b, tb["href"])

        text_a = extract_topic_text(path_a)
        text_b = extract_topic_text(path_b)

        diffs, n_pairs, n_exact, n_only_a, n_only_b = build_topic_diff_details(
            text_a, text_b, threshold=threshold
        )

        sim = compute_topic_similarity(
            len(text_a["sentences"]), len(text_b["sentences"]), [], n_exact
        )
        # 重新计算真正的相似度
        if text_a["sentences"] or text_b["sentences"]:
            from app.utils.dita_compare import fuzzy_match_sentences as fms
            pairs_real, _, _, _ = fms(text_a["sentences"], text_b["sentences"], threshold)
            sim = compute_topic_similarity(
                len(text_a["sentences"]), len(text_b["sentences"]),
                pairs_real, n_exact
            )

        consistency_label, row_class, bar_color = classify_consistency(sim)
        if sim >= 0.99:
            stat_full_match += 1
        elif sim >= 0.95:
            stat_high += 1
        elif sim >= 0.85:
            stat_mid += 1
        elif sim >= 0.70:
            stat_partial += 1
        elif sim >= 0.50:
            stat_low += 1
        else:
            stat_very_low += 1

        topic_results.append({
            "type": "matched",
            "href_a": ta["href"],
            "href_b": tb["href"],
            "navtitle": ta["navtitle"] or tb["navtitle"],
            "path_a": ta["path"],
            "path_b": tb["path"],
            "chapter_a": ta["path"][0] if ta["path"] else "",
            "chapter_b": tb["path"][0] if tb["path"] else "",
            "nav_sim": nav_sim,
            "topic_sim": sim,
            "consistency_label": consistency_label,
            "row_class": row_class,
            "bar_color": bar_color,
            "n_sentences_a": len(text_a["sentences"]),
            "n_sentences_b": len(text_b["sentences"]),
            "n_exact": n_exact,
            "n_diffs": len(diffs),
            "diffs": diffs,
            "tag": "topic_match",
        })

        total_sentences_a += len(text_a["sentences"])
        total_sentences_b += len(text_b["sentences"])
        total_matched_pairs += n_pairs
        total_exact += n_exact

    # 5. 仅 A 中存在的 topic
    for ta in only_a_topics:
        path_a = os.path.join(base_a, ta["href"])
        text_a = extract_topic_text(path_a)
        topic_results.append({
            "type": "only_a",
            "href_a": ta["href"],
            "href_b": "",
            "navtitle": ta["navtitle"],
            "path_a": ta["path"],
            "path_b": [],
            "chapter_a": ta["path"][0] if ta["path"] else "",
            "chapter_b": "",
            "nav_sim": 0.0,
            "topic_sim": 0.0,
            "consistency_label": "仅在 A",
            "row_class": "only-a-row",
            "bar_color": "#999",
            "n_sentences_a": len(text_a["sentences"]),
            "n_sentences_b": 0,
            "n_exact": 0,
            "n_diffs": len(text_a["sentences"]),
            "diffs": [{"type": "only_a", "text_a": s, "text_b": "", "similarity": 0.0,
                        "a_html": s, "b_html": ""} for s in text_a["sentences"][:10]],
            "tag": "only_a",
        })
        total_sentences_a += len(text_a["sentences"])

    for tb in only_b_topics:
        path_b = os.path.join(base_b, tb["href"])
        text_b = extract_topic_text(path_b)
        topic_results.append({
            "type": "only_b",
            "href_a": "",
            "href_b": tb["href"],
            "navtitle": tb["navtitle"],
            "path_a": [],
            "path_b": tb["path"],
            "chapter_a": "",
            "chapter_b": tb["path"][0] if tb["path"] else "",
            "nav_sim": 0.0,
            "topic_sim": 0.0,
            "consistency_label": "仅在 B",
            "row_class": "only-b-row",
            "bar_color": "#999",
            "n_sentences_a": 0,
            "n_sentences_b": len(text_b["sentences"]),
            "n_exact": 0,
            "n_diffs": len(text_b["sentences"]),
            "diffs": [{"type": "only_b", "text_a": "", "text_b": s, "similarity": 0.0,
                        "a_html": "", "b_html": s} for s in text_b["sentences"][:10]],
            "tag": "only_b",
        })
        total_sentences_b += len(text_b["sentences"])

    # 6. 计算整体指标
    n_topics_a = len(raw_a)
    n_topics_b = len(raw_b)
    n_matched_topics = len(matched)

    # 整体 Jaccard（句段级）
    overall_jaccard = 0.0
    if total_sentences_a + total_sentences_b > 0:
        union = total_sentences_a + total_sentences_b - total_matched_pairs
        if union > 0:
            overall_jaccard = total_matched_pairs / union

    # 加权一致性
    weighted_sim = 0.0
    total_topics = n_topics_a + n_topics_b
    if total_topics > 0:
        score = 0.0
        for tr in topic_results:
            if tr["type"] == "matched":
                if tr["topic_sim"] >= 0.99:
                    score += 1.0
                elif tr["topic_sim"] >= 0.70:
                    score += 0.5
            # only_a / only_b 不计
        weighted_sim = score / max(n_matched_topics, 1) if n_matched_topics else 0.0

    # 平均匹配相似度（仅匹配的 topic）
    avg_match = 0.0
    if n_matched_topics > 0:
        avg_match = sum(tr["topic_sim"] for tr in topic_results if tr["type"] == "matched") / n_matched_topics

    return {
        "ditamap_a": os.path.basename(map_a),
        "ditamap_b": os.path.basename(map_b),
        "n_topics_a": n_topics_a,
        "n_topics_b": n_topics_b,
        "n_matched_topics": n_matched_topics,
        "n_only_a": len(only_a_topics),
        "n_only_b": len(only_b_topics),
        "n_sentences_a": total_sentences_a,
        "n_sentences_b": total_sentences_b,
        "n_matched_pairs": total_matched_pairs,
        "n_exact": total_exact,
        "overall_jaccard": overall_jaccard,
        "weighted_sim": weighted_sim,
        "avg_match": avg_match,
        "stat_full_match": stat_full_match,
        "stat_high": stat_high,
        "stat_partial": stat_partial,
        "stat_low": stat_low,
        "topics": topic_results,
        "threshold": threshold,
    }
