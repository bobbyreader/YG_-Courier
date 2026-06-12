#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RPA 录制工具 GUI
功能：
1. 输入页面地址，调用 playwright codegen 录制
2. 人工手动操作结束后，导出为 MD 格式
3. 支持 env 配置保存用户名密码
4. 自动检测并调用本地 Chrome/Edge 浏览器
5. 执行录制的脚本，支持参数化和自动登录
"""

import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox, simpledialog
from pathlib import Path
from typing import Optional, Dict, List

from recorder_utils import (
    find_local_browser,
    get_browser_name,
    load_env_dict,
    save_env_dict,
    get_output_py_path,
    run_codegen,
    find_latest_recording,
    export_to_md,
    ensure_env_exists,
    OUTPUT_DIR,
)
from rpa_executor import (
    extract_params_from_script,
    execute_script,
    list_recordings,
)


class RpaRecorderGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("RPA 录制工具 v2.0")
        self.root.geometry("1100x850")
        self.root.minsize(1000, 750)

        # 状态变量
        self.codegen_process: Optional[object] = None
        self.executor_process: Optional[object] = None
        self.current_output_py: Optional[Path] = None
        self.current_url: str = ""
        self.current_browser_path: Optional[str] = None
        self.selected_script: Optional[Path] = None
        self.script_params: Dict[str, Dict] = {}

        # 确保 .env 存在
        ensure_env_exists()

        self._build_ui()
        self._load_config()
        self._detect_browser()
        self._refresh_script_list()

    def _build_ui(self):
        """构建界面"""
        # 主容器
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # ===== 系统配置区 =====
        config_frame = ttk.LabelFrame(main_frame, text="系统配置", padding="10")
        config_frame.pack(fill=tk.X, pady=(0, 10))

        # 用户名
        ttk.Label(config_frame, text="用户名:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.entry_username = ttk.Entry(config_frame, width=30)
        self.entry_username.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)

        # 密码
        ttk.Label(config_frame, text="密码:").grid(row=0, column=2, sticky=tk.W, padx=5, pady=5)
        self.entry_password = ttk.Entry(config_frame, width=30, show="*")
        self.entry_password.grid(row=0, column=3, sticky=tk.W, padx=5, pady=5)

        # 浏览器选择
        ttk.Label(config_frame, text="浏览器:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.browser_var = tk.StringVar(value="auto")
        browser_combo = ttk.Combobox(
            config_frame,
            textvariable=self.browser_var,
            values=["auto", "chrome", "edge", "manual"],
            width=15,
            state="readonly",
        )
        browser_combo.grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)
        browser_combo.bind("<<ComboboxSelected>>", self._on_browser_change)

        # 浏览器路径
        self.entry_browser_path = ttk.Entry(config_frame, width=45)
        self.entry_browser_path.grid(row=1, column=2, columnspan=2, sticky=tk.EW, padx=5, pady=5)
        self.btn_browse = ttk.Button(config_frame, text="浏览...", command=self._browse_browser)
        self.btn_browse.grid(row=1, column=4, padx=5, pady=5)

        # 保存配置按钮
        self.btn_save_config = ttk.Button(config_frame, text="保存配置", command=self._save_config)
        self.btn_save_config.grid(row=2, column=0, columnspan=5, pady=10)

        config_frame.columnconfigure(2, weight=1)

        # ===== 标签页 =====
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # ---- 录制标签页 ----
        self.record_tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.record_tab, text="录制")
        self._build_record_tab()

        # ---- 执行标签页 ----
        self.exec_tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.exec_tab, text="执行脚本")
        self._build_exec_tab()

        # 状态栏
        self.status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(fill=tk.X, pady=(5, 0))

    # ========== 录制标签页 ==========

    def _build_record_tab(self):
        """构建录制标签页"""
        tab = self.record_tab

        # 录制配置区
        record_frame = ttk.LabelFrame(tab, text="录制配置", padding="10")
        record_frame.pack(fill=tk.X, pady=(0, 10))

        # 目标地址
        ttk.Label(record_frame, text="目标地址:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.entry_url = ttk.Entry(record_frame, width=70)
        self.entry_url.grid(row=0, column=1, columnspan=3, sticky=tk.EW, padx=5, pady=5)
        self.entry_url.insert(0, "https://www.zhyw.spic")

        # 输出名称
        ttk.Label(record_frame, text="输出名称:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.entry_name = ttk.Entry(record_frame, width=40)
        self.entry_name.grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)
        ttk.Label(record_frame, text="(留空使用时间戳)").grid(row=1, column=2, sticky=tk.W, padx=5, pady=5)

        # 按钮区
        btn_frame = ttk.Frame(record_frame)
        btn_frame.grid(row=2, column=0, columnspan=4, pady=10)

        self.btn_start = ttk.Button(btn_frame, text="开始录制", command=self._start_recording, width=15)
        self.btn_start.pack(side=tk.LEFT, padx=5)

        self.btn_stop = ttk.Button(btn_frame, text="停止录制", command=self._stop_recording, width=15, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=5)

        self.btn_export = ttk.Button(btn_frame, text="导出 MD", command=self._export_md, width=15)
        self.btn_export.pack(side=tk.LEFT, padx=5)

        self.btn_open_dir = ttk.Button(btn_frame, text="打开录制目录", command=self._open_recordings_dir, width=15)
        self.btn_open_dir.pack(side=tk.LEFT, padx=5)

        record_frame.columnconfigure(1, weight=1)

        # 日志输出区
        log_frame = ttk.LabelFrame(tab, text="录制日志", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            wrap=tk.WORD,
            state=tk.DISABLED,
            font=("Consolas", 10),
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

    # ========== 执行标签页 ==========

    def _build_exec_tab(self):
        """构建执行标签页"""
        tab = self.exec_tab

        # 上部：脚本列表 + 参数配置
        top_frame = ttk.Frame(tab)
        top_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # 左：脚本列表
        list_frame = ttk.LabelFrame(top_frame, text="脚本列表", padding="5")
        list_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Treeview
        cols = ("name", "size", "mtime")
        self.script_tree = ttk.Treeview(list_frame, columns=cols, show="headings", height=8)
        self.script_tree.heading("name", text="文件名")
        self.script_tree.heading("size", text="大小")
        self.script_tree.heading("mtime", text="修改时间")
        self.script_tree.column("name", width=250)
        self.script_tree.column("size", width=80)
        self.script_tree.column("mtime", width=140)
        self.script_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.script_tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.script_tree.configure(yscrollcommand=scrollbar.set)

        self.script_tree.bind("<<TreeviewSelect>>", self._on_script_select)

        # 右：参数配置
        param_frame = ttk.LabelFrame(top_frame, text="参数配置", padding="10")
        param_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(10, 0))

        # 自动登录开关
        self.auto_login_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            param_frame,
            text="自动登录（使用 .env 中的账号密码）",
            variable=self.auto_login_var,
        ).pack(anchor=tk.W, pady=(0, 10))

        # 登录地址
        login_frame = ttk.Frame(param_frame)
        login_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(login_frame, text="登录地址:").pack(side=tk.LEFT)
        self.entry_login_url = ttk.Entry(login_frame, width=50)
        self.entry_login_url.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))
        self.entry_login_url.insert(0, "https://www.zhyw.spic")

        # 替换硬编码账号
        self.replace_creds_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            param_frame,
            text="替换脚本中的硬编码账号（使用 .env 中的用户名/密码）",
            variable=self.replace_creds_var,
        ).pack(anchor=tk.W, pady=(0, 5))

        # 执行后暂停
        self.pause_after_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            param_frame,
            text="执行后暂停，按回车键关闭浏览器",
            variable=self.pause_after_var,
        ).pack(anchor=tk.W, pady=(0, 10))

        # 参数表格
        ttk.Label(param_frame, text="脚本参数（双击修改值）:").pack(anchor=tk.W, pady=(0, 5))

        param_table_frame = ttk.Frame(param_frame)
        param_table_frame.pack(fill=tk.BOTH, expand=True)

        cols2 = ("param_name", "original", "value")
        self.param_tree = ttk.Treeview(param_table_frame, columns=cols2, show="headings", height=6)
        self.param_tree.heading("param_name", text="参数名")
        self.param_tree.heading("original", text="原始值")
        self.param_tree.heading("value", text="替换值")
        self.param_tree.column("param_name", width=150)
        self.param_tree.column("original", width=200)
        self.param_tree.column("value", width=200)
        self.param_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar2 = ttk.Scrollbar(param_table_frame, orient=tk.VERTICAL, command=self.param_tree.yview)
        scrollbar2.pack(side=tk.RIGHT, fill=tk.Y)
        self.param_tree.configure(yscrollcommand=scrollbar2.set)

        self.param_tree.bind("<Double-1>", self._on_param_edit)

        # 操作按钮
        btn_frame2 = ttk.Frame(param_frame)
        btn_frame2.pack(fill=tk.X, pady=(10, 0))

        self.btn_refresh_scripts = ttk.Button(btn_frame2, text="刷新列表", command=self._refresh_script_list, width=12)
        self.btn_refresh_scripts.pack(side=tk.LEFT, padx=5)

        self.btn_analyze_params = ttk.Button(btn_frame2, text="分析参数", command=self._analyze_params, width=12)
        self.btn_analyze_params.pack(side=tk.LEFT, padx=5)

        self.btn_run_script = ttk.Button(btn_frame2, text="执行脚本", command=self._run_script, width=12)
        self.btn_run_script.pack(side=tk.LEFT, padx=5)

        self.btn_stop_script = ttk.Button(btn_frame2, text="停止执行", command=self._stop_script, width=12, state=tk.DISABLED)
        self.btn_stop_script.pack(side=tk.LEFT, padx=5)

        # 下部：脚本预览 + 执行日志
        bottom_frame = ttk.Frame(tab)
        bottom_frame.pack(fill=tk.BOTH, expand=True)

        # 左：脚本预览
        preview_frame = ttk.LabelFrame(bottom_frame, text="脚本预览", padding="5")
        preview_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.preview_text = scrolledtext.ScrolledText(
            preview_frame,
            wrap=tk.NONE,
            state=tk.DISABLED,
            font=("Consolas", 9),
            height=12,
        )
        self.preview_text.pack(fill=tk.BOTH, expand=True)

        # 右：执行日志
        exec_log_frame = ttk.LabelFrame(bottom_frame, text="执行日志", padding="5")
        exec_log_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(10, 0))

        self.exec_log_text = scrolledtext.ScrolledText(
            exec_log_frame,
            wrap=tk.WORD,
            state=tk.DISABLED,
            font=("Consolas", 9),
            height=12,
        )
        self.exec_log_text.pack(fill=tk.BOTH, expand=True)

    # ========== 公共方法 ==========

    def _log(self, msg: str, widget=None):
        """输出日志到文本框"""
        widget = widget or self.log_text
        widget.configure(state=tk.NORMAL)
        widget.insert(tk.END, f"{msg}\n")
        widget.see(tk.END)
        widget.configure(state=tk.DISABLED)

    def _load_config(self):
        """加载配置到界面"""
        env = load_env_dict()
        self.entry_username.insert(0, env.get("ZHYW_USERNAME", ""))
        self.entry_password.insert(0, env.get("ZHYW_PASSWORD", ""))
        browser_path = env.get("BROWSER_PATH", "")
        if browser_path:
            self.entry_browser_path.delete(0, tk.END)
            self.entry_browser_path.insert(0, browser_path)
            lower = browser_path.lower()
            if "chrome" in lower:
                self.browser_var.set("chrome")
            elif "edge" in lower or "msedge" in lower:
                self.browser_var.set("edge")
            else:
                self.browser_var.set("manual")
        self._log("配置已加载")

    def _detect_browser(self):
        """自动检测浏览器"""
        prefer = self.browser_var.get()
        if prefer == "manual":
            return
        path = find_local_browser(prefer if prefer != "auto" else "auto")
        if path:
            self.current_browser_path = path
            name = get_browser_name(path)
            self._log(f"检测到浏览器: {name} -> {path}")
            if not self.entry_browser_path.get():
                self.entry_browser_path.delete(0, tk.END)
                self.entry_browser_path.insert(0, path)
        else:
            self._log("未检测到 Chrome/Edge，请手动指定")

    def _on_browser_change(self, event=None):
        """浏览器选择变更"""
        mode = self.browser_var.get()
        if mode == "manual":
            self.entry_browser_path.configure(state=tk.NORMAL)
            self.btn_browse.configure(state=tk.NORMAL)
        else:
            self.entry_browser_path.configure(state=tk.NORMAL)
            self.btn_browse.configure(state=tk.NORMAL)
            self._detect_browser()

    def _browse_browser(self):
        """浏览选择浏览器"""
        path = filedialog.askopenfilename(
            title="选择浏览器可执行文件",
            filetypes=[("可执行文件", "*.exe"), ("所有文件", "*.*")],
        )
        if path:
            self.entry_browser_path.delete(0, tk.END)
            self.entry_browser_path.insert(0, path)
            self.browser_var.set("manual")

    def _save_config(self):
        """保存配置到 .env"""
        data = {
            "ZHYW_USERNAME": self.entry_username.get(),
            "ZHYW_PASSWORD": self.entry_password.get(),
            "BROWSER_PATH": self.entry_browser_path.get(),
        }
        save_env_dict(data)
        self._log("配置已保存到 .env")
        self.status_var.set("配置已保存")
        messagebox.showinfo("保存成功", "配置已保存到 .env 文件")

    # ========== 录制功能 ==========

    def _start_recording(self):
        """开始录制"""
        url = self.entry_url.get().strip()
        if not url:
            messagebox.showwarning("提示", "请输入目标地址")
            return

        browser_path = self.entry_browser_path.get().strip()
        if not browser_path or not os.path.isfile(browser_path):
            prefer = self.browser_var.get()
            if prefer == "manual":
                messagebox.showerror("错误", "未找到浏览器，请手动指定路径")
                return
            detected = find_local_browser(prefer if prefer != "auto" else "auto")
            if not detected:
                messagebox.showerror("错误", "未检测到 Chrome/Edge 浏览器，请手动指定")
                return
            browser_path = detected
            self.entry_browser_path.delete(0, tk.END)
            self.entry_browser_path.insert(0, browser_path)

        name = self.entry_name.get().strip()
        output_py = get_output_py_path(name if name else None)
        self.current_output_py = output_py
        self.current_url = url
        self.current_browser_path = browser_path

        self._log("=" * 50)
        self._log(f"开始录制...")
        self._log(f"目标地址: {url}")
        self._log(f"浏览器: {get_browser_name(browser_path)} ({browser_path})")
        self._log(f"输出文件: {output_py}")
        self._log("提示: 请在弹出的浏览器中完成操作，完成后点击 [停止录制]")
        self._log("=" * 50)

        self.status_var.set("录制中...")
        self.btn_start.configure(state=tk.DISABLED)
        self.btn_stop.configure(state=tk.NORMAL)
        self.btn_export.configure(state=tk.DISABLED)

        def read_stdout(proc):
            try:
                for line in iter(proc.stdout.readline, ""):
                    if not line:
                        break
                    self.root.after(0, lambda l=line.strip(): self._log(f"[codegen] {l}"))
            except Exception:
                pass

        def run():
            try:
                self.codegen_process = run_codegen(url, output_py, browser_path)
                threading.Thread(target=read_stdout, args=(self.codegen_process,), daemon=True).start()
                self.codegen_process.wait()
                self.root.after(0, self._on_codegen_finished)
            except Exception as e:
                self.root.after(0, lambda: self._on_codegen_error(str(e)))

        threading.Thread(target=run, daemon=True).start()

    def _stop_recording(self):
        """停止录制"""
        if self.codegen_process and self.codegen_process.poll() is None:
            self._log("正在停止录制...")
            self.codegen_process.terminate()
            try:
                self.codegen_process.wait(timeout=5)
            except Exception:
                self.codegen_process.kill()
                self.codegen_process.wait()
            self._log("录制已停止")
        else:
            self._log("录制进程已结束或未启动")
        self._on_codegen_finished()

    def _on_codegen_finished(self):
        """录制结束回调"""
        self.status_var.set("录制完成")
        self.btn_start.configure(state=tk.NORMAL)
        self.btn_stop.configure(state=tk.DISABLED)
        self.btn_export.configure(state=tk.NORMAL)

        if self.current_output_py and self.current_output_py.exists():
            size = self.current_output_py.stat().st_size
            self._log(f"录制文件已生成: {self.current_output_py.name} ({size} bytes)")
        else:
            latest = find_latest_recording()
            if latest:
                self.current_output_py = latest
                self._log(f"找到最新录制文件: {latest.name}")

        # 刷新执行标签页的脚本列表
        self._refresh_script_list()

    def _on_codegen_error(self, error: str):
        """录制错误回调"""
        self._log(f"录制出错: {error}")
        self.status_var.set("录制出错")
        self.btn_start.configure(state=tk.NORMAL)
        self.btn_stop.configure(state=tk.DISABLED)

    def _export_md(self):
        """导出 MD"""
        py_file = self.current_output_py
        if not py_file or not py_file.exists():
            py_file = find_latest_recording()
            if not py_file:
                messagebox.showwarning("提示", "未找到录制文件，请先进行录制")
                return
            self.current_output_py = py_file

        url = self.current_url or self.entry_url.get().strip()
        browser_path = self.current_browser_path or self.entry_browser_path.get().strip()

        md_path = py_file.with_suffix(".md")
        try:
            export_to_md(py_file, url, browser_path, md_path)
            self._log(f"MD 已导出: {md_path}")
            self.status_var.set(f"MD 已导出: {md_path.name}")
            if messagebox.askyesno("导出成功", f"MD 已导出到:\n{md_path}\n\n是否打开文件所在目录？"):
                os.startfile(md_path.parent)
        except Exception as e:
            messagebox.showerror("导出失败", str(e))
            self._log(f"导出失败: {e}")

    def _open_recordings_dir(self):
        """打开录制目录"""
        OUTPUT_DIR.mkdir(exist_ok=True)
        os.startfile(OUTPUT_DIR)

    # ========== 执行功能 ==========

    def _refresh_script_list(self):
        """刷新脚本列表"""
        for item in self.script_tree.get_children():
            self.script_tree.delete(item)

        recordings = list_recordings(OUTPUT_DIR)
        for rec in recordings:
            size_kb = rec["size"] / 1024
            size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb / 1024:.1f} MB"
            self.script_tree.insert(
                "",
                tk.END,
                values=(rec["name"], size_str, rec["mtime"]),
                tags=(str(rec["path"]),),
            )

        if recordings:
            self._log(f"脚本列表已刷新，共 {len(recordings)} 个脚本", self.exec_log_text)
        else:
            self._log("脚本列表为空，请先录制脚本", self.exec_log_text)

    def _on_script_select(self, event=None):
        """选择脚本"""
        selection = self.script_tree.selection()
        if not selection:
            return

        item = self.script_tree.item(selection[0])
        path_str = item["tags"][0] if item["tags"] else None
        if not path_str:
            return

        self.selected_script = Path(path_str)
        self._log(f"已选择脚本: {self.selected_script.name}", self.exec_log_text)

        # 显示预览
        try:
            content = self.selected_script.read_text(encoding="utf-8")
            self.preview_text.configure(state=tk.NORMAL)
            self.preview_text.delete("1.0", tk.END)
            self.preview_text.insert(tk.END, content)
            self.preview_text.configure(state=tk.DISABLED)
        except Exception as e:
            self._log(f"读取脚本失败: {e}", self.exec_log_text)

        # 自动分析参数
        self._analyze_params()

    def _analyze_params(self):
        """分析脚本参数"""
        if not self.selected_script or not self.selected_script.exists():
            messagebox.showwarning("提示", "请先选择一个脚本")
            return

        try:
            content = self.selected_script.read_text(encoding="utf-8")
            params = extract_params_from_script(content)

            # 清空参数表格
            for item in self.param_tree.get_children():
                self.param_tree.delete(item)

            self.script_params = {}
            for p in params:
                name = p["name"]
                original = p["value"]
                self.script_params[name] = {"original": original, "value": original, "info": p}
                self.param_tree.insert(
                    "",
                    tk.END,
                    values=(name, original, original),
                )

            self._log(f"参数分析完成，共 {len(params)} 个参数", self.exec_log_text)
        except Exception as e:
            self._log(f"参数分析失败: {e}", self.exec_log_text)

    def _on_param_edit(self, event=None):
        """双击编辑参数值"""
        selection = self.param_tree.selection()
        if not selection:
            return

        item = self.param_tree.item(selection[0])
        values = item["values"]
        if not values:
            return

        param_name = values[0]
        original = values[1]

        # 弹出输入框
        new_value = simpledialog.askstring(
            "修改参数",
            f"参数: {param_name}\n原始值: {original}\n\n请输入新值:",
            initialvalue=values[2],
        )
        if new_value is not None:
            self.param_tree.item(selection[0], values=(param_name, original, new_value))
            if param_name in self.script_params:
                self.script_params[param_name]["value"] = new_value
            self._log(f"参数 '{param_name}' 已修改为: {new_value}", self.exec_log_text)

    def _run_script(self):
        """执行脚本"""
        if not self.selected_script or not self.selected_script.exists():
            messagebox.showwarning("提示", "请先选择一个脚本")
            return

        # 收集参数
        params = {}
        for item_id in self.param_tree.get_children():
            values = self.param_tree.item(item_id)["values"]
            if len(values) >= 3:
                name = values[0]
                original = values[1]
                value = values[2]
                if value != original:
                    params[original] = value

        auto_login = self.auto_login_var.get()
        login_url = self.entry_login_url.get().strip() if auto_login else None
        replace_creds = self.replace_creds_var.get()
        pause_after = self.pause_after_var.get()

        self._log("=" * 50, self.exec_log_text)
        self._log(f"开始执行脚本: {self.selected_script.name}", self.exec_log_text)
        if params:
            self._log(f"参数替换: {params}", self.exec_log_text)
        if auto_login:
            self._log(f"自动登录: {login_url}", self.exec_log_text)
        if replace_creds:
            self._log("替换硬编码账号: 已启用", self.exec_log_text)
        if pause_after:
            self._log("执行后暂停: 已启用", self.exec_log_text)
        self._log("=" * 50, self.exec_log_text)

        self.status_var.set("执行中...")
        self.btn_run_script.configure(state=tk.DISABLED)
        self.btn_stop_script.configure(state=tk.NORMAL)

        def on_output(line):
            self.root.after(0, lambda: self._log(line, self.exec_log_text))

        def on_finish(returncode):
            self.root.after(0, lambda: self._on_script_finished(returncode))

        try:
            self.executor_process = execute_script(
                self.selected_script,
                params=params or None,
                auto_login=auto_login,
                login_url=login_url,
                replace_credentials=replace_creds,
                pause_after_exec=pause_after,
                on_output=on_output,
                on_finish=on_finish,
            )
        except Exception as e:
            self._log(f"执行失败: {e}", self.exec_log_text)
            self._on_script_finished(-1)

    def _stop_script(self):
        """停止执行"""
        if self.executor_process and self.executor_process.poll() is None:
            self._log("正在停止执行...", self.exec_log_text)
            self.executor_process.terminate()
            try:
                self.executor_process.wait(timeout=5)
            except Exception:
                self.executor_process.kill()
                self.executor_process.wait()
            self._log("执行已停止", self.exec_log_text)
        self._on_script_finished(-1)

    def _on_script_finished(self, returncode: int):
        """脚本执行结束回调"""
        if returncode == 0:
            self._log("[OK] 脚本执行完成", self.exec_log_text)
            self.status_var.set("执行完成")
        else:
            self._log(f"[ERR] 脚本执行结束，返回码: {returncode}", self.exec_log_text)
            self.status_var.set("执行结束")

        self.btn_run_script.configure(state=tk.NORMAL)
        self.btn_stop_script.configure(state=tk.DISABLED)


def main():
    root = tk.Tk()
    app = RpaRecorderGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
