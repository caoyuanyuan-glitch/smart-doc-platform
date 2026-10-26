import re
import os
from difflib import SequenceMatcher


def normalize_param_name(name):
    name = name.strip()
    name = re.sub(r'[\s\u3000]+', ' ', name)
    name = re.sub(r'[（(][^)）]*[)）]$', '', name)
    return name


def parse_value(raw):
    raw = raw.strip()
    if not raw:
        return raw
    raw = re.sub(r'\s*[±＋]\s*', '±', raw)
    raw = re.sub(r'\s*[×xX]\s*', '×', raw)
    raw = re.sub(r'[−‐‑‒–—―]', '-', raw)
    return raw


def _strip_markdown_markup(text):
    text = str(text or "").strip()
    text = re.sub(r'^>\s*', '', text)
    text = re.sub(r'^(?:[-*+]\s+)', '', text)
    text = re.sub(r'^#{1,6}\s*', '', text)
    text = re.sub(r'^\d+[\.、\)]\s*', '', text)
    text = re.sub(r'\*\*([^*]+?)\*\*', r'\1', text)
    text = re.sub(r'__([^_]+?)__', r'\1', text)
    text = text.replace('**', '')
    text = text.replace('`', '')
    return text.strip()


def _split_markdown_table_rows(text):
    rows = []
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line.startswith('|') or line.count('|') < 2:
            continue
        if re.fullmatch(r'\|[\s\-:\|]+\|?', line):
            continue
        cells = [
            _strip_markdown_markup(cell)
            for cell in line.strip('|').split('|')
        ]
        cells = [cell for cell in cells if cell]
        if len(cells) >= 2:
            rows.append(cells)
    return rows


def _extract_list_section_params(text):
    params = []
    lines = str(text or "").splitlines()
    i = 0
    while i < len(lines):
        heading = _strip_markdown_markup(lines[i])
        if heading not in {"适用样本类型", "适用样本"}:
            i += 1
            continue

        values = []
        j = i + 1
        while j < len(lines):
            raw_line = lines[j].rstrip()
            stripped = raw_line.strip()
            if not stripped:
                if values:
                    break
                j += 1
                continue
            if re.match(r'^#{1,6}\s*', stripped):
                break
            if re.match(r'^\*\*[^*]+[：:]\*\*', stripped):
                break

            item = _strip_markdown_markup(stripped)
            if re.match(r'^(?:[-*+]\s+)', stripped):
                if item:
                    values.append(item)
                j += 1
                continue
            if values:
                break
            j += 1

        if values:
            params.append({
                "name": heading,
                "value": "、".join(values),
                "source": "text_section",
            })
        i = j
    return params


_COLON_PATTERN = re.compile(
    r'^\s*'
    r'(?:[\d]+[\.\、\)）]\s*)?'          # 可选编号前缀
    r'([\u4e00-\u9fff\w][\u4e00-\u9fff\w \t/\-\.·\u2103\u2109\u00b0\u03a9\u03bc\u00b5\u2126]{1,60}?)'
    r'\s*[：:]\s*'
    r'(.+)$'
)

_EQUALS_PATTERN = re.compile(
    r'^\s*'
    r'(?:[\d]+[\.\、\)）]\s*)?'
    r'([\u4e00-\u9fff\w][\u4e00-\u9fff\w \t/\-\.·\u2103\u2109\u00b0\u03a9\u03bc\u00b5\u2126]{1,60}?)'
    r'\s*[=＝]\s*'
    r'(.+)$'
)

_TABLE_LIKE_PATTERN = re.compile(
    r'^\s*'
    r'(?:[\d]+[\.\、\)）]\s*)?'
    r'([\u4e00-\u9fff\w][\u4e00-\u9fff\w \t/\-\.·\u2103\u2109\u00b0\u03a9\u03bc\u00b5\u2126]{1,50}?)'
    r'(?:\s{2,}|\t)\s*'
    r'(.+)$'
)

# OCR 特殊模式：中文参数名直接连接字母数字值（如 "额定功率300W"、"产品型号HTS-100"）
_OCR_CONCAT_PATTERN = re.compile(
    r'^\s*'
    r'([\u4e00-\u9fff][\u4e00-\u9fff\s]{1,40}?)'
    r'([\dA-Za-z\u2103\u2109\u00b0\u03a9\u03bc\u00b5\u2126\u00b1\u2264\u2265][^。,，；;]{0,60})$'
)

_NUMERIC_PATTERN = re.compile(r'[-+]?\d+\.?\d*')
_UNIT_PATTERN = re.compile(
    r'(?:mm|cm|m|km|mm\^?[23]|cm\^?[23]|m\^?[23]|'
    r'kg|g|mg|t|ton|'
    r's|ms|min|h|hour|sec|'
    r'V|kV|mV|A|mA|W|kW|MW|Hz|kHz|MHz|GHz|'
    r'℃|°C|°F|℉|℃|℉|K|'
    r'Ω|kΩ|MΩ|μF|pF|nF|'
    r'L|mL|m\^3|L/min|'
    r'Pa|kPa|MPa|bar|psi|'
    r'N|kN|Nm|rpm|RPM|'
    r'%|％|ppm|ppb|'
    r'dB|dBm|dBi|'
    r'bps|kbps|Mbps|Gbps|'
    r'px|pt|em|rem|'
    r'[\u2103\u2109\u00b0\u03a9\u03bc\u00b5\u2126])'
)


def _is_param_like(text):
    text = text.strip()
    if len(text) > 80:
        return False
    if re.match(r'^[\d\.\-\+\s,;，；·]+$', text):
        return False
    if not re.search(r'[\u4e00-\u9fff\w]', text):
        return False
    if re.match(r'^(第|Chapter|Section|Table|图|Figure|注|Note|参见|参考|详见|如|例如|其中|式中)\s', text):
        return False
    if re.match(r'^(目\s*录|目录|前言|引言|概述|简介|总结|参考文献|附录|致谢)', text):
        return False
    if re.match(r'^\d+\.?\d*\s+', text):
        return False
    # 排除长句子（含中文标点的多词文本）
    if len(text) > 20 and re.search(r'[，。、；,]', text):
        return False
    # 排除含中文句号的文本（OCR 多行拼接）
    if re.search(r'[。]', text):
        return False
    # 排除以动词/介词开头的非参数文本
    if re.match(r'^.*(将|按|如|根据|检查|重新|联系|停止)', text) and len(text) > 10:
        return False
    # 排除章节词混杂（如"常见问题处理设备无法开机"）
    if re.match(r'^(常见问题|安全注意|清洁与维护|产品介绍|产品组成|主要技术|操作说明|使用环境|储存与运输)', text):
        return False
    return True


def _is_value_like(text):
    text = text.strip()
    if not text:
        return False
    if text in _HEADER_VALUES:
        return False
    if len(text) > 200:
        return False
    if re.search(r'[。；，；\n]{2,}', text):
        return False
    words = text.split()
    if len(words) > 20:
        return False
    # 排除纯数字编号（如 "6.2"、"6.4"、"3."）
    if re.match(r'^\d+\.?\d*\s*(开机|设置|停止|启动|清洁|安全|操作|产品|使用|储存)?$', text):
        return False
    has_digit = bool(_NUMERIC_PATTERN.search(text))
    has_unit = bool(_UNIT_PATTERN.search(text.casefold()))
    is_short = len(text) <= 30
    if re.search(r'[@]|https?://|\bwww\.', text, re.IGNORECASE):
        return True
    # 值不包含数字且不包含单位时，必须是短文本
    if not has_digit and not has_unit:
        if len(text) > 40:
            return False
        if re.search(r'[。；]', text):
            return False
    if has_digit or has_unit:
        return True
    if is_short and not re.search(r'[。，、；]', text):
        return True
    return False


def extract_params_from_text(text):
    params = []
    seen = set()

    table_rows = _split_markdown_table_rows(text)
    if table_rows:
        for p in extract_params_from_table_rows(table_rows):
            key = p["name"].casefold()
            if key in seen:
                continue
            seen.add(key)
            params.append(p)

    for p in _extract_list_section_params(text):
        key = p["name"].casefold()
        if key in seen:
            continue
        seen.add(key)
        params.append(p)

    lines = text.split('\n')
    for line in lines:
        line = _strip_markdown_markup(line)
        if not line:
            continue

        source = "text"

        m = _COLON_PATTERN.match(line)
        if not m:
            m = _EQUALS_PATTERN.match(line)
        if not m:
            m = _TABLE_LIKE_PATTERN.match(line)
        if not m:
            m = _OCR_CONCAT_PATTERN.match(line)
            if m:
                source = "ocr_concat"
        if not m:
            continue

        name = normalize_param_name(_strip_markdown_markup(m.group(1)))
        value = parse_value(m.group(2).strip())
        if not name or not value:
            continue
        if not _is_param_like(name):
            continue
        if not _is_value_like(value):
            continue

        # OCR 拼接模式额外验证：值必须含数字或单位
        if source == "ocr_concat":
            if not (_NUMERIC_PATTERN.search(value) or _UNIT_PATTERN.search(value.casefold())):
                continue

        norm_name = name.casefold()
        if norm_name in seen:
            continue
        seen.add(norm_name)
        params.append({"name": name, "value": value, "source": source})
    return params


