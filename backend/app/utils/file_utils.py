"""文件读取工具函数。"""

def read_file_safe(file_path: str) -> str:
    """安全读取文件，自动尝试 UTF-8 / GBK / GB2312 / GB18030 / latin-1 编码。"""
    encodings = ['utf-8', 'gbk', 'gb2312', 'gb18030', 'latin-1']
    for enc in encodings:
        try:
            with open(file_path, 'r', encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
        return f.read()
