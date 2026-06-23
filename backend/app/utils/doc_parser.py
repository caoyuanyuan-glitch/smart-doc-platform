"""
文档格式解析器
支持：Word (.docx) / PDF / Markdown
"""
import re
from difflib import SequenceMatcher


def parse_docx(filepath):
    """
    解析 Word 文档，提取文本和章节结构
    使用 python-docx 库
    """
    try:
        from docx import Document
    except ImportError:
        return {"paragraphs": [], "tables_text": [], "chapters": [], "full_text": "", "error": "python-docx not installed"}

    doc = Document(filepath)

    paragraphs = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        style_name = para.style.name if para.style else "Normal"
        paragraphs.append({
            "text": text,
            "style": style_name
        })

    # 提取表格文本
    tables_text = []
    for table in doc.tables:
        for row in table.rows:
            row_text = " | ".join(cell.text.strip() for cell in row.cells)
            if row_text.strip():
                tables_text.append(row_text)

    # 提取章节结构
    chapters = _extract_chapters_from_paragraphs(paragraphs)

    full_text = "\n".join(p["text"] for p in paragraphs)
    full_text += "\n" + "\n".join(tables_text)

    return {
        "paragraphs": paragraphs,
        "tables_text": tables_text,
        "chapters": chapters,
        "full_text": full_text,
        "type": "docx"
    }


def parse_pdf(filepath):
    """
    解析 PDF 文档，提取文本和书签结构
    使用 PyMuPDF (fitz)
    """
    try:
        import fitz
    except ImportError:
        return {"pages_text": [], "toc": [], "chapters": [], "full_text": "", "error": "pymupdf not installed"}

    doc = fitz.open(filepath)

    # 提取书签（目录结构）
    toc = doc.get_toc()  # [(level, title, page), ...]

    # 提取每页文本
    pages_text = []
    for page_num in range(doc.page_count):
        page = doc[page_num]
        text = page.get_text()
        pages_text.append(text)

    full_text = "\n".join(pages_text)

    # 从书签构建章节结构，如果无书签则从文本检测标题
    if toc:
        chapters = _extract_chapters_from_toc(toc, pages_text)
    else:
        # PDF 无书签，通过文本模式检测标题
        chapters = detect_headings_from_text(pages_text)

    doc.close()

    return {
        "pages_text": pages_text,
        "toc": toc,
        "chapters": chapters,
        "full_text": full_text,
        "type": "pdf"
    }