def _is_header_row(cells):
    """判断一行是否为表头（列标题行）

    表头特征：单元格全是短中文词，不含数字/单位，通常为"参数名称"、"规格"、"数值"等
    """
    if not cells:
        return False
    header_keywords = [
        '参数', '名称', '项目', '指标', '规格', '型号', '数值', '值', '单位',
        '要求', '标准', '范围', '条件', '说明', '备注', '描述', '类型', '序号',
        '编号', '代码', 'name', 'value', 'unit', 'spec', 'param', 'item',
    ]
    numeric_count = 0
    for cell in cells:
        cell_text = cell.strip()
        if not cell_text:
            continue
        if _NUMERIC_PATTERN.search(cell_text) or _UNIT_PATTERN.search(cell_text.casefold()):
            numeric_count += 1
        for kw in header_keywords:
            if kw in cell_text:
                return True
    if numeric_count == 0 and len(cells) >= 2:
        return True
    return False


def _detect_header_row_idx(rows, max_check=5):
    """自动检测表头行索引，返回第一个疑似表头的行号"""
    for idx in range(min(len(rows), max_check)):
        cells = [c.strip() for c in rows[idx] if c.strip()]
        if _is_header_row(cells):
            return idx
    return -1


def extract_params_from_table_rows(rows, header_row_idx=0):
    params = []
    seen = set()

    if not rows or len(rows) < 1:
        return params

    skip_idx = max(header_row_idx, _detect_header_row_idx(rows))

    for row_idx, row in enumerate(rows):
        if row_idx == skip_idx:
            continue
        cells = [c.strip() for c in row if c.strip()]
        if len(cells) < 2:
            continue

        for i in range(len(cells) - 1):
            name = _strip_markdown_markup(cells[i])
            value = _strip_markdown_markup(cells[i + 1])

            if not name or not value:
                continue
            if not _is_param_like(name):
                name2 = cells[i + 1] if i + 2 < len(cells) else ""
                if not name2:
                    continue
                continue

            name = normalize_param_name(name)
            value = parse_value(value)

            norm_name = name.casefold()
            if norm_name in seen:
                continue

            if not _is_value_like(value):
                continue

            seen.add(norm_name)
            params.append({"name": name, "value": value, "source": f"table_row_{row_idx}"})

    return params


def extract_params_from_docx(filepath):
    try:
        from docx import Document
    except ImportError:
        return []

    try:
        doc = Document(filepath)
    except Exception:
        return []

    text_parts = []
    table_rows = []

    for para in doc.paragraphs:
        t = para.text.strip()
        if t:
            text_parts.append(t)

    for table in doc.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            if any(cells):
                table_rows.append(cells)

    full_text = "\n".join(text_parts)
    text_params = extract_params_from_text(full_text)
    table_params = extract_params_from_table_rows(table_rows)

    merged = {}
    for p in text_params:
        merged[p["name"].casefold()] = p
    for p in table_params:
        key = p["name"].casefold()
        if key not in merged:
            merged[key] = p

    result = list(merged.values())
    result.sort(key=lambda x: x["name"])
    return result


def extract_params_from_pdf(filepath):
    text_parts = []
    table_rows = []

    # 主提取器：PyMuPDF (fitz) 对 CJK 支持最好
    fitz_text = ""
    try:
        import fitz
        doc = fitz.open(filepath)
        print(f"[param_compare] PyMuPDF: PDF has {len(doc)} pages")
        for i, page in enumerate(doc):
            t = page.get_text("text")
            if t and t.strip():
                text_parts.append(t)
                print(f"[param_compare] PyMuPDF Page {i+1} text length: {len(t)}")
            else:
                t2 = page.get_text("blocks")
                if t2:
                    block_texts = []
                    for b in t2:
                        if len(b) >= 5 and b[4].strip():
                            block_texts.append(b[4].strip())
                    if block_texts:
                        combined = "\n".join(block_texts)
                        text_parts.append(combined)
                        print(f"[param_compare] PyMuPDF Page {i+1} blocks text length: {len(combined)}")
        doc.close()
        fitz_text = "\n".join(text_parts)
        print(f"[param_compare] PyMuPDF total text length: {len(fitz_text)}")
    except ImportError:
        print("[param_compare] PyMuPDF (fitz) not available")
    except Exception as e:
        print(f"[param_compare] PyMuPDF error: {e}")

    # 如果 PyMuPDF 提取到了文本，用它
    if fitz_text.strip():
        text_params = extract_params_from_text(fitz_text)
        multiline_params = _extract_params_multiline(fitz_text)
        print(f"[param_compare] text_params: {len(text_params)}, multiline_params: {len(multiline_params)}")
    else:
        text_params = []
        multiline_params = []

    # 始终尝试用 pdfplumber 提取文本和表格（补充 PyMuPDF 可能遗漏的表格数据）
    try:
        import pdfplumber
        with pdfplumber.open(filepath) as pdf:
            print(f"[param_compare] pdfplumber supplement: PDF has {len(pdf.pages)} pages")
            for i, page in enumerate(pdf.pages):
                tables = page.extract_tables()
                if tables:
                    print(f"[param_compare] pdfplumber Page {i+1} has {len(tables)} tables")
                for tbl in tables:
                    for row in tbl:
                        if row and any(c for c in row if c):
                            table_rows.append([(c or "").strip() for c in row])
                if not fitz_text.strip():
                    t = page.extract_text()
                    if t and t.strip():
                        text_parts.append(t)
                        print(f"[param_compare] pdfplumber Page {i+1} text length: {len(t)}")
        if not fitz_text.strip():
            full_text = "\n".join(text_parts)
            print(f"[param_compare] pdfplumber total text length: {len(full_text)}")
            if full_text.strip():
                text_params = extract_params_from_text(full_text)
                multiline_params = _extract_params_multiline(full_text)
    except ImportError:
        print("[param_compare] pdfplumber not available for supplement")
    except Exception as e:
        print(f"[param_compare] pdfplumber supplement error: {e}")

    # 回退到 pypdf
    if not fitz_text.strip() and not text_params and not multiline_params:
        try:
            from pypdf import PdfReader
            reader = PdfReader(filepath)
            text_parts2 = []
            print(f"[param_compare] pypdf: PDF has {len(reader.pages)} pages")
            for page in reader.pages:
                t = page.extract_text()
                if t and t.strip():
                    text_parts2.append(t)
            full_text = "\n".join(text_parts2)
            print(f"[param_compare] pypdf total text length: {len(full_text)}")
            text_params = extract_params_from_text(full_text)
            multiline_params = _extract_params_multiline(full_text)
        except ImportError:
            print("[param_compare] pypdf not available")
        except Exception as e:
            print(f"[param_compare] pypdf error: {e}")

    # OCR 回退：扫描件/图片型PDF（无文本层时自动触发）
    if not fitz_text.strip() and not text_params and not multiline_params:
        ocr_text = _ocr_pdf_pages(filepath)
        if ocr_text.strip():
            print(f"[param_compare] OCR text length: {len(ocr_text)}")
            text_params = extract_params_from_text(ocr_text)
            multiline_params = _extract_params_multiline(ocr_text)

    # 提取表格参数
    table_params = extract_params_from_table_rows(table_rows)
    print(f"[param_compare] table_params: {len(table_params)}")

    # 合并：单行 > 多行 > 表格，同名优先保留先出现的
    merged = {}
    for p in text_params:
        merged[p["name"].casefold()] = p
    for p in multiline_params:
        key = p["name"].casefold()
        if key not in merged:
            merged[key] = p
    for p in table_params:
        key = p["name"].casefold()
        if key not in merged:
            merged[key] = p

    result = list(merged.values())
    result.sort(key=lambda x: x["name"])
    print(f"[param_compare] PDF total merged params: {len(result)}")
    return result


def _ocr_pdf_pages(filepath):
    """对扫描件/图片型 PDF 进行 OCR 识别，返回提取的文本"""
    text_parts = []
    try:
        import fitz
        import io
        from PIL import Image, ImageFilter, ImageEnhance

        doc = fitz.open(filepath)
        zoom = 3.0
        mat = fitz.Matrix(zoom, zoom)

        for i, page in enumerate(doc):
            pix = page.get_pixmap(matrix=mat)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            img = img.convert('L')
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.5)
            img = img.filter(ImageFilter.SHARPEN)
            page_text = _ocr_image(img)
            if page_text and page_text.strip():
                text_parts.append(page_text)
                print(f"[param_compare] OCR Page {i+1}: {len(page_text)} chars")

        doc.close()
    except ImportError as e:
        print(f"[param_compare] OCR: required library not available - {e}")
    except Exception as e:
        print(f"[param_compare] OCR error: {e}")

    return "\n".join(text_parts)


