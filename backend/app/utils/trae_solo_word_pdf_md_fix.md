# Trae Solo 修复指令 — 新增 Word/PDF/MD 格式对比功能

## 一、问题描述

当前平台仅支持 DITA 格式对比。Word 对比功能**完全不可用**——它把 .docx 的 ZIP 二进制内容直接拿来对比，显示的是乱码。同时还需要支持 PDF 和 Markdown 格式。

---

## 二、格式解析器

### 2.1 Word 解析器（用 python-docx）

```python
from docx import Document
import re

def parse_docx(filepath):
    """
    正确解析 Word 文档，提取文本和章节结构
    
    使用 python-docx 库，不能直接读取二进制
    """
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
    chapters = extract_chapters(paragraphs)
    
    full_text = "\n".join(p["text"] for p in paragraphs)
    full_text += "\n" + "\n".join(tables_text)
    
    return {
        "paragraphs": paragraphs,
        "tables_text": tables_text,
        "chapters": chapters,
        "full_text": full_text
    }
```

### 2.2 PDF 解析器（用 PyMuPDF）

```python
import fitz  # PyMuPDF

def parse_pdf(filepath):
    """
    解析 PDF 文档，提取文本和书签结构
    """
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
    
    # 从书签构建章节结构
    chapters = []
    if toc:
        chapters = extract_chapters_from_toc(toc, pages_text)
    
    doc.close()
    
    return {
        "pages_text": pages_text,
        "toc": toc,
        "chapters": chapters,
        "full_text": full_text
    }


def extract_chapters_from_toc(toc, pages_text):
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
```

### 2.3 Markdown 解析器

```python
def parse_markdown(filepath):
    """
    解析 Markdown 文件，按 # 标题提取章节结构
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
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
        "full_text": content
    }
```

### 2.4 章节结构提取（通用）

```python
def extract_chapters(paragraphs):
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
        
        if style.startswith("Heading 1"):
            if current_chapter:
                if current_section:
                    current_chapter["subsections"].append(current_section)
                chapters.append(current_chapter)
            current_chapter = {"heading": text, "content": "", "subsections": []}
            current_section = None
        
        elif style.startswith("Heading 2"):
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
```

---

## 三、章节对齐

```python
from difflib import SequenceMatcher

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
                "match_type": "exact" if best_score > 0.9 else "fuzzy"
            })
            matched_b.add(best_match)
        else:
            aligned.append({
                "heading_a": ch_a["heading"],
                "heading_b": None,
                "content_a": ch_a["content"],
                "content_b": None,
                "match_type": "orphan_a"
            })
    
    for j, ch_b in enumerate(chapters_b):
        if j not in matched_b:
            aligned.append({
                "heading_a": None,
                "heading_b": ch_b["heading"],
                "content_a": None,
                "content_b": ch_b["content"],
                "match_type": "orphan_b"
            })
    
    return aligned
```

---

## 四、入口函数

```python
def compare_files(file_a_path, file_b_path):
    """
    自动识别格式并对比两个文件
    
    支持：.docx / .doc / .pdf / .md / .dita / .ditamap
    """
    ext_a = file_a_path.split('.')[-1].lower()
    ext_b = file_b_path.split('.')[-1].lower()
    
    parsers = {
        'docx': parse_docx,
        'doc': parse_docx,
        'pdf': parse_pdf,
        'md': parse_markdown,
        'dita': parse_dita,      # 已有
        'ditamap': parse_dita,   # 已有
    }
    
    parsed_a = parsers[ext_a](file_a_path)
    parsed_b = parsers[ext_b](file_b_path)
    
    # 章节对齐
    aligned = align_chapters(
        parsed_a.get("chapters", []),
        parsed_b.get("chapters", [])
    )
    
    # 句子级对比（复用已有算法）
    results = []
    for item in aligned:
        if item["match_type"] == "orphan_a":
            results.append({"heading": item["heading_a"], "status": "仅在A中", "similarity": 0})
        elif item["match_type"] == "orphan_b":
            results.append({"heading": item["heading_b"], "status": "仅在B中", "similarity": 0})
        else:
            # 对比正文
            sentences_a = [s.strip() for s in re.split(r'[。！？.!?]', item["content_a"]) if s.strip()]
            sentences_b = [s.strip() for s in re.split(r'[。！？.!?]', item["content_b"]) if s.strip()]
            result = fuzzy_jaccard(sentences_a, sentences_b, threshold=0.70)
            results.append({
                "heading": item["heading_a"],
                "status": "匹配",
                "similarity": result["jaccard"],
                "diffs": result["matched_pairs"]
            })
    
    # 生成 HTML 报告（复用 DITA 报告模板）
    report_html = generate_report_html(parsed_a, parsed_b, results)
    return report_html
```

---

## 五、对比报告要求

**必须使用与 DITA 对比报告完全相同的 HTML 模板**，包括：

### 报告头部
- 标题统一为"DITA 数据包对比报告"
- 生成时间、文件A↔文件B
- 文件格式标注（如"文件A: Word / 文件B: Word"）

### 汇总卡片（8个）
- 整体一致性 · 模糊 Jaccard
- 匹配平均
- 匹配章节数
- 完全一致
- 高度相似
- 部分相似
- 差异较大
- 仅在 A / 仅在 B

### 差异点汇总表
- 序号、一级章节、小节、差异说明、一致性
- 差异说明格式：⚠️ 安全警告变更 / 措辞调整 / 参数变更 / 操作流程变更 / 内容变更
- 一致性格式：100% / 95%~99% / 85%~95% / 70%~85% / 50%~70% / <50%

### 差异详情
- 点击展开/收起
- A/B 原文对比，增删改高亮（del/ins 标签）
- 严重程度标记：🔴 🟠 🟢 🔵

### 结论与建议
- 判定：🟥 强制人工复核（<60%，不可互换）
- 复核重点：差异较大章节、仅在A/仅在B的内容
- 复核建议：优先复核<70%章节、安全章节重点确认、参数变更核对

### CSS 样式
- 必须使用 DITA 报告现有的 CSS，不能另写一套

---

## 六、修改清单

| 优先级 | 修改内容 | 说明 |
|:----:|:--------|:------|
| 🔴 P0 | **Word 解析器** | 用 python-docx 解析，不能读二进制 |
| 🔴 P0 | **PDF 解析器** | 用 PyMuPDF 解析，提取书签和文本 |
| 🔴 P0 | **Markdown 解析器** | 按 # 标题提取章节结构 |
| 🔴 P0 | **章节对齐** | 按标题文本匹配对齐 |
| 🟡 P1 | **句子级对比** | 复用已有对比算法 |
| 🟡 P1 | **HTML 报告** | 复用 DITA 报告模板，外观结构完全一致 |