def parse_markdown(filepath):
    """
    解析 Markdown 文件，按 # 标题提取章节结构
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return {"chapters": [], "full_text": "", "error": "Failed to read file"}

    lines = content.split('\n')
    chapters = []
    current_chapter = None
    current_section = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # 检测标题
        heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
        if heading_match:
            level = len(heading_match.group(1))
            text = heading_match.group(2)

            if level == 1:
                if current_chapter:
                    if current_section:
                        current_chapter["subsections"].append(current_section)
                    chapters.append(current_chapter)
                current_chapter = {"heading": text, "content": "", "subsections": []}
                current_section = None
            elif level == 2:
                if current_section and current_chapter:
                    current_chapter["subsections"].append(current_section)
                current_section = {"heading": text, "content": ""}
            continue

        # 跳过表格和分隔线
        if '|' in stripped and '---' not in stripped:
            continue
        if stripped.startswith('---') or stripped.startswith('***'):
            continue

        # 正文
        if current_section:
            current_section["content"] += stripped + " "
        elif current_chapter:
            current_chapter["content"] += stripped + " "

    if current_chapter:
        if current_section:
            current_chapter["subsections"].append(current_section)
        chapters.append(current_chapter)

    return {
        "chapters": chapters,
        "full_text": content,
        "type": "md"
    }


def _extract_chapters_from_paragraphs(paragraphs):
    """
    从段落列表中提取章节结构
    基于 Heading 样式识别标题层级
    """
    chapters = []
    current_chapter = None
    current_section = None

    for p in paragraphs:
        style = p["style"]
        text = p["text"]

        if style.startswith("Heading 1") or style.startswith("标题 1"):
            if current_chapter:
                if current_section:
                    current_chapter["subsections"].append(current_section)
                chapters.append(current_chapter)
            current_chapter = {"heading": text, "content": "", "subsections": []}
            current_section = None

        elif style.startswith("Heading 2") or style.startswith("标题 2"):
            if current_section and current_chapter:
                current_chapter["subsections"].append(current_section)
            current_section = {"heading": text, "content": ""}

        else:
            if current_section:
                current_section["content"] += text + " "
            elif current_chapter:
                current_chapter["content"] += text + " "

    if current_chapter:
        if current_section:
            current_chapter["subsections"].append(current_section)
        chapters.append(current_chapter)

    return chapters


def _extract_chapters_from_toc(toc, pages_text):
    """从 PDF 书签提取章节结构"""
    chapters = []
    for item in toc:
        level, title, page_num = item
        # 获取该页的文本作为内容
        content = ""
        if 1 <= page_num <= len(pages_text):
            content = pages_text[page_num - 1][:500]  # 取前500字符

        if level == 1:
            chapters.append({
                "heading": title,
                "content": content,
                "subsections": []
            })
        elif level == 2 and chapters:
            chapters[-1]["subsections"].append({
                "heading": title,
                "content": content
            })

    return chapters


def detect_headings_from_text(pages_text):
    """
    从 PDF 文本中检测标题（当 PDF 没有书签时使用）

    识别规则：
    1. 顶级章节: "Chapter X Title" 或 "第X章 标题"
    2. 二级章节: "X.Y Title"（如 1.1, 1.2, 3.1，支持中文如"1.2 电气安全"）
    3. 三级小节: "X.Y.Z Subtitle"

    排除规则：
    - 目录行（含 "...."/"……"）
    - 单独页码（"1"、"2" 等）和 "Page N"、罗马数字页码
    - 表格项目（数字+单位开头，如 "1.3 ml ..."、"2.2 mL ..."、"220V"）
    - 表格行（含 "Cat. No."、"Quantity"、"型号"、"规格" 等）
    - 常见页眉页脚
    - 重复行（同一行出现多次时只保留第一次）
    """
    import re as re_mod

    # 收集所有行（带全局索引），同时去重
    seen_lines = set()  # 用于去重
    global_lines = []
    for page_idx, page_text in enumerate(pages_text):
        for line in page_text.split('\n'):
            s = line.strip()
            if s and s not in seen_lines:
                seen_lines.add(s)
                global_lines.append(s)

    # 标题模式（支持中英文）
    # 顶级：Chapter X Title（英文）或 第X章 标题（中文）
    chapter_pattern = re_mod.compile(r'^Chapter\s+(\d+)\s+([A-Z\u4e00-\u9fff][A-Za-z\u4e00-\u9fff\s\-]{2,80})$')
    chapter_cn_pattern = re_mod.compile(r'^第([一二三四五六七八九十\d]+)[章节篇]\s+([A-Za-z\u4e00-\u9fff][A-Za-z\u4e00-\u9fff\s\-]{2,80})$')
    # 二级：X.Y Title（支持中文标题，如 "1.2 电气安全"）
    h1_pattern = re_mod.compile(r'^(\d+)\.(\d+)\s+([A-Za-z\u4e00-\u9fff][A-Za-z\u4e00-\u9fff\s\-，、：]{0,80})$')
    # 三级：X.Y.Z Subtitle
    h2_pattern = re_mod.compile(r'^(\d+)\.(\d+)\.(\d+)\s+([A-Za-z\u4e00-\u9fff][A-Za-z0-9\u4e00-\u9fff\s\-\(\)\uff08\uff09]{0,80})$')

    # 表格项目：数字 + 空格 + 单位（ml, mL, μL, L, g, kg 等）
    is_table_item = re_mod.compile(r'^\d+(\.\d+)?\s*(ml|mL|μL|uL|L|g|kg|mg|cm|mm|m|nm|µm|V|W|Hz|A|kW|kV)\b', re_mod.IGNORECASE)
    # 表格行标识（含表格列名，中英文）
    table_row_pattern = re_mod.compile(r'(Cat\.?\s*No\.?|Quantity|Brand|Volume/well|Position\s*$|Tips\s*$|^Consumables\s*$|^Reagents\s*$|^Equipment\s*$|^Specification|Adaptable\s+tube|型号|规格|数量|单位|备注|参数)', re_mod.IGNORECASE)
    # 表格标题行（如 "Table 1-2 ..."、"Figure 3-1 ..."、"表 1-2"、"图 3-1"）
    table_caption_pattern = re_mod.compile(r'^(Table|Figure|表|图)\s*\d+[-\u2013\u2014]\d+', re_mod.IGNORECASE)
    # 页眉页脚（中英文）
    footer_pattern = re_mod.compile(r'^(For Research Use Only\.|MGI Tech Co\.,? Ltd\.|Doc\.?\s*No\.?:?|版权所有|仅供研究使用|技术文档|内部资料)\s*', re_mod.IGNORECASE)
    # 单独页码
    page_num_pattern = re_mod.compile(r'^\d+$|^Page\s*\d+|^第\s*\d+\s*页', re_mod.IGNORECASE)
    # 罗马数字页码
    roman_pattern = re_mod.compile(r'^(I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII)$')

    # 标记哪些行属于表格区（Table/Figure 区域）
    in_table_zone = [False] * len(global_lines)
    i = 0
    while i < len(global_lines):
        line = global_lines[i]
        if table_caption_pattern.match(line):
            # 从这行开始标记为表格区，到下一个标题行或非表格内容行结束
            start = i
            i += 1
            # 找到表格区结束（遇到下一个标题、Table 标题、Chapter 等）
            while i < len(global_lines):
                next_line = global_lines[i]
                # 结束条件：遇到新的标题或长正文
                if (chapter_pattern.match(next_line) or
                    h1_pattern.match(next_line) or
                    h2_pattern.match(next_line) or
                    table_caption_pattern.match(next_line) or
                    (len(next_line) > 60 and not table_row_pattern.search(next_line))):
                    break
                in_table_zone[i] = True
                i += 1
            in_table_zone[start] = True
        else:
            i += 1

    chapters = []
    current_chapter = None
    current_h1 = None  # 当前的 X.Y 章节
    current_section = None  # 当前的 X.Y.Z 小节

    def flush_h1():
        """把当前 H1（X.Y）的所有内容提交到 Chapter 的 subsections"""
        nonlocal current_h1, current_section
        if current_h1 and current_chapter is not None:
            if current_section:
                current_h1["subsections"].append(current_section)
                current_section = None
            current_chapter["subsections"].append(current_h1)
            current_h1 = None

    def flush_chapter():
        """把当前 Chapter 的所有内容提交到 chapters"""
        nonlocal current_chapter, current_h1, current_section
        flush_h1()
        if current_chapter is not None:
            chapters.append(current_chapter)
            current_chapter = None

    for line_idx, line in enumerate(global_lines):
        s = line.strip()
        if not s:
            continue

        # 先检测标题（标题检测优先于表格过滤）
        m_chapter = chapter_pattern.match(s)
        m_chapter_cn = chapter_cn_pattern.match(s)
        m_h1 = h1_pattern.match(s)
        m_h2 = h2_pattern.match(s)

        # 如果是标题，直接处理（不跳过）
        if (m_chapter or m_chapter_cn or m_h1 or m_h2) and len(s) <= 80:
            # 处理标题（见下方）
            pass
        else:
            # 不是标题，检查是否需要跳过
            # 跳过表格区
            if in_table_zone[line_idx]:
                # 把内容加到最近的章节
                if current_section:
                    current_section["content"] += s + " "
                elif current_h1:
                    current_h1["content"] += s + " "
                elif current_chapter:
                    current_chapter["content"] += s + " "
                continue
            # 跳过页眉页脚
            if footer_pattern.match(s):
                continue
            # 跳过页码
            if page_num_pattern.match(s):
                continue
            if roman_pattern.match(s):
                continue
            # 跳过目录行（含省略号）
            if '....' in s or '……' in s:
                continue
            # 跳过表格项目（数字+单位）
            if is_table_item.match(s):
                continue
            # 跳过表格行（含表格列名）- 但标题行已在上方处理，不会被跳过
            if table_row_pattern.search(s):
                continue

        # 额外校验：标题行长度不应过长
        if (m_h1 or m_h2) and len(s) > 80:
            # 作为正文处理
            if current_section:
                current_section["content"] += s + " "
            elif current_h1:
                current_h1["content"] += s + " "
            elif current_chapter:
                current_chapter["content"] += s + " "
            continue

        if m_chapter or m_chapter_cn:
            # 顶级章节（英文 Chapter X 或中文 第X章）
            flush_chapter()
            if m_chapter:
                chapter_num = int(m_chapter.group(1))
            else:
                # 中文数字转换
                cn_num = m_chapter_cn.group(1)
                cn_num_map = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}
                chapter_num = cn_num_map.get(cn_num, int(cn_num) if cn_num.isdigit() else 0)
            current_chapter = {
                "heading": s,
                "content": "",
                "subsections": [],
                "_chapter_num": chapter_num
            }
            current_h1 = None
            current_section = None
        elif m_h2:
            # 三级小节（X.Y.Z） - 应该归到当前 X.Y 下
            if current_section and current_h1:
                current_h1["subsections"].append(current_section)
            elif current_section and current_chapter and not current_h1:
                # 没有 X.Y 时，把 X.Y.Z 直接放到 Chapter 下
                current_chapter["subsections"].append(current_section)
            current_section = {"heading": s, "content": "", "subsections": []}
        elif m_h1:
            # 二级章节（X.Y）- 应该归到对应的 Chapter X 下
            chapter_num = int(m_h1.group(1))
            # 如果当前 chapter 不存在或者编号不匹配，创建一个 Chapter 占位
            if not current_chapter or current_chapter.get("_chapter_num") != chapter_num:
                flush_chapter()
                current_chapter = {
                    "heading": f"Chapter {chapter_num}",
                    "content": "",
                    "subsections": [],
                    "_chapter_num": chapter_num
                }
            else:
                # 同 chapter 下的下一个 H1，先 flush 当前的 H1
                flush_h1()
            current_h1 = {"heading": s, "content": "", "subsections": []}
            current_section = None
        else:
            # 正文内容
            if current_section:
                current_section["content"] += s + " "
            elif current_h1:
                current_h1["content"] += s + " "
            elif current_chapter:
                current_chapter["content"] += s + " "

    # 处理最后一个章节
    flush_chapter()

    return chapters


def align_chapters(chapters_a, chapters_b):
    """
    按标题文本匹配对齐两个文档的章节
    """
    aligned = []
    matched_b = set()

    for ch_a in chapters_a:
        best_match = None
        best_score = 0
        for j, ch_b in enumerate(chapters_b):
            if j in matched_b:
                continue
            score = SequenceMatcher(None, ch_a["heading"], ch_b["heading"]).ratio()
            if score > best_score and score > 0.5:
                best_score = score
                best_match = j

        if best_match is not None:
            aligned.append({
                "heading_a": ch_a["heading"],
                "heading_b": chapters_b[best_match]["heading"],
                "content_a": ch_a["content"],
                "content_b": chapters_b[best_match]["content"],
                "subsections_a": ch_a.get("subsections", []),
                "subsections_b": chapters_b[best_match].get("subsections", []),
                "match_type": "exact" if best_score > 0.9 else "fuzzy",
                "match_score": best_score
            })
            matched_b.add(best_match)
        else:
            aligned.append({
                "heading_a": ch_a["heading"],
                "heading_b": None,
                "content_a": ch_a["content"],
                "content_b": None,
                "match_type": "orphan_a",
                "match_score": 0
            })

    for j, ch_b in enumerate(chapters_b):
        if j not in matched_b:
            aligned.append({
                "heading_a": None,
                "heading_b": ch_b["heading"],
                "content_a": None,
                "content_b": ch_b["content"],
                "match_type": "orphan_b",
                "match_score": 0
            })

    return aligned


def _split_sentences(text):
    """
    智能句子切分：
    1. 按句号、问号、感叹号、分号切分（中英文）
    2. 过滤太短（< 5 字符）的片段（页码、噪声）
    3. 保留列表项和正文
    """
    if not text:
        return []

    # 预处理：把 `\n` 替换为空格（保留同一段内容），但保留列表项结构
    text = text.replace('\n', ' ').strip()
    # 合并多余空格
    text = re.sub(r'\s+', ' ', text)

    # 按句末标点切分（中英文）
    # 注意：不切分 "1)" "2)" "a)" 等列表项标号，也不切分 "1.3" "X.Y" 等编号
    parts = re.split(r'(?<=[。！？?])\s*|(?<=[;；])\s*|(?<=[.!?])\s+(?=[A-Z])', text)

    sentences = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        # 过滤太短的片段（页码、单字符等）
        if len(p) < 5:
            continue
        # 过滤纯数字/罗马数字
        if re.match(r'^[\dIVXLCDM]+$', p, re.IGNORECASE):
            continue
        # 过滤纯标点
        if re.match(r'^[\s\W]+$', p):
            continue
        sentences.append(p)

    return sentences


def fuzzy_jaccard(sentences_a, sentences_b, threshold=0.70):
    """
    句子级模糊 Jaccard 对比
    返回匹配对数和 Jaccard 值
    """
    if not sentences_a or not sentences_b:
        return {"jaccard": 0.0, "matched_pairs": [], "only_a": sentences_a, "only_b": sentences_b}

    matched_a = set()
    matched_b = set()
    pairs = []

    # 精确匹配
    hash_b = {}
    for j, s in enumerate(sentences_b):
        h = hash(s.lower())
        hash_b.setdefault(h, []).append(j)

    for i, s in enumerate(sentences_a):
        h = hash(s.lower())
        if h in hash_b:
            for j in hash_b[h]:
                if j not in matched_b:
                    matched_a.add(i)
                    matched_b.add(j)
                    pairs.append({"type": "exact", "a": s, "b": sentences_b[j], "score": 1.0})
                    break

    # 模糊匹配
    candidates = []
    for i in range(len(sentences_a)):
        if i in matched_a:
            continue
        for j in range(len(sentences_b)):
            if j in matched_b:
                continue
            score = SequenceMatcher(None, sentences_a[i].lower(), sentences_b[j].lower()).ratio()
            if score >= threshold:
                candidates.append((i, j, score))
    candidates.sort(key=lambda x: -x[2])

    for i, j, score in candidates:
        if i in matched_a or j in matched_b:
            continue
        matched_a.add(i)
        matched_b.add(j)
        pairs.append({"type": "fuzzy", "a": sentences_a[i], "b": sentences_b[j], "score": score})

    only_a = [sentences_a[i] for i in range(len(sentences_a)) if i not in matched_a]
    only_b = [sentences_b[j] for j in range(len(sentences_b)) if j not in matched_b]

    # 计算 Jaccard（改进版）
    # Jaccard = 匹配数 / (A总数 + B总数 - 匹配数)
    # 但为了更直观，也计算 similarity = 匹配数 / max(A总数, B总数)
    union = len(sentences_a) + len(sentences_b) - len(pairs)
    jaccard = len(pairs) / union if union > 0 else 0.0

    # 额外计算：匹配覆盖率（更直观的相似度）
    coverage = len(pairs) / max(len(sentences_a), len(sentences_b), 1)

    # 计算平均匹配分数（用于判断是否全部 exact）
    avg_score = sum(p.get("score", 1.0) for p in pairs) / len(pairs) if pairs else 0.0

    return {
        "jaccard": jaccard,
        "coverage": coverage,
        "avg_score": avg_score,
        "matched_pairs": pairs,
        "only_a": only_a,
        "only_b": only_b,
        "n_sentences_a": len(sentences_a),
        "n_sentences_b": len(sentences_b),
        "n_matched": len(pairs)
    }


def compare_documents_by_format(file_a_path, file_b_path):
    """
    自动识别格式并对比两个文档

    支持：.docx / .doc / .pdf / .md / .txt
    """
    ext_a = file_a_path.split('.')[-1].lower().replace(' ', '')
    ext_b = file_b_path.split('.')[-1].lower().replace(' ', '')

    # 选择解析器
    parsed_a = None
    parsed_b = None

    if ext_a in ('docx', 'doc'):
        parsed_a = parse_docx(file_a_path)
    elif ext_a == 'pdf':
        parsed_a = parse_pdf(file_a_path)
    elif ext_a in ('md', 'markdown'):
        parsed_a = parse_markdown(file_a_path)
    else:
        # 尝试纯文本
        try:
            with open(file_a_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            parsed_a = {"chapters": [{"heading": "全文", "content": content, "subsections": []}], "full_text": content, "type": "text"}
        except Exception:
            parsed_a = {"chapters": [], "full_text": "", "type": "unknown"}

    if ext_b in ('docx', 'doc'):
        parsed_b = parse_docx(file_b_path)
    elif ext_b == 'pdf':
        parsed_b = parse_pdf(file_b_path)
    elif ext_b in ('md', 'markdown'):
        parsed_b = parse_markdown(file_b_path)
    else:
        try:
            with open(file_b_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            parsed_b = {"chapters": [{"heading": "全文", "content": content, "subsections": []}], "full_text": content, "type": "text"}
        except Exception:
            parsed_b = {"chapters": [], "full_text": "", "type": "unknown"}

    # 章节对齐
    chapters_a = parsed_a.get("chapters", [])
    chapters_b = parsed_b.get("chapters", [])
    aligned = align_chapters(chapters_a, chapters_b)

    # 句子级对比
    results = []
    full_sim = 0.0
    n_full = 0
    n_high = 0
    n_partial = 0
    n_low = 0
    n_only_a = 0
    n_only_b = 0

    for item in aligned:
        if item["match_type"] == "orphan_a":
            # 合并所有子章节内容（不包含 heading）
            full_a = item.get("content_a") or ""
            for sub in item.get("subsections_a", []):
                full_a += " " + sub.get("content", "")
            results.append({
                "heading": item["heading_a"],
                "content_a": full_a,
                "content_b": "",
                "status": "仅在A中",
                "similarity": 0,
                "diffs": []
            })
            n_only_a += 1
        elif item["match_type"] == "orphan_b":
            full_b = item.get("content_b") or ""
            for sub in item.get("subsections_b", []):
                full_b += " " + sub.get("content", "")
            results.append({
                "heading": item["heading_b"],
                "content_a": "",
                "content_b": full_b,
                "status": "仅在B中",
                "similarity": 0,
                "diffs": []
            })
            n_only_b += 1
        else:
            # 合并所有子章节内容（不重复 heading）
            full_a = item.get("content_a") or ""
            full_b = item.get("content_b") or ""
            for sub in item.get("subsections_a", []):
                full_a += " " + sub.get("content", "")
            for sub in item.get("subsections_b", []):
                full_b += " " + sub.get("content", "")

            # 使用智能句子切分
            sentences_a = _split_sentences(full_a)
            sentences_b = _split_sentences(full_b)
            result = fuzzy_jaccard(sentences_a, sentences_b, threshold=0.70)

            # 使用 coverage 作为主要相似度指标（更直观）
            sim = result["coverage"]
            avg_score = result.get("avg_score", 1.0)
            n_matched = result.get("n_matched", 0)

            # 状态判定：结合 coverage 和 avg_score
            # 如果全部 exact 匹配（avg_score >= 0.99）且覆盖率 >= 95%，视为完全一致
            if avg_score >= 0.99 and sim >= 0.95:
                status = "完全一致"
                n_full += 1
            elif avg_score >= 0.95 and sim >= 0.90:
                status = "高度相似"
                n_high += 1
            elif sim >= 0.70:
                status = "部分相似"
                n_partial += 1
            else:
                status = "差异较大"
                n_low += 1

            results.append({
                "heading": item["heading_a"],
                "content_a": full_a,
                "content_b": full_b,
                "status": status,
                "similarity": sim,
                "avg_score": avg_score,
                "n_matched": n_matched,
                "diffs": result["matched_pairs"],
                "only_a": result["only_a"],
                "only_b": result["only_b"]
            })

    # 计算整体指标
    n_matched = len([r for r in results if r["status"] not in ("仅在A中", "仅在B中")])
    total = n_matched + n_only_a + n_only_b
    overall_sim = sum(r["similarity"] for r in results if r["status"] not in ("仅在A中", "仅在B中")) / max(n_matched, 1)

    return {
        "results": results,
        "stats": {
            "n_full": n_full,
            "n_high": n_high,
            "n_partial": n_partial,
            "n_low": n_low,
            "n_only_a": n_only_a,
            "n_only_b": n_only_b,
            "n_matched": n_matched,
            "overall_sim": overall_sim,
            "total": total
        },
        "type_a": parsed_a.get("type", "unknown"),
        "type_b": parsed_b.get("type", "unknown"),
        "aligned_chapters": aligned
    }
