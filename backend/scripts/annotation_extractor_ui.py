#!/usr/bin/env python3
"""Small Windows UI for extracting and merging manual review comments."""

import tkinter as tk
import threading
import os
from pathlib import Path
from tkinter import filedialog, messagebox
from tkinter import ttk


def default_output(mode):
    if mode == "merge":
        return "全部人工审核意见汇总.md"
    return "人工审核意见汇总.md"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("人工审核意见汇总工具")
        self.geometry("820x420")
        self.minsize(760, 380)
        self.resizable(True, True)

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
            filetypes=[("Markdown", "*.md")],
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

        worker = threading.Thread(target=self.run_worker, daemon=True)
        worker.start()

    def run_worker(self):
        try:
            try:
                from extract_pdf_annotations import extract_all, merge_markdown, to_markdown
            except ModuleNotFoundError as exc:
                missing = exc.name or str(exc)
                if missing == "fitz":
                    raise RuntimeError(
                        "缺少 PyMuPDF 依赖。\n\n"
                        "请在 PowerShell 中运行：\n"
                        "py -m pip install PyMuPDF\n\n"
                        "安装完成后重新双击打开 UI。"
                    ) from exc
                raise RuntimeError(f"缺少 Python 依赖：{missing}") from exc

            if self.mode.get() == "merge":
                rows = merge_markdown(self.input_path.get())
            else:
                rows = extract_all(self.input_path.get())
            output = Path(self.output_path.get())
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
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("启动失败", str(exc))