def _ocr_image(pil_image):
    """对单张 PIL Image 进行 OCR (tesserocr > pytesseract)，并对结果进行清洗"""
    import os

    _TESSDATA_CANDIDATES = [
        '/usr/share/tesseract-ocr/5/tessdata',
        '/usr/share/tesseract-ocr/4.00/tessdata',
        '/usr/share/tessdata',
        os.environ.get('TESSDATA_PREFIX', ''),
    ]

    # 尝试 tesserocr（直接 C API，速度快）
    try:
        import tesserocr
        tessdata_path = None
        for candidate in _TESSDATA_CANDIDATES:
            if candidate and os.path.isdir(candidate):
                tessdata_path = candidate
                break
        api = tesserocr.PyTessBaseAPI(path=tessdata_path, lang='chi_sim+eng')
        api.SetImage(pil_image)
        text = api.GetUTF8Text()
        api.End()
        if text and text.strip():
            print(f"[param_compare] tesserocr OCR success: {len(text)} chars")
            return _clean_ocr_text(text)
        else:
            print("[param_compare] tesserocr OCR returned empty text")
    except ImportError:
        print("[param_compare] tesserocr not available, trying pytesseract")
    except Exception as e:
        print(f"[param_compare] tesserocr OCR error: {e}, trying pytesseract")

    # 回退到 pytesseract（命令行 wrapper，需安装 tesseract-ocr）
    try:
        import pytesseract
        for candidate in _TESSDATA_CANDIDATES:
            if candidate and os.path.isdir(candidate):
                os.environ['TESSDATA_PREFIX'] = candidate
                break
        text = pytesseract.image_to_string(pil_image, lang='chi_sim+eng')
        if text and text.strip():
            print(f"[param_compare] pytesseract OCR success: {len(text)} chars")
            return _clean_ocr_text(text)
        else:
            print("[param_compare] pytesseract OCR returned empty text")
    except ImportError:
        print("[param_compare] pytesseract not available for OCR")
    except Exception as e:
        print(f"[param_compare] pytesseract OCR error: {e}")

    return ""


def _clean_ocr_text(text):
    """清理 OCR 文本：去除中文间多余空格、修复常见 OCR 错误"""
    import re
    # 去除中文（含中日韩）字符之间的空格（迭代清理，直到无变化）
    while True:
        cleaned = re.sub(
            r'([\u4e00-\u9fff\u3400-\u4dbf])\s+([\u4e00-\u9fff\u3400-\u4dbf])',
            r'\1\2', text
        )
        if cleaned == text:
            break
        text = cleaned
    # 去除中文与数字/单位之间的多余空格
    text = re.sub(
        r'([\u4e00-\u9fff])\s+(\d)',
        r'\1\2', text
    )
    text = re.sub(
        r'(\d)\s+([\u4e00-\u9fff])',
        r'\1\2', text
    )
    # 去除中文与字母/单位之间的多余空格
    text = re.sub(
        r'([\u4e00-\u9fff])\s+([a-zA-Z])',
        r'\1\2', text
    )
    text = re.sub(
        r'([a-zA-Z])\s+([\u4e00-\u9fff])',
        r'\1\2', text
    )

    # 修复字母/单位间多余空格（如 "HTS- 100" → "HTS-100"）
    text = re.sub(r'([A-Z]{2,})\s+-', r'\1-', text)
    text = re.sub(r'-\s+(\d)', r'-\1', text)

    # 常见 OCR 数字/符号错误修复
    text = re.sub(r'\b8096\b', '80%', text)
    text = re.sub(r'\b2096\b', '20%', text)
    text = re.sub(r'\b109%\b', '10%', text)
    text = re.sub(r'\b1096\b', '10%', text)
    text = re.sub(r'\b90%6\b', '90%', text)
    text = re.sub(r'\b1006\b', '100', text)
    # OCR 将百分比数字拆开：200%6 → 20%, 809%6 → 80%
    text = re.sub(r'200%6', '20%', text)
    text = re.sub(r'809%6', '80%', text)
    text = re.sub(r'10%6', '10%', text)
    text = re.sub(r'90%6', '90%', text)
    # 也处理末尾带6的变体
    text = re.sub(r'200%\b', '20%', text)
    text = re.sub(r'809%\b', '80%', text)

    # 百分比 OCR 误识别修复
    text = re.sub(r'(\d{1,3})%(\d)', r'\1%\2', text)

    # 修复 OCR 把 ~ 识别成其他字符
    text = re.sub(r'[一—―]', '~', text)

    # 修复常见 OCR 单位/符号错误
    text = re.sub(r'\bKE\b', 'kg', text)
    text = re.sub(r'\bke\b', 'kg', text)
    text = re.sub(r'kKPa', 'kPa', text)
    text = re.sub(r'逞0O', '200', text)
    text = re.sub(r'\b([\d])O([\d])', r'\1O\2', text)  # 谨慎处理

    # 修复常见中文 OCR 错误
    corrections = {
        '温度控制范图': '温度控制范围',
        '定时范图': '定时范围',
        '分劲率': '分辨率',
        '均匀性万': '均匀性≤',
        '圆周振济': '圆周振荡',
        '控制精度土': '控制精度±',
        'HTS-100恒温热振烫器': 'HTS-100恒温热振荡器',
        '热振烫器': '热振荡器',
    }
    for wrong, right in corrections.items():
        text = text.replace(wrong, right)

    # 修复 ± 符号（土 → ±）
    text = re.sub(r'(?<=[\d\s])土(?=[\d])', '±', text)
    # 修复 ≤ 符号（万 → ≤）
    text = re.sub(r'(?<=[性\s])万(?=[土±\d])', '≤', text)
    text = re.sub(r'([<>])万(?=[土±\d])', r'\1≤', text)

    # 拆分 OCR 拼接的参数行：在单位/数值后紧跟参数名称处插入换行
    param_keywords = [
        '电源', '额定功率', '额定电压', '额定频率', '输入功率',
        '外形尺寸', '净重', '毛重',
        '温度控制范围', '温度控制精度', '温度显示分辨率', '温度均匀性',
        '温度上升时间', '温度下降时间', '升温时间', '降温时间',
        '振荡方式', '振荡转速', '振荡转速范围', '转速调节间隔', '转速调节步进',
        '振荡幅度', '振荡频率', '定时范围', '定时时间',
        '适配模块', '模块材料', '模块更换方式',
        '产品型号', '产品名称', '工作条件', '操作环境',
        '环境温度', '相对湿度', '大气压力',
        '使用环境', '储存温度', '储存湿度', '运输温度', '运输湿度',
        '连续运行', '文件编号', '版本', '关键参数',
    ]
    for kw in sorted(param_keywords, key=len, reverse=True):
        text = re.sub(
            r'([WVAHzΩkgmLCsminrp℃°\u2103\u2109%％\d])\s*' + re.escape(kw),
            r'\1\n' + kw, text
        )
        # 也处理中文→中文参数名的边界（如 "约8.5kg温度控制" → "约8.5kg\n温度控制"）
        text = re.sub(
            r'([\u4e00-\u9fff])\s*' + re.escape(kw),
            r'\1\n' + kw, text
        )

    return text


def _extract_params_multiline(text):
    """提取参数名和值在不同行的情况，如：
    额定电压
    220V
    """
    params = []
    seen = set()
    lines = [l.strip() for l in text.split('\n')]
    lines = [l for l in lines if l and len(l) > 0]

    if len(lines) < 2:
        return params

    i = 0
    while i < len(lines) - 1:
        name_line = lines[i]
        value_line = lines[i + 1]

        if _COLON_PATTERN.match(value_line) or _EQUALS_PATTERN.match(value_line):
            i += 1
            continue

        # 参数名不应过长，且不应包含数字（纯中文/英文关键词）
        if _is_param_like(name_line) and _is_value_like(value_line):
            if not _NUMERIC_PATTERN.search(name_line) and len(name_line) <= 16:
                name = normalize_param_name(name_line)
                value = parse_value(value_line)
                norm_name = name.casefold()
                if norm_name not in seen:
                    seen.add(norm_name)
                    params.append({"name": name, "value": value, "source": "text_ml"})
                i += 2
                continue
        i += 1

    return params


def extract_params_from_xlsx(filepath):
    try:
        from openpyxl import load_workbook
    except ImportError:
        return []

    try:
        wb = load_workbook(filepath, read_only=True, data_only=True)
    except Exception:
        return []

    all_params = {}

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows = []
        for row in ws.iter_rows(values_only=True):
            str_cells = [(str(c).strip() if c is not None else "") for c in row]
            if any(str_cells):
                rows.append(str_cells)

        sheet_params = extract_params_from_table_rows(rows)
        for p in sheet_params:
            key = p["name"].casefold()
            if key not in all_params:
                p["source"] = f"sheet_{sheet_name}"
                p["chapter"] = sheet_name
                all_params[key] = p

    wb.close()
    result = list(all_params.values())
    result.sort(key=lambda x: x["name"])
    return result


