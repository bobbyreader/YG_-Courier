#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
构建脚本：在有网的机器上运行，生成内网可直接使用的便携包

用法:
    python build.py

输出:
    dist/hzrpa/ 文件夹，复制到内网解压即用
"""

import os
import shutil
import subprocess
import sys


def run(cmd, **kwargs):
    """执行命令并检查返回值"""
    print(f">>> {' '.join(cmd)}")
    result = subprocess.run(cmd, **kwargs)
    if result.returncode != 0:
        print(f"命令失败: {' '.join(cmd)}")
        sys.exit(1)
    return result


def check_pyinstaller():
    """检查并安装 PyInstaller"""
    try:
        import PyInstaller
        print("[Build] PyInstaller 已安装")
    except ImportError:
        print("[Build] 正在安装 PyInstaller...")
        run([sys.executable, "-m", "pip", "install", "pyinstaller"])


def build_exe():
    """用 PyInstaller 打包"""
    print("\n[Build] 开始打包 exe...")
    
    # 清理旧构建
    for d in ["build", "dist"]:
        if os.path.exists(d):
            shutil.rmtree(d)
    
    # PyInstaller 参数
    # --onedir: 生成文件夹（适合放浏览器，比单文件启动快）
    # --noconsole: 不弹黑窗口（调试用可去掉）
    sep = ";" if sys.platform == "win32" else ":"
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onedir",
        "--noconsole",
        f"--add-data=.env.example{sep}.",
        f"--add-data=config.py{sep}.",
        f"--add-data=rpa_bot.py{sep}.",
        "--name", "hzrpa",
        "gui.py"
    ]
    run(cmd)
    print("[Build] exe 打包完成")


def copy_playwright_browsers():
    """复制 Playwright 浏览器到输出目录（确保内网机器无需安装即可运行）"""
    print("\n[Build] 正在复制 Chromium 浏览器...")

    src = os.path.expandvars(r"%LOCALAPPDATA%\ms-playwright")
    dst = os.path.join("dist", "hzrpa", "playwright")

    if not os.path.exists(src):
        print(f"[Build] 警告: 未找到浏览器缓存目录: {src}")
        print("[Build] 请先运行: playwright install chromium")
        sys.exit(1)

    os.makedirs(dst, exist_ok=True)
    for item in os.listdir(src):
        if "chromium" in item.lower():
            src_path = os.path.join(src, item)
            dst_path = os.path.join(dst, item)
            if os.path.isdir(src_path):
                print(f"[Build] 复制: {item}")
                shutil.copytree(src_path, dst_path, dirs_exist_ok=True)

    print(f"[Build] 浏览器已复制到: {dst}")


def create_launcher():
    """生成启动脚本"""
    print("\n[Build] 生成启动脚本...")

    bat_content = """@echo off
chcp 65001 >nul
echo ==========================================
echo   内网 RPA 工单自动填写工具
echo ==========================================
echo.

if not exist .env (
    copy .env.example .env >nul 2>&1
)

echo [启动] 正在运行 RPA...
hzrpa.exe
echo.
echo [完成] 程序已退出。
pause
"""

    dst_dir = os.path.join("dist", "hzrpa")
    with open(os.path.join(dst_dir, "启动.bat"), "w", encoding="utf-8") as f:
        f.write(bat_content)

    readme = """内网 RPA 工单自动填写工具
==================================

环境要求
--------
- Windows 系统

1. 配置账号（首次使用）
   编辑 .env 文件，填入用户名和密码：
   ZHYW_USERNAME=你的用户名
   ZHYW_PASSWORD=你的密码

   如果浏览器检测不到，可手动指定路径：
   BROWSER_PATH="C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"

2. 运行
   双击 "启动.bat"

3. 使用流程
   - 在 GUI 界面中填写账号信息，点击"保存配置"
   - 选择流程类型（用户支持 / 权限申请）
   - 输入受理人姓名
   - 粘贴问题描述
   - 点击"开始运行"
   - 浏览器自动打开并填写工单
   - 在浏览器中人工审核并手动提交/保存
   - 审核完成后回到 GUI 点击确定关闭浏览器

注意事项
--------
- 本工具为离线便携包，无需安装 Python
- 首次使用请务必配置 .env 文件
- 如遇到证书错误，已自动忽略，无需处理
- 自带 Chromium 浏览器（优先调用系统 Chrome/Edge）
- 同名受理人会自动匹配路径含"湖北公司"的人员
"""
    with open(os.path.join(dst_dir, "使用说明.txt"), "w", encoding="utf-8") as f:
        f.write(readme)

    print("[Build] 启动脚本和使用说明已生成")


def show_result():
    """显示构建结果"""
    dst = os.path.abspath(os.path.join("dist", "hzrpa"))
    size = sum(
        os.path.getsize(os.path.join(dirpath, f))
        for dirpath, _, filenames in os.walk(dst)
        for f in filenames
    )
    size_mb = size / (1024 * 1024)

    print("\n" + "=" * 50)
    print("[Build] 构建完成！")
    print("=" * 50)
    print(f"输出目录: {dst}")
    print(f"总大小:   {size_mb:.1f} MB")
    print(f"\n使用步骤:")
    print(f"  1. 将整个 'hzrpa' 文件夹复制到内网机器")
    print(f"  2. 编辑 .env 文件填入账号密码")
    print(f"  3. 双击 '启动.bat' 运行")
    print("=" * 50)


def main():
    print("=" * 50)
    print("内网 RPA 便携包构建工具")
    print("=" * 50)

    check_pyinstaller()
    build_exe()
    copy_playwright_browsers()
    create_launcher()
    show_result()


if __name__ == "__main__":
    main()
