import os
import zipfile
import xml.etree.ElementTree as ET
from docx import Document as DocxDocument
from PyPDF2 import PdfReader
import markdown

def parse_pdf(file_path):
    try:
        reader = PdfReader(file_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text.strip()
    except Exception as e:
        raise ValueError(f"PDF解析失败: {str(e)}")

def parse_docx(file_path):
    try:
        doc = DocxDocument(file_path)
        text = ""
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"
        return text.strip()
    except Exception as e:
        raise ValueError(f"DOCX解析失败: {str(e)}")

def parse_markdown(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return content.strip()
    except Exception as e:
        raise ValueError(f"MD解析失败: {str(e)}")

def parse_dita_zip(file_path):
    try:
        text = ""
        with zipfile.ZipFile(file_path, 'r') as zip_ref:
            for name in zip_ref.namelist():
                if name.endswith('.dita') or name.endswith('.xml'):
                    with zip_ref.open(name) as f:
                        content = f.read().decode('utf-8')
                        root = ET.fromstring(content)
                        text += ' '.join(root.itertext()) + "\n"
        return text.strip()
    except Exception as e:
        raise ValueError(f"DITA ZIP解析失败: {str(e)}")

def parse_text(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except Exception as e:
        raise ValueError(f"文本文件解析失败: {str(e)}")

def parse_idml(file_path):
    try:
        text = ""
        with zipfile.ZipFile(file_path, 'r') as zip_ref:
            for name in zip_ref.namelist():
                if name.endswith('.xml'):
                    with zip_ref.open(name) as f:
                        content = f.read().decode('utf-8')
                        root = ET.fromstring(content)
                        text += ' '.join(root.itertext()) + "\n"
        return text.strip()
    except Exception as e:
        raise ValueError(f"IDML解析失败: {str(e)}")

def parse_dita(file_path):
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        ns = {"dita": "http://docs.oasis-open.org/dita/v1.1/ns.dita"}
        text = " ".join(root.itertext())
        return text.strip()
    except Exception as e:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            root = ET.fromstring(content)
            return " ".join(root.itertext()).strip()
        except Exception:
            raise ValueError(f"DITA解析失败: {str(e)}")

def parse_xlsx(file_path):
    try:
        from openpyxl import load_workbook
        wb = load_workbook(file_path, read_only=True, data_only=True)
        texts = []
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            texts.append(f"[Sheet: {sheet_name}]")
            for row in ws.iter_rows(values_only=True):
                row_texts = []
                for cell in row:
                    if cell is not None:
                        row_texts.append(str(cell))
                if row_texts:
                    texts.append("\t".join(row_texts))
        wb.close()
        return "\n".join(texts)
    except Exception as e:
        raise ValueError(f"XLSX解析失败: {str(e)}")

def parse_pptx(file_path):
    try:
        text = ""
        import re
        with zipfile.ZipFile(file_path, 'r') as zf:
            slide_files = [n for n in zf.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml")]
            slide_files.sort(key=lambda x: int(re.search(r'slide(\d+)', x).group(1)))

            for slide_name in slide_files:
                with zf.open(slide_name) as f:
                    content = f.read().decode('utf-8')
                    root = ET.fromstring(content)
                    ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
                    slide_texts = []
                    for t_elem in root.iter(f"{{{ns['a']}}}t"):
                        if t_elem.text:
                            slide_texts.append(t_elem.text)
                    if slide_texts:
                        text += "\n".join(slide_texts) + "\n"
        return text.strip()
    except Exception as e:
        raise ValueError(f"PPTX解析失败: {str(e)}")

def parse_xlf(file_path):
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        ns = {"xliff": "urn:oasis:names:tc:xliff:document:1.2"}

        texts = []
        for tu in root.iter("{urn:oasis:names:tc:xliff:document:1.2}trans-unit"):
            source = tu.find("{urn:oasis:names:tc:xliff:document:1.2}source")
            if source is not None and source.text:
                texts.append(source.text.strip())

        if not texts:
            for source in root.iter("{urn:oasis:names:tc:xliff:document:1.2}source"):
                if source.text and source.text.strip():
                    texts.append(source.text.strip())

        return "\n".join(texts) if texts else ""
    except Exception as e:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            root = ET.fromstring(content)
            texts = []
            xliff_ns = "urn:oasis:names:tc:xliff:document:1.2"
            for tu in root.iter(f"{{{xliff_ns}}}trans-unit"):
                source = tu.find(f"{{{xliff_ns}}}source")
                if source is not None and source.text:
                    texts.append(source.text.strip())
            if not texts:
                for source in root.iter(f"{{{xliff_ns}}}source"):
                    if source.text and source.text.strip():
                        texts.append(source.text.strip())
            return "\n".join(texts) if texts else ""
        except Exception:
            raise ValueError(f"XLF解析失败: {str(e)}")

def parse_file(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == '.pdf':
        return parse_pdf(file_path)
    elif ext == '.docx':
        return parse_docx(file_path)
    elif ext == '.md':
        return parse_markdown(file_path)
    elif ext == '.zip':
        return parse_dita_zip(file_path)
    elif ext == '.dita':
        return parse_dita(file_path)
    elif ext == '.xls':
        return parse_xlsx(file_path)
    elif ext == '.xlsx':
        return parse_xlsx(file_path)
    elif ext == '.pptx':
        return parse_pptx(file_path)
    elif ext == '.xlf':
        return parse_xlf(file_path)
    elif ext == '.txt':
        return parse_text(file_path)
    elif ext == '.idml':
        return parse_idml(file_path)
    else:
        raise ValueError(f"不支持的文件格式: {ext}")

def get_file_type(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.pdf':
        return 'pdf'
    elif ext == '.docx':
        return 'docx'
    elif ext == '.md':
        return 'md'
    elif ext == '.zip':
        return 'dita'
    elif ext == '.dita':
        return 'dita'
    elif ext == '.xls':
        return 'xlsx'
    elif ext == '.xlsx':
        return 'xlsx'
    elif ext == '.pptx':
        return 'pptx'
    elif ext == '.xlf':
        return 'xlf'
    elif ext == '.txt':
        return 'txt'
    elif ext == '.idml':
        return 'idml'
    return 'unknown'