def _extract_raw_text(filepath):
    """提取文件中的原始文本（用于调试）"""
    ext = os.path.splitext(filepath)[1].lower()

    if ext in ('.docx', '.doc'):
        try:
            from docx import Document
            doc = Document(filepath)
            parts = []
            for para in doc.paragraphs:
                if para.text.strip():
                    parts.append(para.text.strip())
            for table in doc.tables:
                for row in table.rows:
                    cells = [cell.text.strip() for cell in row.cells]
                    if any(cells):
                        parts.append(" | ".join(cells))
            return "\n".join(parts)
        except Exception:
            return ""

    if ext == '.pdf':
        parts = []
        try:
            import fitz
            doc = fitz.open(filepath)
            for page in doc:
                t = page.get_text("text")
                if t and t.strip():
                    parts.append(t)
                else:
                    blocks = page.get_text("blocks")
                    for b in blocks:
                        if len(b) >= 5 and b[4].strip():
                            parts.append(b[4].strip())
                try:
                    found = page.find_tables()
                    tables = found.tables if found else []
                    for tab in tables:
                        for row in tab.extract() or []:
                            cells = [(c or "").strip() for c in row]
                            if not any(cells):
                                continue
                            line = " | ".join(cells)
                            if _STD_TOKEN_RE.search(line):
                                parts.append(line)
                except Exception:
                    pass
            doc.close()
            if parts:
                return "\n---PAGE---\n".join(parts)
        except Exception:
            pass

        try:
            import pdfplumber
            with pdfplumber.open(filepath) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t and t.strip():
                        parts.append(t)
            if parts:
                return "\n---PAGE---\n".join(parts)
        except Exception:
            pass

        ocr_text = _ocr_pdf_pages(filepath)
        if ocr_text.strip():
            return ocr_text

        return ""

    if ext in ('.xlsx', '.xls'):
        try:
            from openpyxl import load_workbook
            wb = load_workbook(filepath, read_only=True, data_only=True)
            parts = []
            for name in wb.sheetnames:
                ws = wb[name]
                for row in ws.iter_rows(values_only=True):
                    cells = [str(c).strip() if c is not None else "" for c in row]
                    if any(cells):
                        parts.append(" | ".join(cells))
            wb.close()
            return "\n".join(parts)
        except Exception:
            return ""

    if ext in ('.txt', '.md'):
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        except Exception:
            return ""

    return ""


