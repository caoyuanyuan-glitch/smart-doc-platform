@echo off
setlocal
set "TMP_SCRIPT=%TEMP%\annotation_extractor_ui_%RANDOM%%RANDOM%.py"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$src = Get-Content -LiteralPath '%~f0' -Encoding UTF8; $marker = [Array]::IndexOf($src, '# __PYTHON__'); if ($marker -lt 0) { exit 2 }; $src[($marker + 1)..($src.Length - 1)] | Set-Content -LiteralPath '%TMP_SCRIPT%' -Encoding UTF8"
if errorlevel 1 goto extract_failed

where py.exe >nul 2>nul
if not errorlevel 1 (
    py.exe "%TMP_SCRIPT%"
    goto done
)

where python.exe >nul 2>nul
if not errorlevel 1 (
    python.exe "%TMP_SCRIPT%"
    goto done
)

echo Python was not found. Please install Python and try again.
pause
exit /b 1

:extract_failed
echo Failed to start annotation extractor.
echo Please send this window screenshot to the maintainer.
pause
exit /b 1

:done
set "EXIT_CODE=%ERRORLEVEL%"
del "%TMP_SCRIPT%" >nul 2>nul
if not "%EXIT_CODE%"=="0" pause
exit /b %EXIT_CODE%

# __PYTHON__
import json
import os
import re
import threading
import tkinter as tk
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def clean(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def has_comment(row):
    comment = clean(row.get("comment"))
    return bool(comment and comment != "-")


def input_files(path):
    path = Path(path)
    if path.is_dir():
        return sorted(
            file for file in path.rglob("*")
            if file.is_file() and file.suffix.lower() in {".pdf", ".docx"} and not file.name.startswith("~$")
        )
    return [path] if path.is_file() else []


def markdown_files(path):
    path = Path(path)
    if path.is_dir():
        return sorted(file for file in path.rglob("*.md") if file.is_file() and not file.name.startswith("~$"))
    return [path] if path.is_file() and path.suffix.lower() == ".md" else []


def extract_pdf(pdf):
    try:
        import fitz
    except ModuleNotFoundError as exc:
        raise RuntimeError("缺少 PyMuPDF 依赖。请在 PowerShell 中运行：py -m pip install PyMuPDF") from exc

    rows = []
    try:
        doc = fitz.open(pdf)
    except Exception as exc:
        raise RuntimeError(f"无法读取 PDF：{pdf}\n{exc}") from exc

    with doc:
        for page_no, page in enumerate(doc, start=1):
            annot = page.first_annot
            while annot:
                info = annot.info or {}
                rect = annot.rect
                rows.append({
                    "file": Path(pdf).name,
                    "page": page_no,
                    "type": annot.type[1],
                    "author": clean(info.get("title")),
                    "comment": clean(info.get("content")),
                    "selected": clean(page.get_textbox(rect)),
                    "context": clean(page.get_textbox(rect + (-90, -45, 180, 70))),
                })
                annot = annot.next
    return rows


def xml_text(node):
    if node is None:
        return ""
    return clean("".join(text.text or "" for text in node.findall(".//w:t", WORD_NS)))


def extract_docx(docx):
    rows = []
    try:
        archive = zipfile.ZipFile(docx)
    except zipfile.BadZipFile:
        return rows

    with archive:
        names = set(archive.namelist())
        if "word/comments.xml" not in names:
            return rows

        comments_root = ET.fromstring(archive.read("word/comments.xml"))
        comments = {}
        for comment in comments_root.findall("w:comment", WORD_NS):
            comment_id = comment.attrib.get(f"{{{WORD_NS['w']}}}id", "")
            comments[comment_id] = {
                "author": comment.attrib.get(f"{{{WORD_NS['w']}}}author", ""),
                "comment": xml_text(comment),
            }

        selected_by_id = {}
        if "word/document.xml" in names:
            document_root = ET.fromstring(archive.read("word/document.xml"))
            active_id = None
            parts = []
            for elem in document_root.iter():
                tag = elem.tag.rsplit("}", 1)[-1]
                if tag == "commentRangeStart":
                    active_id = elem.attrib.get(f"{{{WORD_NS['w']}}}id", "")
                    parts = []
                elif tag == "t" and active_id is not None:
                    parts.append(elem.text or "")
                elif tag == "commentRangeEnd":
                    end_id = elem.attrib.get(f"{{{WORD_NS['w']}}}id", "")
                    if active_id == end_id:
                        selected_by_id[active_id] = clean("".join(parts))
                        active_id = None
                        parts = []

        for comment_id, data in comments.items():
            selected = selected_by_id.get(comment_id, "")
            rows.append({
                "file": Path(docx).name,
                "page": "-",
                "type": "WordComment",
                "author": clean(data.get("author")),
                "comment": clean(data.get("comment")),
                "selected": selected,
                "context": selected,
            })
    return rows


def extract_all(input_path):
    rows = []
    for file in input_files(input_path):
        if file.suffix.lower() == ".pdf":
            rows.extend(extract_pdf(file))
        elif file.suffix.lower() == ".docx":
            rows.extend(extract_docx(file))
    return [row for row in rows if has_comment(row)]


def parse_bullet(block, label):
    match = re.search(rf"^- {re.escape(label)}: (.*)$", block, flags=re.MULTILINE)
    return clean(match.group(1)) if match else ""


def parse_markdown_file(md_file):
    text = Path(md_file).read_text(encoding="utf-8-sig")
    rows = []
    blocks = re.split(r"(?=^## \d+\. )", text, flags=re.MULTILINE)
    for block in blocks:
        header = re.search(r"^## \d+\. (.*?) · 第 (.*?) 页", block, flags=re.MULTILINE)
        if not header:
            continue
        row = {
            "file": clean(header.group(1)),
            "page": clean(header.group(2)),
            "type": parse_bullet(block, "批注类型"),
            "author": parse_bullet(block, "批注人"),
            "comment": parse_bullet(block, "人工意见"),
            "selected": parse_bullet(block, "选中文本"),
            "context": parse_bullet(block, "附近正文"),
        }
        if has_comment(row):
            rows.append(row)
    return rows


def merge_markdown(input_path):
    rows = []
    for md_file in markdown_files(input_path):
        rows.extend(parse_markdown_file(md_file))
    return rows


def to_markdown(rows):
    lines = ["# 人工审核 PDF 和 Word 批注汇总", ""]
    for i, row in enumerate(rows, start=1):
        lines += [
            f"## {i}. {row['file']} · 第 {row['page']} 页",
            "",
            f"- 批注类型: {row['type']}",
            f"- 批注人: {row['author'] or '-'}",
            f"- 人工意见: {row['comment'] or '-'}",
            f"- 选中文本: {row['selected'] or '-'}",
            f"- 附近正文: {row['context'] or '-'}",
            "- 知识库整理:",
            "  - 类别: [待归类]",
            "  - 触发条件: [待补充]",
            "  - 例外条件: [待补充]",
            "  - 修改建议: [待补充]",
            "",
        ]
    return "\n".join(lines)


def default_output(mode):
    return "全部人工审核意见汇总.md" if mode == "merge" else "人工审核意见汇总.md"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("人工审核意见汇总工具")
        self.geometry("820x420")
        self.minsize(760, 380)
        self.mode = tk.StringVar(value="extract")
        self.input_path = tk.StringVar(value=str(Path.cwd()))
        self.output_path = tk.StringVar(value=str(Path.cwd() / default_output("extract")))
        self.status = tk.StringVar(value="选择输入后点击开始。")
        self.is_running = False
        self.protocol("WM_DELETE_WINDOW", self.close_window)
        self.build()

    def build(self):
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)

        mode_frame = ttk.LabelFrame(frame, text="模式", padding=10)
        mode_frame.pack(fill="x")
        ttk.Radiobutton(mode_frame, text="提取 PDF/Word 批注", variable=self.mode, value="extract", command=self.refresh_output).pack(side="left", padx=(0, 24))
        ttk.Radiobutton(mode_frame, text="合并多个 Markdown", variable=self.mode, value="merge", command=self.refresh_output).pack(side="left")

        input_frame = ttk.LabelFrame(frame, text="输入", padding=10)
        input_frame.pack(fill="x", pady=(14, 0))
        ttk.Entry(input_frame, textvariable=self.input_path).pack(fill="x", expand=True)
        input_buttons = ttk.Frame(input_frame)
        input_buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(input_buttons, text="选择文件夹", command=self.choose_input_folder).pack(side="left", padx=(0, 8))
        ttk.Button(input_buttons, text="选择单个文件", command=self.choose_input_file).pack(side="left")

        output_frame = ttk.LabelFrame(frame, text="输出", padding=10)
        output_frame.pack(fill="x", pady=(14, 0))
        ttk.Entry(output_frame, textvariable=self.output_path).pack(fill="x", expand=True)
        ttk.Button(output_frame, text="保存为", command=self.choose_output).pack(anchor="w", pady=(8, 0))

        action_frame = ttk.Frame(frame)
        action_frame.pack(fill="x", pady=(20, 0))
        self.run_button = ttk.Button(action_frame, text="开始汇总", command=self.run)
        self.run_button.pack(side="left", ipadx=28, ipady=8)
        ttk.Label(action_frame, textvariable=self.status, anchor="w").pack(side="left", fill="x", expand=True, padx=(16, 0))
        self.progress = ttk.Progressbar(frame, mode="indeterminate")
        self.progress.pack(fill="x", pady=(14, 0))

    def refresh_output(self):
        base = Path(self.input_path.get())
        folder = base if base.is_dir() else base.parent
        self.output_path.set(str(folder / default_output(self.mode.get())))

    def choose_input_folder(self):
        selected = filedialog.askdirectory(initialdir=self.input_path.get() or str(Path.cwd()))
        if selected:
            self.input_path.set(selected)
            self.refresh_output()

    def choose_input_file(self):
        selected = filedialog.askopenfilename(
            initialdir=self.input_path.get() or str(Path.cwd()),
            filetypes=[("Supported files", "*.pdf *.docx *.md"), ("All files", "*.*")],
        )
        if selected:
            self.input_path.set(selected)
            self.refresh_output()

    def choose_output(self):
        selected = filedialog.asksaveasfilename(
            initialfile=Path(self.output_path.get()).name,
            defaultextension=".md",
            filetypes=[("Markdown", "*.md"), ("JSON", "*.json")],
        )
        if selected:
            self.output_path.set(selected)

    def run(self):
        if self.is_running:
            return
        self.is_running = True
        self.run_button.configure(state="disabled", text="正在汇总...")
        self.status.set("正在处理，请稍候。文件较多时可能需要几分钟。")
        self.progress.start(12)
        threading.Thread(target=self.run_worker, daemon=True).start()

    def run_worker(self):
        try:
            rows = merge_markdown(self.input_path.get()) if self.mode.get() == "merge" else extract_all(self.input_path.get())
            output = Path(self.output_path.get())
            if output.suffix.lower() == ".json":
                output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
            else:
                output.write_text(to_markdown(rows), encoding="utf-8")
            self.after(0, self.finish_success, len(rows), output)
        except Exception as exc:
            self.after(0, self.finish_error, str(exc))

    def finish_success(self, count, output):
        self.progress.stop()
        self.run_button.configure(state="normal", text="开始汇总")
        self.is_running = False
        self.status.set(f"完成：{count} 条批注 -> {output}")
        messagebox.showinfo("完成", f"已生成 {count} 条批注。\n\n{output}")

    def finish_error(self, error):
        self.progress.stop()
        self.run_button.configure(state="normal", text="开始汇总")
        self.is_running = False
        self.status.set("运行失败，请查看弹窗错误。")
        messagebox.showerror("运行失败", error)

    def close_window(self):
        if self.is_running:
            should_close = messagebox.askyesno("确认关闭", "当前仍在处理文件。确定要退出吗？")
            if should_close:
                os._exit(0)
            return
        self.destroy()


if __name__ == "__main__":
    try:
        App().mainloop()
    except Exception as exc:
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("启动失败", str(exc))
        except Exception:
            print(f"启动失败: {exc}")
            raise
