#!/usr/bin/env pythonw
"""Windows no-console launcher for the annotation extractor UI."""

import tkinter as tk
from tkinter import messagebox

from annotation_extractor_ui import App


if __name__ == "__main__":
    try:
        App().mainloop()
    except Exception as exc:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("启动失败", str(exc))