def _clean_heading(text):
    s = (text or "").strip()
    s = re.sub(r"^#{1,6}\s*", "", s)
    s = re.sub(r"^第\s*[一二三四五六七八九十百零\d]+\s*[章节篇]\s*", "", s)
    s = re.sub(r"^[A-Za-z]?\d+(?:\.\d+)*\s+", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _is_heading_line(line):
    s = (line or "").strip()
    if not s or len(s) > 40:
        return False
    if s.endswith(("。", "；")):
        return False
    if re.search(r"[。]", s):
        return False
    if re.match(r"^#{1,6}\s+\S", s):
        return True
    if re.match(r"^第\s*[一二三四五六七八九十百零\d]+\s*[章节篇]", s):
        return True
    if re.match(r"^\d+(?:\.\d+){0,3}\s+[\u4e00-\u9fffA-Za-z]", s):
        if re.match(r"^\d+(\.\d+)?\s*(ml|mL|μL|uL|kg|g|mm|cm|m|V|W|Hz|A|℃)\b", s, re.I):
            return False
        return True
    known = (
        "安全", "产品概述", "产品介绍", "产品组成", "技术规格", "主要技术参数",
        "操作说明", "使用方法", "安装", "维护", "故障排除", "常见问题",
        "附录", "包装清单", "运输储存", "运输/储存环境", "操作环境",
        "预期用途", "适用范围", "结构组成", "运行环境", "使用环境", "工作环境",
        "符合标准", "符合标准清单", "产品性能", "技术指标", "制造商信息", "术语表",
        "工作原理", "禁忌症",
    )
    return any(s == k or s.startswith(k) for k in known)


def _name_in_text(name, text):
    if not name or not text:
        return False
    if name in text:
        return True
    compact_name = re.sub(r"\s+", "", name)
    compact_text = re.sub(r"\s+", "", text)
    return bool(compact_name) and compact_name in compact_text


def _pdf_pages_and_chapters(filepath):
    import fitz
    doc = fitz.open(filepath)
    try:
        n = int(doc.page_count or 0)
        pages = []
        for i in range(n):
            pages.append(doc[i].get_text("text") or "")
        chapters = [""] * n
        toc = doc.get_toc() or []
        if toc:
            items = []
            for i, item in enumerate(toc):
                level = int(item[0] or 1)
                title = str(item[1] or "").strip()
                page = max(1, min(int(item[2] or 1), n)) if n else 1
                end = n
                for j in range(i + 1, len(toc)):
                    if int(toc[j][0] or 1) <= level:
                        end = max(page, int(toc[j][2] or 1) - 1)
                        break
                if title:
                    items.append((level, title, page, end))
            for _level, title, page, end in sorted(items, key=lambda x: x[0]):
                for p in range(page, min(end, n) + 1):
                    chapters[p - 1] = title
        else:
            current = ""
            for i, text in enumerate(pages):
                for line in text.splitlines():
                    if _is_heading_line(line):
                        current = _clean_heading(line) or line.strip()
                        break
                chapters[i] = current
        return pages, chapters
    finally:
        doc.close()


def _attach_pdf_chapters(params, filepath):
    try:
        pages, chapters = _pdf_pages_and_chapters(filepath)
    except Exception:
        return
    for p in params:
        if p.get("chapter"):
            continue
        name = p.get("name") or ""
        found = ""
        for i, text in enumerate(pages):
            if _name_in_text(name, text):
                found = chapters[i] if i < len(chapters) else ""
                break
        p["chapter"] = found


def _attach_docx_chapters(params, filepath):
    try:
        from docx import Document
        from docx.oxml.ns import qn
        from docx.table import Table
        from docx.text.paragraph import Paragraph
    except ImportError:
        return
    try:
        doc = Document(filepath)
    except Exception:
        return
    current = ""
    mapping = {}

    def take_heading(text, style=""):
        nonlocal current
        style = style or ""
        if style.startswith("Heading") or style.startswith("标题"):
            current = _clean_heading(text) or text.strip()
            return True
        if _is_heading_line(text):
            current = _clean_heading(text) or text.strip()
            return True
        return False

    def note_text(text):
        for item in extract_params_from_text(text):
            mapping.setdefault(item["name"].casefold(), current)
        for p in params:
            key = (p.get("name") or "").casefold()
            if key and key not in mapping and _name_in_text(p.get("name"), text):
                mapping[key] = current

    body = doc.element.body
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            para = Paragraph(child, doc)
            text = para.text or ""
            style = para.style.name if para.style else ""
            if take_heading(text, style):
                continue
            if text.strip():
                note_text(text)
        elif child.tag == qn("w:tbl"):
            table = Table(child, doc)
            chunks = [cell.text or "" for row in table.rows for cell in row.cells]
            note_text("\n".join(chunks))
    for p in params:
        if not p.get("chapter"):
            p["chapter"] = mapping.get((p.get("name") or "").casefold(), "")


def _attach_text_chapters(params, text):
    current = ""
    mapping = {}
    for line in str(text or "").splitlines():
        s = line.strip()
        if not s:
            continue
        if _is_heading_line(s):
            current = _clean_heading(s) or s
            continue
        for item in extract_params_from_text(s):
            mapping.setdefault(item["name"].casefold(), current)
        for p in params:
            key = (p.get("name") or "").casefold()
            if key and key not in mapping and _name_in_text(p.get("name"), s):
                mapping[key] = current
    for p in params:
        if not p.get("chapter"):
            p["chapter"] = mapping.get((p.get("name") or "").casefold(), "")


def _attach_chapters(params, filepath):
    if not params or not filepath:
        return
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".pdf":
        _attach_pdf_chapters(params, filepath)
        return
    if ext in (".docx", ".doc"):
        _attach_docx_chapters(params, filepath)
        return
    if ext in (".xlsx", ".xls"):
        for p in params:
            if p.get("chapter"):
                continue
            source = p.get("source") or ""
            if source.startswith("sheet_"):
                p["chapter"] = source.replace("sheet_", "", 1)
        return
    if ext in (".txt", ".md"):
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        except Exception:
            return
        _attach_text_chapters(params, text)


_NOISE_NAME_RE = re.compile(
    r"(点击|按键|按钮|开关|开机|关机|界面|步骤|请先|请勿|"
    r"注意|警告|小心|提示|见图|见表|参见|参考|目录|页码|修订|"
    r"^y$|^LCD$)"
)

_HEADER_VALUES = {
    "尺寸", "范围", "名称", "参数", "规格", "单位", "数值", "要求", "项目", "说明",
    "类型", "型号", "序号", "类别", "内容", "备注", "描述",
}

_PREFERRED_CHAPTER_KEYS = (
    "技术规格", "技术参数", "主要技术", "产品规格",
    "网络要求", "网络安全", "网络",
    "电源要求", "电源", "电气",
    "操作环境", "运行环境", "使用环境", "工作环境",
    "预期用途", "产品组成", "结构组成", "适用范围",
    "符合标准", "产品性能", "技术指标",
)

DEFAULT_PARAM_TARGETS = [
    {"label": "预期用途", "aliases": ["预期用途", "预期用处", "用途"], "kind": "section"},
    {"label": "适用范围", "aliases": ["适用范围", "适用样本", "适用仪器", "应用范围"], "kind": "section"},
    {"label": "结构组成", "aliases": ["结构组成", "产品组成", "主要组成", "产品结构", "系统组成"], "kind": "section"},
    {
        "label": "符合标准清单",
        "aliases": [
            "符合标准清单", "符合法规标准清单", "符合标准", "法规标准",
            "执行标准", "适用标准", "参考标准", "符合的标准", "标准清单", "相关标准",
        ],
        "keywords": ["符合标准清单", "符合标准", "标准清单", "符合以下标准", "本仪器符合"],
        "kind": "section",
    },
    {
        "label": "产品性能-技术指标",
        "aliases": [
            "产品性能-技术指标", "产品性能 - 技术指标", "产品性能－技术指标",
            "产品性能", "技术指标", "主要技术指标", "产品技术指标",
        ],
        "keywords": ["产品性能-技术指标", "产品性能", "技术指标"],
        "kind": "section",
    },
    {"label": "仪器尺寸", "aliases": ["仪器尺寸", "外形尺寸", "整机尺寸", "尺寸"]},
    {"label": "重量", "aliases": ["净重", "毛重", "重量"]},
    {"label": "操作/运行环境温度", "aliases": ["操作/运行环境温度", "操作温度", "运行温度", "工作温度", "环境温度", "温度"]},
    {"label": "湿度", "aliases": ["相对湿度", "工作湿度", "环境湿度", "湿度"]},
    {"label": "大气压", "aliases": ["大气压力", "大气压", "气压"]},
    {"label": "电源电压", "aliases": ["电源电压", "额定电压", "输入电压", "电源", "电压"]},
    {"label": "额定功率", "aliases": ["额定功率", "功耗", "整机功率", "最大功率", "功率"]},
    {"label": "LCD尺寸", "aliases": ["LCD尺寸", "LCD 尺寸", "屏幕尺寸", "显示屏尺寸", "液晶屏尺寸", "显示屏", "触摸屏", "LCD"]},
    {"label": "分辨率", "aliases": ["屏幕分辨率", "显示分辨率", "分辨率"]},
]

_DEFAULT_TARGET_MAP = {t["label"]: t for t in DEFAULT_PARAM_TARGETS}


def _compact(text):
    return re.sub(r"\s+", "", text or "").casefold()


def _is_generic_chapter(title):
    t = re.sub(r"\s+", "", title or "")
    if not t:
        return True
    if t in {"说明书", "使用说明书", "目录", "封面", "前言", "首页"}:
        return True
    if t.endswith("说明书") and len(t) <= 30:
        return True
    return False


def _pick_chapter(candidates):
    cleaned = [(c or "").strip() for c in candidates if (c or "").strip()]
    preferred = [c for c in cleaned if _chapter_preferred(c) and not _is_generic_chapter(c)]
    if preferred:
        return preferred[0]
    specific = [c for c in cleaned if not _is_generic_chapter(c)]
    if specific:
        return specific[0]
    return ""


def _value_fits_target(label, value):
    v = (value or "").strip()
    if not v or v in _HEADER_VALUES:
        return False
    if label == "LCD尺寸":
        return bool(re.search(r"\d+(?:\.\d+)?\s*(英寸|寸|inch|in\b|\"|”)", v, re.I))
    if label == "电源电压":
        if re.search(r"不应|不得|必须|请勿|超过标称", v):
            return False
        return bool(re.search(r"\d.+\s*(V|伏)", v, re.I))
    if label == "额定功率":
        return bool(re.search(r"\d.+\s*(kW|W|瓦)", v, re.I))
    if label == "操作/运行环境温度":
        return bool(re.search(r"\d.+(℃|°C|℉|°F)", v, re.I))
    return True


def _is_toc_line(line):
    s = (line or "").strip()
    if not s:
        return False
    if re.search(r"[\.·．…‧]{3,}\s*\d+\s*$", s):
        return True
    if re.match(r"^\d+(?:\.\d+)*\s+\S.{0,40}\s+\d{1,3}$", s) and "。" not in s:
        return True
    return False


def _alias_pattern(aliases):
    parts = [re.escape(a) for a in sorted(aliases or [], key=len, reverse=True) if a]
    return "|".join(parts)


def _heading_matches_aliases(heading, aliases):
    ch = _compact(heading)
    if not ch:
        return False
    for alias in aliases or []:
        ac = _compact(alias)
        if len(ac) < 2:
            continue
        if ch == ac or ch.startswith(ac):
            return True
        if len(ac) >= 4 and ac in ch and len(ch) <= len(ac) + 12:
            return True
    return False


def _is_section_heading(line, aliases):
    raw = (line or "").strip()
    heading = _clean_heading(raw)
    if _is_heading_line(raw) or _is_heading_line(heading):
        return True
    return _compact(heading) in {_compact(a) for a in (aliases or []) if a}


def _is_running_header(line):
    s = (line or "").strip()
    if not s:
        return False
    if re.fullmatch(r"\d{1,3}", s):
        return True
    if "此页有意留白" in s or "---PAGE---" in s.replace(" ", ""):
        return True
    return _compact(s) in {"说明书", "目录", "封面", "前言"}


def _is_standards_internal_label(line):
    return _compact(line) in {
        "项目", "符合标准", "电磁兼容性", "安全要求", "电气安全",
        "环境要求", "性能要求", "生物相容性", "y",
    }


def _is_noise_line(line):
    s = (line or "").strip()
    if not s:
        return False
    if _is_running_header(s):
        return True
    return _compact(s) in {
        "部件", "功能", "名称", "说明", "序号", "仪器概述", "产品概述",
    }


def _structure_continues(line):
    s = (line or "").strip()
    if not s:
        return False
    if any(k in s for k in ("模块", "负责", "控制软件", "耗材", "货号", "部件", "功能")):
        return True
    return bool(re.match(r"^[yY•·●]\s*", s))


def _resume_after_blank(lines, blank_idx, aliases):
    blob = "".join(aliases or [])
    if not any(k in blob for k in ("结构组成", "产品组成")):
        return False
    for k in range(blank_idx + 1, min(len(lines), blank_idx + 12)):
        nxt = lines[k].strip()
        if not nxt or _is_toc_line(nxt) or _is_noise_line(nxt):
            continue
        if _starts_new_section(nxt, aliases):
            return False
        return _structure_continues(nxt)
    return False


def _starts_new_section(line, aliases=None):
    s = (line or "").strip()
    if not s:
        return False
    if _looks_like_standard_row(s):
        return False
    if _is_noise_line(s):
        return False
    blob = "".join(aliases or [])
    if "标准" in blob and _is_standards_internal_label(s):
        return False
    if aliases and _heading_matches_aliases(_clean_heading(s), aliases):
        return True
    if _is_heading_line(s):
        return True
    if _is_appendix_heading(s):
        return True
    return bool(re.match(r"^(?:#{1,6}\s+)?\d+(?:\.\d+)+\s+[\u4e00-\u9fffA-Za-z]", s))


def _is_appendix_heading(line):
    h = _compact(_clean_heading(line))
    if not h:
        return False
    h = h.replace("－", "-")
    titles = {
        "索引", "术语表", "目录", "封面", "前言",
        "技术规格", "符合标准清单", "符合标准",
        "产品性能-技术指标", "产品性能技术指标", "产品性能", "技术指标",
        "制造商信息", "有害物质表",
        "产品中有害物质的名称及含量", "产品中有害物质的名称及有害物质表",
        "预期用途", "适用范围", "结构组成", "产品组成",
        "工作原理", "禁忌症", "基本部件",
    }
    if h in titles:
        return True
    return h.replace("-", "") in {t.replace("-", "") for t in titles}


_STD_TOKEN_RE = re.compile(r"(?:GB|YY|ISO|IEC|EN)(?:/T)?\s*[\d.]+(?:-\d{4})?", re.I)


def _looks_like_standard_row(line):
    s = (line or "").strip()
    if not s:
        return False
    if _STD_TOKEN_RE.search(s):
        return True
    if "|" in s and re.search(r"(标准|GB|YY|ISO|IEC|EN)", s, re.I):
        return True
    return False


def _toc_like_body(val):
    s = re.sub(r"\s+", " ", val or "").strip()
    if not s:
        return True
    catalog_hits = sum(1 for m in ("产品性能", "制造商信息", "有害物质", "索引", "术语表") if m in s)
    if catalog_hits >= 2 and not _STD_TOKEN_RE.search(s):
        return True
    if _STD_TOKEN_RE.search(s) or re.search(r"[。；：:]", s) or re.search(r"\d", s):
        return False
    parts = [p for p in re.split(r"[\s/、|]+", s) if p]
    short = [p for p in parts if 2 <= len(p) <= 18]
    return len(parts) >= 3 and len(short) >= 3 and len(s) <= 90


def _section_quality(val):
    s = val or ""
    if _toc_like_body(s):
        return -1000
    score = min(len(s), 400)
    if re.search(r"[。；]", s):
        score += 200
    score += 80 * len(_STD_TOKEN_RE.findall(s))
    if "各部件功能说明" in s:
        score += 500
    if s.count("模块") >= 3:
        score += 150
    if "本仪器符合以下标准" in s:
        score += 300
    if "示意图" in s or re.search(r"图\s*\d+", s):
        score -= 400
    return score


def _looks_like_location_value(val, aliases):
    s = re.sub(r"\s+", " ", (val or "")).strip()
    if not s:
        return True
    if re.fullmatch(r"\d{1,4}", s):
        return True
    if re.fullmatch(r"[.\·．…‧\s\-—_]+", s):
        return True
    compact = _compact(s)
    if any(compact == _compact(a) for a in (aliases or []) if a):
        return True
    if re.match(r"^\d+(?:\.\d+)+\s+\S+$", s) and len(s) <= 40:
        return True
    return False


def _inline_section_rest(line, aliases):
    raw = (line or "").strip()
    heading = _clean_heading(raw)
    if any(_compact(heading) == _compact(a) for a in (aliases or []) if a):
        return ""
    parts = re.split(r"[:：]", raw, 1)
    if len(parts) == 2 and parts[1].strip() and not _is_heading_line(parts[1].strip()) and not _is_toc_line(parts[1]):
        return parts[1].strip()
    pat = _alias_pattern(aliases)
    if not pat:
        return ""
    m = re.match(
        rf"^(?:#{{1,6}}\s+|第\s*[一二三四五六七八九十百零\d]+\s*[章节篇]\s+)?(?:[A-Za-z]?\d+(?:\.\d+)*\s+)?(?:{pat})\s+(.+)$",
        raw,
    )
    if not m:
        return ""
    rest = m.group(1).strip(" :：")
    if not rest or _is_heading_line(rest) or _is_toc_line(rest):
        return ""
    return rest


def _section_allows_blank(aliases):
    blob = "".join(aliases or [])
    return any(k in blob for k in ("标准", "产品性能", "技术指标"))


def _clip_at_next_section(val, aliases):
    own = {_compact(a) for a in (aliases or []) if a}
    s = val or ""
    cut = len(s)
    markers = (
        "工作原理", "禁忌症", "预期用途", "适用范围", "结构组成", "产品组成",
        "符合标准清单", "符合标准", "产品性能", "技术指标", "技术规格",
        "制造商信息", "有害物质", "操作说明", "使用方法", "主要技术参数",
        "基本部件",
    )
    for marker in markers:
        if _compact(marker) in own:
            continue
        m = re.search(rf"(?<=[。；;])\s*{re.escape(marker)}", s)
        if m and m.start() >= 8:
            cut = min(cut, m.start())
            continue
        m = re.search(rf"(?:^|[\n])\s*{re.escape(marker)}(?:\s|[:：]|$)", s)
        if m and m.start() >= 8:
            cut = min(cut, m.start())
    return s[:cut].strip()


def _format_structure_value(val):
    s = re.sub(r"\s+", " ", val or "").strip()
    if not s:
        return s
    module_pat = r"(?:主机\s*)?(?:主体|外壳|显示|电源|控制|计算)模块"
    pattern = (
        rf"({module_pat})"
        r"\s*(负责.+?)"
        rf"(?={module_pat}\s*负责|控制软件|耗材|$)"
    )
    items = list(re.finditer(pattern, s, re.S))
    if len(items) < 2:
        return s
    intro = s[: items[0].start()].strip()
    intro = re.sub(
        r"(?:各部件功能说明如下[:：]?)?\s*(?:部件\s*功能)?\s*(?:主机)?\s*$",
        "",
        intro,
    ).strip()
    lines = []
    if intro:
        lines.append(re.sub(r"\s+", " ", intro))
    lines.append("各部件功能说明如下：")
    for m in items:
        name = re.sub(r"\s+", "", m.group(1))
        name = re.sub(r"^主机", "", name) or name
        desc = re.sub(r"\s+", " ", m.group(2)).strip(" ；;，,")
        lines.append(f"{name} | {desc}")
    rest = s[items[-1].end():].strip()
    rest = re.sub(r"^(?:部件|功能)\s*", "", rest)
    if rest:
        sw = re.search(r"控制软件\s*", rest)
        if sw:
            after = rest[sw.end():].strip()
            parts = re.split(r"(?=耗材|DNBSEQ-E25\s*集成测序载片)", after, 1)
            sw_desc = re.sub(r"\s+", " ", parts[0]).strip(" ；;，,")
            sw_desc = re.sub(r"\s*[yY•·●]\s*", "；", sw_desc)
            sw_desc = re.sub(r"^[；\s]+", "", sw_desc).strip(" ；;")
            if sw_desc:
                lines.append(f"控制软件 | {sw_desc}")
            if len(parts) > 1:
                consum = re.sub(r"\s+", " ", parts[1]).strip()
                consum = re.sub(r"^耗材[，,]?", "", consum).strip()
                if consum:
                    lines.append(f"耗材 | {consum}")
        else:
            extra = re.sub(r"\s+", " ", rest).strip()
            if extra:
                lines.append(extra)
    return "\n".join(lines)


def _format_standards_value(val):
    s = re.sub(r"\s+", " ", val or "").strip()
    if not s:
        return s
    tokens = list(_STD_TOKEN_RE.finditer(s))
    if not tokens:
        return s
    intro = s[: tokens[0].start()]
    intro = re.sub(r"(?:\s*(?:项目|符合标准|电磁兼容性|安全要求|y))+\s*$", "", intro, flags=re.I)
    intro = intro.strip(" ：:")
    lines = []
    if intro:
        lines.append(intro)
    seen = set()
    for i, m in enumerate(tokens):
        ident = re.sub(r"\s+", " ", m.group(0)).strip()
        key = re.sub(r"\s+", "", ident).upper()
        if key in seen:
            continue
        seen.add(key)
        end = tokens[i + 1].start() if i + 1 < len(tokens) else len(s)
        desc = re.sub(r"\s+", " ", s[m.end():end])
        desc = re.sub(r"---PAGE---", " ", desc)
        desc = re.sub(
            r"(?:\s*(?:电磁兼容性|安全要求|项目|符合标准|y|\|))+\s*$",
            "",
            desc,
            flags=re.I,
        )
        desc = re.sub(r"^(?:\s*y\s*)+", "", desc).strip(" ；;，,、/|")
        lines.append(f"{ident} | {desc}" if desc else ident)
    return "\n".join(lines)


def _dedupe_section_text(val):
    s = re.sub(r"\s+", " ", val or "").strip()
    if not s:
        return s
    compact = re.sub(r"\s+", "", s)
    n = len(compact)
    if n >= 40:
        half = n // 2
        if compact[:half] == compact[half:half * 2] or compact[:half] == compact[-half:]:
            mid = len(s) // 2
            return s[:mid].strip()
    parts = re.split(r"(?<=[。；;])\s*", s)
    out, seen = [], set()
    for p in parts:
        key = re.sub(r"\s+", "", p)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(p)
    return " ".join(out).strip()


def _collect_section_body(lines, start, aliases, max_len, allow_blank=False):
    raw = (lines[start] if start < len(lines) else "").strip()
    heading = _clean_heading(raw)
    buf = []
    inline_rest = _inline_section_rest(raw, aliases)
    if inline_rest and not _looks_like_location_value(inline_rest, aliases):
        buf.append(inline_rest)
    for j in range(start + 1, len(lines)):
        nxt = lines[j].strip()
        if not nxt:
            if buf and not allow_blank:
                if not _resume_after_blank(lines, j, aliases):
                    break
            continue
        if _is_toc_line(nxt) or _is_noise_line(nxt):
            continue
        if _starts_new_section(nxt, aliases):
            break
        if _looks_like_location_value(nxt, aliases):
            continue
        buf.append(nxt)
        if sum(len(x) for x in buf) >= max_len:
            break
    val = re.sub(r"---PAGE---", " ", " ".join(buf))
    val = re.sub(r"\s+", " ", val).strip()
    val = _dedupe_section_text(val)
    if not val or _looks_like_location_value(val, aliases) or _toc_like_body(val):
        return "", heading
    return val[:max_len], heading or (aliases[0] if aliases else "")


def _section_max_len(label):
    n = str(label or "")
    if any(k in n for k in ("标准", "产品性能", "技术指标", "结构组成", "产品组成")):
        return 8000
    return 1200


def _extract_section_value(text, aliases, max_len=2000, keywords=None):
    lines = str(text or "").splitlines()
    best_val, best_heading, best_score = "", "", -10 ** 9
    for i, line in enumerate(lines):
        raw = line.strip()
        if not raw or _is_toc_line(raw):
            continue
        heading = _clean_heading(raw)
        if not _heading_matches_aliases(heading, aliases):
            continue
        inline_rest = _inline_section_rest(raw, aliases)
        if not _is_section_heading(raw, aliases) and not inline_rest:
            continue
        val, heading = _collect_section_body(
            lines, i, aliases, max_len, allow_blank=_section_allows_blank(aliases),
        )
        if not val:
            continue
        score = _section_quality(val)
        if score > best_score:
            best_val, best_heading, best_score = val, heading, score
    keys = []
    seen = set()
    for item in list(keywords or []) + list(aliases or []):
        k = (item or "").strip()
        if len(k) < 2 or k in seen:
            continue
        seen.add(k)
        keys.append(k)
    if not best_val and keys:
        for i, line in enumerate(lines):
            raw = line.strip()
            if not raw or _is_toc_line(raw):
                continue
            if not any(k in raw for k in keys):
                continue
            val, heading = _collect_section_body(
                lines, i, aliases or keys, max_len, allow_blank=_section_allows_blank(aliases or keys),
            )
            if not val:
                continue
            score = _section_quality(val) + 40
            if score > best_score:
                best_val, best_heading, best_score = val, heading or _clean_heading(raw), score
    if best_val:
        best_val = _clip_at_next_section(best_val, aliases)
        blob = "".join(aliases or [])
        if any(k in blob for k in ("结构组成", "产品组成")):
            best_val = _format_structure_value(best_val)
        if any(k in blob for k in ("标准清单", "符合标准", "法规标准")):
            best_val = _format_standards_value(best_val)
    return best_val, best_heading


def parse_param_names(raw):
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        parts = [str(x).strip() for x in raw]
    else:
        parts = re.split(r"[,，;；\n]+", str(raw))
    names = []
    seen = set()
    for part in parts:
        name = part.strip()
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def resolve_param_targets(raw_names=None):
    names = parse_param_names(raw_names)
    if not names:
        return [dict(t) for t in DEFAULT_PARAM_TARGETS]
    targets = []
    for name in names:
        found = _DEFAULT_TARGET_MAP.get(name)
        if found:
            targets.append(dict(found))
            continue
        for item in DEFAULT_PARAM_TARGETS:
            aliases = [_compact(a) for a in item["aliases"]]
            if _compact(name) in aliases:
                targets.append(dict(item))
                break
        else:
            targets.append({"label": name, "aliases": [name]})
    return targets


def _chapter_preferred(chapter):
    s = chapter or ""
    return any(k in s for k in _PREFERRED_CHAPTER_KEYS)


def _name_target_score(name, aliases):
    n = _compact(name)
    if not n or len(n) < 2:
        return 0
    best = 0
    for alias in aliases:
        a = _compact(alias)
        if not a:
            continue
        if n == a:
            best = max(best, 100 + min(len(n), 20))
            continue
        if n.startswith(a) or a.startswith(n) or n.endswith(a) or a.endswith(n):
            gap = abs(len(n) - len(a)) / max(len(n), len(a))
            if gap <= 0.35:
                best = max(best, 80)
            elif min(len(n), len(a)) >= 4:
                best = max(best, 55)
    return best


def _extract_target_value_from_text(text, aliases, label=""):
    lines = str(text or "").splitlines()
    for alias in aliases:
        a = re.sub(r"\s+", r"\\s*", re.escape(alias))
        pats = (
            re.compile(rf"^{a}(?:\s*范围)?\s*[:：]\s*(.+)$"),
            re.compile(rf"^{a}(?:\s*范围)?\s+(.+)$"),
            re.compile(rf"^{a}(\d.+)$"),
            re.compile(rf"^{a}((?:AC|DC)\s*.+)$", re.IGNORECASE),
        )
        for line in lines:
            stripped = line.strip()
            for pat in pats:
                m = pat.match(stripped)
                if not m:
                    continue
                val = parse_value(m.group(1).strip())
                val = re.split(r"[。；;]", val)[0].strip()
                if val and val not in _HEADER_VALUES and _is_value_like(val):
                    if not label or _value_fits_target(label, val):
                        return val
        compact_alias = _compact(alias)
        for i, line in enumerate(lines):
            if _compact(line) != compact_alias:
                continue
            if i + 1 >= len(lines):
                continue
            nxt = parse_value(lines[i + 1].strip())
            nxt = re.split(r"[。；;]", nxt)[0].strip()
            if nxt in _HEADER_VALUES and i + 2 < len(lines):
                nxt = parse_value(lines[i + 2].strip())
            if nxt and nxt not in _HEADER_VALUES and _is_value_like(nxt):
                if not label or _value_fits_target(label, nxt):
                    return nxt
    return ""


def select_target_params(params, text, targets):
    selected = []
    used = set()
    for target in targets:
        label = target["label"]
        aliases = target.get("aliases") or [label]
        if target.get("kind") == "section":
            value, heading = _extract_section_value(
                text,
                aliases,
                max_len=_section_max_len(label),
                keywords=target.get("keywords") or aliases,
            )
            if value:
                selected.append({
                    "name": label,
                    "value": value,
                    "source": "section",
                    "chapter": heading or "",
                })
            continue
        best = None
        best_score = 0
        for idx, param in enumerate(params):
            if idx in used:
                continue
            name = param.get("name") or ""
            score = _name_target_score(name, aliases)
            if score < 55:
                continue
            if _chapter_preferred(param.get("chapter") or ""):
                score += 20
            value = (param.get("value") or "").strip()
            if value in _HEADER_VALUES or not _value_fits_target(label, value):
                continue
            if score > best_score:
                best_score = score
                best = (idx, param)
        if best and best_score >= 55:
            idx, param = best
            used.add(idx)
            value = (param.get("value") or "").strip()
            selected.append({
                "name": label,
                "value": value,
                "source": param.get("source") or "",
                "chapter": param.get("chapter") or "",
            })
            continue
        value = _extract_target_value_from_text(text, aliases, label)
        if value and _value_fits_target(label, value):
            selected.append({
                "name": label,
                "value": value,
                "source": "text",
                "chapter": "",
            })
    return selected


def extract_params(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    if ext in ('.docx', '.doc'):
        params = extract_params_from_docx(filepath)
    elif ext == '.pdf':
        params = extract_params_from_pdf(filepath)
    elif ext in ('.xlsx', '.xls'):
        params = extract_params_from_xlsx(filepath)
    elif ext in ('.txt', '.md'):
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
            params = sorted(extract_params_from_text(text), key=lambda x: x["name"])
        except Exception:
            params = []
    else:
        params = []
    _attach_chapters(params, filepath)
    kept_aliases = {_compact(a) for t in DEFAULT_PARAM_TARGETS for a in t.get("aliases") or []}
    return [
        p for p in params
        if (not _NOISE_NAME_RE.search(p.get("name") or ""))
        or _compact(p.get("name") or "") in kept_aliases
    ]


def _fuzzy_match_key(key, candidates, threshold=0.70):
    best_score = 0
    best_key = None
    key_lower = key.casefold()
    for cand in candidates:
        cand_lower = cand.casefold()
        if key_lower == cand_lower:
            return 1.0, cand
        sim = SequenceMatcher(None, key_lower, cand_lower).ratio()
        if sim < threshold:
            edit_sim = _edit_similarity(key_lower, cand_lower)
            sim = max(sim, edit_sim)
        if sim < threshold:
            sim = max(sim, _common_prefix_similarity(key_lower, cand_lower))
        if sim > best_score:
            best_score = sim
            best_key = cand
    if best_score >= threshold:
        return best_score, best_key
    return 0, None


def _common_prefix_similarity(s1, s2):
    """公共前缀加权相似度，用于匹配同义词（如"使用地点"≈"使用场所"）"""
    n = min(len(s1), len(s2))
    prefix_len = 0
    for i in range(n):
        if s1[i] == s2[i]:
            prefix_len += 1
        else:
            break
    if prefix_len < 2:
        return 0
    prefix_ratio = prefix_len / max(len(s1), len(s2))
    if prefix_ratio < 0.3:
        return 0
    return 0.60 + prefix_ratio * 0.25


def _edit_similarity(s1, s2):
    """字符级编辑距离相似度，对中文短文本（<=15字）更敏感"""
    if not s1 or not s2:
        return 0
    if len(s1) > 15 or len(s2) > 15:
        return 0
    max_len = max(len(s1), len(s2))
    if max_len == 0:
        return 1.0
    d = [[0] * (len(s2) + 1) for _ in range(len(s1) + 1)]
    for i in range(len(s1) + 1):
        d[i][0] = i
    for j in range(len(s2) + 1):
        d[0][j] = j
    for i in range(1, len(s1) + 1):
        for j in range(1, len(s2) + 1):
            cost = 0 if s1[i-1] == s2[j-1] else 1
            d[i][j] = min(d[i-1][j] + 1, d[i][j-1] + 1, d[i-1][j-1] + cost)
    return 1.0 - d[len(s1)][len(s2)] / max_len


def _values_equal(v1, v2):
    v1c = v1.strip().casefold()
    v2c = v2.strip().casefold()
    if v1c == v2c:
        return True
    v1c = re.sub(r'\s+', ' ', v1c)
    v2c = re.sub(r'\s+', ' ', v2c)
    return v1c == v2c


def _param_kind(name):
    n = str(name or "")
    if any(k in n for k in ("用途", "适用范围", "结构组成", "产品组成", "标准清单", "符合标准", "产品性能", "技术指标")):
        return "section"
    if any(k in n for k in ("重量", "净重", "毛重")):
        return "weight"
    if any(k in n for k in ("温度", "湿度", "大气压", "气压")):
        return "range"
    if "电压" in n:
        return "voltage"
    if "功率" in n:
        return "power"
    if any(k in n for k in ("尺寸", "长", "宽", "高")):
        return "dimension"
    return "text"


def _unify_value_text(raw):
    v = str(raw or "").strip()
    v = v.replace("（", "(").replace("）", ")")
    v = v.replace("，", ",").replace("～", "~")
    v = re.sub(r"[−‐‑‒–—―]", "-", v)
    v = re.sub(r"\s*[×xX]\s*", "×", v)
    v = re.sub(r"[（(]\s*(长|宽|高|深|厚)\s*[）)]", "", v)
    v = re.sub(r"\s+", "", v)
    return v.casefold()


def _extra_constraint(raw):
    v = _unify_value_text(raw)
    v = re.sub(
        r"\d+(?:[.,]\d+)?|kpa|mpa|hpa|pa\b|℃|°c|℉|%|rh\b|mmhg|atm|"
        r"mm\b|cm\b|m\b|米|kg\b|g\b|w\b|kw\b|v\b|vac|hz|英寸|寸|inch",
        "",
        v,
        flags=re.I,
    )
    v = re.sub(r"[()（）~,~\-×x]", "", v)
    return v


def _section_plain(raw):
    v = str(raw or "").strip()
    v = v.replace("（", "(").replace("）", ")")
    v = v.replace("，", ",").replace("～", "~")
    v = re.sub(r"[−‐‑‒–—―]", "-", v)
    v = re.sub(r"\s+", "", v)
    return v.casefold()


def _parse_numbers(raw):
    return [
        float(x.replace(",", ""))
        for x in re.findall(r"\d+(?:,\d{3})*(?:\.\d+)?", str(raw or ""))
    ]


def _parse_range(raw):
    nums = _parse_numbers(raw)
    if len(nums) >= 2:
        lo, hi = nums[0], nums[1]
        if lo > hi:
            lo, hi = hi, lo
        return lo, hi
    if len(nums) == 1:
        return nums[0], nums[0]
    return None


def _within_abs_or_pct(a, b, abs_tol, pct):
    if a == b:
        return True
    diff = abs(a - b)
    base = max(abs(a), abs(b), 1e-9)
    return diff <= abs_tol or diff / base <= pct


def _values_consistent(name, v1, v2):
    """Apply multi-file consistency rules: format noise, range overlap, numeric tolerance."""
    if _values_equal(v1, v2):
        return True
    kind = _param_kind(name)
    if kind == "section":
        return bool(_section_plain(v1) and _section_plain(v1) == _section_plain(v2))
    if _extra_constraint(v1) != _extra_constraint(v2):
        return False
    n1 = _unify_value_text(v1)
    n2 = _unify_value_text(v2)
    if n1 == n2:
        return True
    nums1, nums2 = _parse_numbers(v1), _parse_numbers(v2)
    r1, r2 = _parse_range(v1), _parse_range(v2)
    if kind == "range" and r1 and r2:
        return r1[1] >= r2[0] and r2[1] >= r1[0]
    if kind == "dimension" and nums1 and nums2 and len(nums1) == len(nums2):
        return all(_within_abs_or_pct(a, b, 10, 0.05) for a, b in zip(nums1, nums2))
    if kind == "weight" and nums1 and nums2:
        return _within_abs_or_pct(nums1[0], nums2[0], 1, 0.05)
    if kind == "voltage" and nums1 and nums2:
        if len(nums1) == len(nums2):
            return all(abs(a - b) <= 10 for a, b in zip(nums1, nums2))
        if r1 and r2:
            return r1[1] >= r2[0] and r2[1] >= r1[0]
        return False
    if kind == "power" and nums1 and nums2:
        return _within_abs_or_pct(nums1[0], nums2[0], 0, 0.10)
    return bool(nums1) and nums1 == nums2


def _translate_source(source):
    """将内部 source 编码翻译为可读的中文标签"""
    if not source:
        return ""
    if source == "text":
        return "正文"
    if source == "text_ml":
        return "正文(多行)"
    if source == "ocr_concat":
        return "OCR提取"
    if source.startswith("table_row_"):
        n = source.replace("table_row_", "")
        return f"表格第{n}行" if n.isdigit() else f"表格行"
    if source.startswith("sheet_"):
        name = source.replace("sheet_", "")
        return f"工作表「{name}」"
    return source


def compare_params(params_a, params_b):
    keys_a = {p["name"].casefold(): p for p in params_a}
    keys_b = {p["name"].casefold(): p for p in params_b}

    matched_b = set()
    results = []

    for pa in params_a:
        key = pa["name"].casefold()
        if key in keys_b:
            pb = keys_b[key]
            matched_b.add(key)
            equal = _values_consistent(pa["name"], pa["value"], pb["value"])
            results.append({
                "param": pa["name"],
                "value_a": pa["value"],
                "value_b": pb["value"],
                "match": "一致" if equal else "不一致",
                "source_a": _translate_source(pa.get("source", "")),
                "source_b": _translate_source(pb.get("source", "")),
                "chapter_a": pa.get("chapter") or "",
                "chapter_b": pb.get("chapter") or "",
            })
        else:
            score, matched_key = _fuzzy_match_key(key, [k for k in keys_b if k not in matched_b])
            if matched_key:
                pb = keys_b[matched_key]
                matched_b.add(matched_key)
                equal = _values_consistent(pa["name"], pa["value"], pb["value"])
                results.append({
                    "param": pa["name"],
                    "value_a": pa["value"],
                    "value_b": pb["value"],
                    "match": "一致" if equal else "不一致",
                    "fuzzy": True,
                    "fuzzy_score": round(score, 3),
                    "matched_param": pb["name"],
                    "source_a": _translate_source(pa.get("source", "")),
                    "source_b": _translate_source(pb.get("source", "")),
                    "chapter_a": pa.get("chapter") or "",
                    "chapter_b": pb.get("chapter") or "",
                })
            else:
                results.append({
                    "param": pa["name"],
                    "value_a": pa["value"],
                    "value_b": "",
                    "match": "仅A有",
                    "source_a": _translate_source(pa.get("source", "")),
                    "source_b": "",
                    "chapter_a": pa.get("chapter") or "",
                    "chapter_b": "",
                })

    for pb in params_b:
        key = pb["name"].casefold()
        if key not in matched_b:
            results.append({
                "param": pb["name"],
                "value_a": "",
                "value_b": pb["value"],
                "match": "仅B有",
                "source_a": "",
                "source_b": _translate_source(pb.get("source", "")),
                "chapter_a": "",
                "chapter_b": pb.get("chapter") or "",
            })

    return results


def _fill_missing_chapters(selected, filepath, targets):
    if not selected or not filepath:
        return
    text = _extract_raw_text(filepath)
    by_label = {t["label"]: t for t in targets}
    pages, chapters = None, None
    if os.path.splitext(filepath)[1].lower() == ".pdf":
        try:
            pages, chapters = _pdf_pages_and_chapters(filepath)
        except Exception:
            pages, chapters = None, None
    for p in selected:
        cur = (p.get("chapter") or "").strip()
        if cur and not _is_generic_chapter(cur):
            continue
        aliases = (by_label.get(p["name"]) or {}).get("aliases") or [p["name"]]
        cands = []
        if pages:
            for i, page_text in enumerate(pages):
                if any(_name_in_text(a, page_text) for a in aliases):
                    cands.append(chapters[i] if i < len(chapters) else "")
        else:
            current = ""
            for line in str(text or "").splitlines():
                s = line.strip()
                if not s:
                    continue
                if _is_heading_line(s):
                    current = _clean_heading(s) or s
                    continue
                if any(_name_in_text(a, s) for a in aliases):
                    cands.append(current)
        picked = _pick_chapter(cands)
        if picked:
            p["chapter"] = picked
        elif _is_generic_chapter(cur):
            p["chapter"] = ""


def run_param_compare(file_a_path, file_b_path, param_names=None):
    params_a = extract_params(file_a_path)
    params_b = extract_params(file_b_path)
    targets = resolve_param_targets(param_names)
    params_a = select_target_params(params_a, _extract_raw_text(file_a_path), targets)
    params_b = select_target_params(params_b, _extract_raw_text(file_b_path), targets)
    _fill_missing_chapters(params_a, file_a_path, targets)
    _fill_missing_chapters(params_b, file_b_path, targets)

    compared = compare_params(params_a, params_b)
    by_name = {row["param"]: row for row in compared}
    results = []
    for target in targets:
        label = target["label"]
        row = by_name.get(label)
        if row:
            results.append(row)
            continue
        results.append({
            "param": label,
            "value_a": "",
            "value_b": "",
            "match": "缺失",
            "source_a": "",
            "source_b": "",
            "chapter_a": "",
            "chapter_b": "",
        })

    n_total = len(results)
    n_match = sum(1 for r in results if r["match"] == "一致")
    n_diff = sum(1 for r in results if r["match"] == "不一致")
    n_only_a = sum(1 for r in results if r["match"] == "仅A有")
    n_only_b = sum(1 for r in results if r["match"] == "仅B有")

    return {
        "file_a": os.path.basename(file_a_path),
        "file_b": os.path.basename(file_b_path),
        "params_a_count": len(params_a),
        "params_b_count": len(params_b),
        "total": n_total,
        "match_count": n_match,
        "diff_count": n_diff,
        "only_a_count": n_only_a,
        "only_b_count": n_only_b,
        "results": results,
        "param_names": [t["label"] for t in targets],
    }
