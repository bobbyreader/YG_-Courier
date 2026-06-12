#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
内网 RPA 工单自动填写工具 - 现代化 GUI

用法:
    python gui.py
    或双击打包后的 exe
"""

import os
import sys
import threading
import tkinter as tk
from tkinter import scrolledtext, messagebox

from config import config
from rpa_bot import run_rpa


# ========== 配色方案 ==========
class Theme:
    BG = "#f0f2f5"           # 全局背景
    CARD = "#ffffff"        # 卡片背景
    PRIMARY = "#2563eb"     # 主按钮蓝
    PRIMARY_HOVER = "#1d4ed8"
    SECONDARY = "#64748b"   # 次要按钮灰
    SECONDARY_HOVER = "#475569"
    SUCCESS = "#10b981"     # 成功绿
    TEXT = "#1e293b"        # 主文字
    TEXT_LIGHT = "#64748b"  # 次要文字
    BORDER = "#e2e8f0"      # 边框
    INPUT_BG = "#f8fafc"    # 输入框背景
    LOG_BG = "#0f172a"      # 日志区背景
    LOG_FG = "#94a3b8"      # 日志文字
    ACCENT = "#3b82f6"      # 强调色


# ========== 工具函数 ==========

def _app_dir() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


# ========== 自定义组件 ==========

class RoundedButton(tk.Canvas):
    """圆角按钮（Canvas 绘制）"""
    def __init__(self, parent, text, command=None, width=120, height=38,
                 bg=Theme.PRIMARY, hover_bg=Theme.PRIMARY_HOVER,
                 fg="white", font=("微软雅黑", 10, "bold"), **kwargs):
        super().__init__(parent, width=width, height=height,
                         bg=parent["bg"], highlightthickness=0, **kwargs)
        self.command = command
        self.bg = bg
        self.hover_bg = hover_bg
        self.fg = fg
        self._text = text
        self._font = font
        self._radius = 8
        self._draw(bg)
        self.bind("<Enter>", lambda e: self._draw(self.hover_bg))
        self.bind("<Leave>", lambda e: self._draw(self.bg))
        self.bind("<Button-1>", self._on_click)

    def _draw(self, color):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 10:
            w, h = 120, 38
        r = self._radius
        self.create_oval(0, 0, r*2, r*2, fill=color, outline=color)
        self.create_oval(w-r*2, 0, w, r*2, fill=color, outline=color)
        self.create_oval(0, h-r*2, r*2, h, fill=color, outline=color)
        self.create_oval(w-r*2, h-r*2, w, h, fill=color, outline=color)
        self.create_rectangle(r, 0, w-r, h, fill=color, outline=color)
        self.create_rectangle(0, r, w, h-r, fill=color, outline=color)
        self.create_text(w//2, h//2, text=self._text, fill=self.fg,
                         font=self._font, anchor="center")

    def _on_click(self, event):
        if self.command:
            self.command()


class Card(tk.Frame):
    """圆角卡片容器"""
    def __init__(self, parent, title=None, **kwargs):
        super().__init__(parent, bg=Theme.CARD, **kwargs)
        self.configure(highlightbackground=Theme.BORDER,
                       highlightthickness=1,
                       bd=0)
        if title:
            self.title_label = tk.Label(self, text=title, bg=Theme.CARD,
                                        fg=Theme.TEXT, font=("微软雅黑", 11, "bold"))
            self.title_label.pack(anchor="w", padx=16, pady=(12, 8))


class StyledEntry(tk.Entry):
    """美化输入框"""
    def __init__(self, parent, show=None, width=35, **kwargs):
        super().__init__(parent, show=show, width=width,
                         font=("微软雅黑", 10),
                         bg=Theme.INPUT_BG, fg=Theme.TEXT,
                         highlightbackground=Theme.BORDER,
                         highlightcolor=Theme.ACCENT,
                         highlightthickness=1, bd=0,
                         insertbackground=Theme.TEXT, **kwargs)
        self.configure(relief="flat")


class StyledText(tk.Text):
    """美化文本框"""
    def __init__(self, parent, height=5, width=35, **kwargs):
        super().__init__(parent, height=height, width=width,
                         font=("微软雅黑", 10),
                         bg=Theme.INPUT_BG, fg=Theme.TEXT,
                         highlightbackground=Theme.BORDER,
                         highlightcolor=Theme.ACCENT,
                         highlightthickness=1, bd=0,
                         wrap="word", **kwargs)
        self.configure(relief="flat", padx=8, pady=6)


# ========== 主应用 ==========

class RpaGuiApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("内网RPA工单自动填写工具")
        self.root.geometry("720x780")
        self.root.resizable(False, False)
        self.root.configure(bg=Theme.BG)

        self.is_running = False
        self.bot = None
        self._build_ui()
        self._load_config()

    def _build_ui(self):
        # 顶部标题栏
        header = tk.Frame(self.root, bg=Theme.BG, height=60)
        header.pack(fill="x", padx=24, pady=(20, 10))
        header.pack_propagate(False)

        tk.Label(header, text="RPA", bg=Theme.BG, fg=Theme.PRIMARY,
                 font=("微软雅黑", 20, "bold")).pack(side="left")
        tk.Label(header, text="工单自动填写", bg=Theme.BG, fg=Theme.TEXT,
                 font=("微软雅黑", 16)).pack(side="left", padx=(6, 0))
        tk.Label(header, text="v1.0", bg=Theme.BG, fg=Theme.TEXT_LIGHT,
                 font=("微软雅黑", 9)).pack(side="left", padx=(8, 0), pady=(8, 0))

        # 主内容区（可滚动）
        canvas = tk.Canvas(self.root, bg=Theme.BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(self.root, orient="vertical", command=canvas.yview)
        self.main_frame = tk.Frame(canvas, bg=Theme.BG)
        self.main_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.main_frame, anchor="nw", width=672)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True, padx=24, pady=0)
        scrollbar.pack(side="right", fill="y")
        # 鼠标滚轮
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        pad = {"padx": 0, "pady": 10}

        # --- 账号配置卡片 ---
        cfg_card = Card(self.main_frame, title="账号配置")
        cfg_card.pack(fill="x", **pad)
        cfg_inner = tk.Frame(cfg_card, bg=Theme.CARD)
        cfg_inner.pack(fill="x", padx=16, pady=(0, 16))

        # 用户名
        row = tk.Frame(cfg_inner, bg=Theme.CARD)
        row.pack(fill="x", pady=6)
        tk.Label(row, text="用户名", bg=Theme.CARD, fg=Theme.TEXT,
                 font=("微软雅黑", 10), width=10, anchor="e").pack(side="left")
        self.entry_username = StyledEntry(row)
        self.entry_username.pack(side="left", padx=(10, 0))

        # 密码
        row = tk.Frame(cfg_inner, bg=Theme.CARD)
        row.pack(fill="x", pady=6)
        tk.Label(row, text="密  码", bg=Theme.CARD, fg=Theme.TEXT,
                 font=("微软雅黑", 10), width=10, anchor="e").pack(side="left")
        self.entry_password = StyledEntry(row, show="*")
        self.entry_password.pack(side="left", padx=(10, 0))

        # 浏览器路径
        row = tk.Frame(cfg_inner, bg=Theme.CARD)
        row.pack(fill="x", pady=6)
        tk.Label(row, text="浏览器", bg=Theme.CARD, fg=Theme.TEXT,
                 font=("微软雅黑", 10), width=10, anchor="e").pack(side="left")
        self.entry_browser = StyledEntry(row)
        self.entry_browser.pack(side="left", padx=(10, 0))
        tk.Label(row, text="可选，留空自动检测", bg=Theme.CARD, fg=Theme.TEXT_LIGHT,
                 font=("微软雅黑", 9)).pack(side="left", padx=(8, 0))

        # 保存按钮
        btn_row = tk.Frame(cfg_inner, bg=Theme.CARD)
        btn_row.pack(fill="x", pady=(8, 0))
        RoundedButton(btn_row, text="保存配置", command=self._save_config,
                      width=100, height=32,
                      bg=Theme.SECONDARY, hover_bg=Theme.SECONDARY_HOVER,
                      font=("微软雅黑", 10)).pack(side="left", padx=(100, 0))

        # --- 工单信息卡片 ---
        ticket_card = Card(self.main_frame, title="工单信息")
        ticket_card.pack(fill="x", **pad)
        ticket_inner = tk.Frame(ticket_card, bg=Theme.CARD)
        ticket_inner.pack(fill="x", padx=16, pady=(0, 16))

        # 流程类型
        row = tk.Frame(ticket_inner, bg=Theme.CARD)
        row.pack(fill="x", pady=6)
        tk.Label(row, text="流程类型", bg=Theme.CARD, fg=Theme.TEXT,
                 font=("微软雅黑", 10), width=10, anchor="e").pack(side="left")
        self.flow_display = tk.StringVar(value="用户支持")
        self.flow_map = {"用户支持": "support", "权限申请": "permission"}
        self.flow_menu = tk.OptionMenu(row, self.flow_display, *self.flow_map.keys())
        self.flow_menu.config(
            font=("微软雅黑", 10),
            bg=Theme.INPUT_BG, fg=Theme.TEXT,
            activebackground=Theme.ACCENT, activeforeground="white",
            highlightthickness=1, highlightbackground=Theme.BORDER,
            bd=0, relief="flat", width=20
        )
        self.flow_menu["menu"].config(
            font=("微软雅黑", 10),
            bg=Theme.INPUT_BG, fg=Theme.TEXT,
            activebackground=Theme.ACCENT, activeforeground="white"
        )
        self.flow_menu.pack(side="left", padx=(10, 0))

        # 受理人
        row = tk.Frame(ticket_inner, bg=Theme.CARD)
        row.pack(fill="x", pady=6)
        tk.Label(row, text="受理人", bg=Theme.CARD, fg=Theme.TEXT,
                 font=("微软雅黑", 10), width=10, anchor="e").pack(side="left")
        self.entry_assignee = StyledEntry(row)
        self.entry_assignee.pack(side="left", padx=(10, 0))
        tk.Label(row, text="同名自动匹配湖北公司", bg=Theme.CARD, fg=Theme.TEXT_LIGHT,
                 font=("微软雅黑", 9)).pack(side="left", padx=(8, 0))

        # 问题描述
        row = tk.Frame(ticket_inner, bg=Theme.CARD)
        row.pack(fill="x", pady=6)
        tk.Label(row, text="问题描述", bg=Theme.CARD, fg=Theme.TEXT,
                 font=("微软雅黑", 10), width=10, anchor="ne").pack(side="left")
        self.text_description = StyledText(row, height=5, width=35)
        self.text_description.pack(side="left", padx=(10, 0))
        tk.Label(row, text="直接粘贴即可", bg=Theme.CARD, fg=Theme.TEXT_LIGHT,
                 font=("微软雅黑", 9), anchor="nw").pack(side="left", padx=(8, 0))

        # 运行按钮
        btn_row = tk.Frame(ticket_inner, bg=Theme.CARD)
        btn_row.pack(fill="x", pady=(12, 0))
        self.btn_run = RoundedButton(btn_row, text="开始运行", command=self._on_run,
                                     width=140, height=42,
                                     bg=Theme.PRIMARY, hover_bg=Theme.PRIMARY_HOVER,
                                     font=("微软雅黑", 11, "bold"))
        self.btn_run.pack(side="left", padx=(100, 0))

        # --- 日志卡片 ---
        log_card = Card(self.main_frame, title="运行日志")
        log_card.pack(fill="x", **pad)
        log_inner = tk.Frame(log_card, bg=Theme.CARD)
        log_inner.pack(fill="x", padx=16, pady=(0, 16))

        self.log_box = scrolledtext.ScrolledText(
            log_inner,
            wrap="word",
            state="disabled",
            font=("JetBrains Mono", 10),
            bg=Theme.LOG_BG,
            fg=Theme.LOG_FG,
            insertbackground="white",
            height=12,
            bd=0,
            highlightthickness=1,
            highlightbackground=Theme.BORDER
        )
        self.log_box.pack(fill="both", expand=True)

    def _load_config(self):
        self.entry_username.insert(0, config.USERNAME)
        self.entry_password.insert(0, config.PASSWORD)
        self.entry_browser.insert(0, config.BROWSER_PATH)

        env_path = os.path.join(_app_dir(), ".env")
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("ZHYW_USERNAME="):
                        self.entry_username.delete(0, tk.END)
                        self.entry_username.insert(0, line.split("=", 1)[1])
                    elif line.startswith("ZHYW_PASSWORD="):
                        self.entry_password.delete(0, tk.END)
                        self.entry_password.insert(0, line.split("=", 1)[1])
                    elif line.startswith("BROWSER_PATH="):
                        self.entry_browser.delete(0, tk.END)
                        self.entry_browser.insert(0, line.split("=", 1)[1])

    def _save_config(self):
        username = self.entry_username.get().strip()
        password = self.entry_password.get().strip()
        browser = self.entry_browser.get().strip()

        if not username or not password:
            messagebox.showwarning("保存失败", "用户名和密码不能为空！")
            return

        env_path = os.path.join(_app_dir(), ".env")
        lines = [f"ZHYW_USERNAME={username}", f"ZHYW_PASSWORD={password}"]
        if browser:
            lines.append(f'BROWSER_PATH="{browser}"')

        with open(env_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        config.refresh()
        messagebox.showinfo("保存成功", "账号配置已保存")
        self._log("[GUI] 配置已保存")

    def _log(self, msg: str):
        def append():
            self.log_box.configure(state="normal")
            self.log_box.insert(tk.END, msg + "\n")
            self.log_box.see(tk.END)
            self.log_box.configure(state="disabled")
        self.root.after(0, append)

    def _on_run(self):
        if self.is_running:
            messagebox.showinfo("提示", "RPA 正在运行中，请等待...")
            return

        assignee = self.entry_assignee.get().strip()
        description = self.text_description.get("1.0", tk.END).strip()

        if not assignee:
            messagebox.showwarning("缺少信息", "请输入受理人姓名！")
            return
        if not description:
            messagebox.showwarning("缺少信息", "请输入问题描述！")
            return

        if not messagebox.askyesno("确认执行", f"受理人：{assignee}\n\n确认开始运行RPA？"):
            return

        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", tk.END)
        self.log_box.configure(state="disabled")
        self._log("[GUI] RPA 启动中...")

        self.is_running = True
        self.btn_run._text = "运行中..."
        self.btn_run._draw(Theme.PRIMARY)

        flow_type = self.flow_map[self.flow_display.get()]

        thread = threading.Thread(
            target=self._run_rpa_thread,
            args=(assignee, description, flow_type),
            daemon=True
        )
        thread.start()

    def _run_rpa_thread(self, assignee: str, description: str, flow_type: str):
        self.bot = None
        try:
            self.bot = run_rpa(assignee=assignee, description=description,
                               flow_type=flow_type, on_log=self._log)
        except Exception as e:
            self._log(f"[GUI] 异常: {e}")
        finally:
            self.is_running = False
            self.root.after(0, self._reset_run_button)
            if self.bot:
                self._log("[GUI] RPA 填写完成，等待人工审核...")
                self.root.after(0, self._prompt_close_browser)
            else:
                self._log("[GUI] RPA 已结束")

    def _reset_run_button(self):
        self.btn_run._text = "开始运行"
        self.btn_run._draw(Theme.PRIMARY)

    def _prompt_close_browser(self):
        messagebox.showinfo(
            "RPA 填写完成",
            "工单表单已自动填写完成！\n\n"
            "请在浏览器中人工审核并手动提交/保存。\n"
            "审核完成后点击确定关闭浏览器。"
        )
        if self.bot:
            self._log("[GUI] 正在关闭浏览器...")
            self.bot.close()
            self.bot = None
            self._log("[GUI] 浏览器已关闭")


def main():
    root = tk.Tk()
    app = RpaGuiApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
