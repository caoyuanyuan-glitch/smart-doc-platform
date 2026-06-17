import os
import zipfile
import xml.etree.ElementTree as ET
from docx import Document as DocxDocument
from PyPDF2 import PdfReader
import markdown


def _read_file_safe(file_path: str) -> str:
    """安全读取文件，自动尝试多种编码"""
    encodings = ['utf-8', 'gbk', 'gb2312', 'gb18030', 'latin-1']
    for enc in encodings:
        try:
            with open(file_path, 'r', encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
        return f.read()


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
        content = _read_file_safe(file_path)
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
        return _read_file_safe(file_path).strip()
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
    elif ext == '.txt':
        return 'txt'
    elif ext == '.idml':
        return 'idml'
    return 'unknown'