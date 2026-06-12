#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
外网准备脚本：下载所有离线安装包
在内网无法联网的机器上部署前，先在一台有外网的机器上运行此脚本

用法:
    python scripts/prepare_offline.py

输出:
    offline_bundle/
    ├── packages/          pip 离线包
    ├── playwright_cache/  Playwright 浏览器二进制缓存
    ├── scripts/
    │   ├── install_offline.py   内网安装脚本
    │   └── set_env.py           设置环境变量脚本
    └── README.md

然后将 offline_bundle 整个目录拷贝到内网机器运行 install_offline.py 即可
"""

import os
import sys
import shutil
import subprocess
import zipfile
import tempfile
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
BUNDLE_DIR = PROJECT_ROOT / "offline_bundle"
PACKAGES_DIR = BUNDLE_DIR / "packages"
PLAYWRIGHT_CACHE_DIR = BUNDLE_DIR / "playwright_cache"
SCRIPTS_DIR = BUNDLE_DIR / "scripts"

# 依赖列表（与 requirements.txt 保持一致）
REQUIREMENTS = [
    "playwright>=1.40.0",
    "python-dotenv>=1.0.0",
]


def run_cmd(cmd, cwd=None, check=True):
    """运行命令并输出"""
    print(f">>> {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if check and result.returncode != 0:
        raise RuntimeError(f"命令失败: {' '.join(cmd)} (exit {result.returncode})")
    return result


def step(title):
    """打印步骤标题"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def download_pip_packages():
    """步骤1: 下载 pip 离线包"""
    step("步骤 1/4: 下载 Python 依赖包")

    PACKAGES_DIR.mkdir(parents=True, exist_ok=True)

    # 先确保本机已安装这些包（用于 playwright install）
    print("\n[1.1] 确保外网机器已安装依赖...")
    for req in REQUIREMENTS:
        subprocess.run([sys.executable, "-m", "pip", "install", req], check=False)

    # 下载所有包（含依赖）到 packages 目录
    print("\n[1.2] 下载离线 wheel 包...")
    cmd = [
        sys.executable, "-m", "pip", "download",
        "--only-binary=:all:",
        "--dest", str(PACKAGES_DIR),
    ] + REQUIREMENTS
    run_cmd(cmd)

    # 额外下载 setuptools 和 wheel（某些环境可能需要）
    print("\n[1.3] 额外下载基础工具包...")
    run_cmd([
        sys.executable, "-m", "pip", "download",
        "--only-binary=:all:",
        "--dest", str(PACKAGES_DIR),
        "setuptools", "wheel", "pip",
    ], check=False)

    # 列出下载的包
    files = sorted(PACKAGES_DIR.glob("*"))
    print(f"\n已下载 {len(files)} 个包:")
    for f in files:
        size = f.stat().st_size / 1024 / 1024
        print(f"  {f.name} ({size:.1f} MB)")


def download_playwright_browsers():
    """步骤2: 下载 Playwright 浏览器"""
    step("步骤 2/4: 下载 Playwright 浏览器")

    # Playwright 缓存目录
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    if not local_appdata:
        local_appdata = Path.home() / "AppData" / "Local"
    src_cache = Path(local_appdata) / "ms-playwright"

    if not src_cache.exists():
        print(f"Playwright 缓存目录不存在: {src_cache}")
        print("先执行 playwright install 安装浏览器...")
        run_cmd([sys.executable, "-m", "playwright", "install", "chromium"])

    if not src_cache.exists():
        raise RuntimeError(f"无法找到 Playwright 缓存: {src_cache}")

    # 拷贝到离线包目录
    PLAYWRIGHT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\n从 {src_cache} 拷贝到 {PLAYWRIGHT_CACHE_DIR}")

    # 只拷贝 chromium 相关的目录（减小体积）
    chromium_dirs = [d for d in src_cache.iterdir() if d.is_dir() and "chromium" in d.name.lower()]
    if not chromium_dirs:
        print("未找到 chromium 目录，拷贝全部...")
        chromium_dirs = [d for d in src_cache.iterdir() if d.is_dir()]

    total_size = 0
    for src_dir in chromium_dirs:
        dst_dir = PLAYWRIGHT_CACHE_DIR / src_dir.name
        if dst_dir.exists():
            shutil.rmtree(dst_dir)
        print(f"  拷贝: {src_dir.name}")
        shutil.copytree(src_dir, dst_dir)
        size = sum(f.stat().st_size for f in dst_dir.rglob("*") if f.is_file()) / 1024 / 1024
        total_size += size
        print(f"    -> {size:.1f} MB")

    print(f"\nPlaywright 浏览器总计: {total_size:.1f} MB")


def copy_project_files():
    """步骤3: 拷贝项目源码"""
    step("步骤 3/4: 拷贝项目源码")

    # 拷贝核心文件
    files_to_copy = [
        "gui_recorder.py",
        "recorder_utils.py",
        "config.py",
        "requirements.txt",
        ".env.example",
        "README.md",
    ]

    for filename in files_to_copy:
        src = PROJECT_ROOT / filename
        if src.exists():
            dst = BUNDLE_DIR / filename
            shutil.copy2(src, dst)
            print(f"  已拷贝: {filename}")
        else:
            print(f"  跳过(不存在): {filename}")

    # 创建 recordings 目录
    (BUNDLE_DIR / "recordings").mkdir(exist_ok=True)
    print("  已创建: recordings/")


def generate_install_script():
    """步骤4: 生成内网安装脚本"""
    step("步骤 4/4: 生成内网安装脚本")

    SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

    # 安装脚本
    install_script = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
内网安装脚本
将 offline_bundle 目录拷贝到内网机器后，运行此脚本完成安装

用法:
    python scripts/install_offline.py
"""

import os
import sys
import shutil
import subprocess
import platform
from pathlib import Path

# 获取 offline_bundle 根目录
BUNDLE_DIR = Path(__file__).parent.parent.resolve()
PACKAGES_DIR = BUNDLE_DIR / "packages"
PLAYWRIGHT_CACHE_SRC = BUNDLE_DIR / "playwright_cache"


def run_cmd(cmd, check=True):
    print(f">>> {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if check and result.returncode != 0:
        print(f"警告: 命令返回非零退出码 {result.returncode}")
    return result


def check_python():
    print("=" * 60)
    print("  RPA 录制工具 - 内网离线安装")
    print("=" * 60)
    print(f"\\nPython: {sys.executable}")
    print(f"版本: {platform.python_version()}")
    print(f"平台: {platform.platform()}")

    if sys.version_info < (3, 8):
        print("\\n错误: 需要 Python 3.8 或更高版本")
        sys.exit(1)
    print("\\n[OK] Python 版本检查通过")


def install_pip_packages():
    print("\\n" + "=" * 60)
    print("步骤 1/3: 安装 Python 依赖包")
    print("=" * 60)

    if not PACKAGES_DIR.exists():
        print(f"错误: 未找到包目录 {PACKAGES_DIR}")
        sys.exit(1)

    cmd = [
        sys.executable, "-m", "pip", "install",
        "--no-index",
        "--find-links", str(PACKAGES_DIR),
        "-r", str(BUNDLE_DIR / "requirements.txt"),
    ]
    run_cmd(cmd)
    print("\\n[OK] 依赖包安装完成")


def install_playwright_browsers():
    print("\\n" + "=" * 60)
    print("步骤 2/3: 安装 Playwright 浏览器")
    print("=" * 60)

    if not PLAYWRIGHT_CACHE_SRC.exists():
        print("警告: 未找到预下载的浏览器缓存")
        print("将尝试使用系统已安装的 Chrome/Edge")
        return

    # 确定目标缓存目录
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    if not local_appdata:
        local_appdata = Path.home() / "AppData" / "Local"
    dst_cache = Path(local_appdata) / "ms-playwright"
    dst_cache.mkdir(parents=True, exist_ok=True)

    print(f"\\n目标缓存目录: {dst_cache}")
    print(f"源缓存目录: {PLAYWRIGHT_CACHE_SRC}")

    for src_dir in PLAYWRIGHT_CACHE_SRC.iterdir():
        if not src_dir.is_dir():
            continue
        dst_dir = dst_cache / src_dir.name
        if dst_dir.exists():
            print(f"\\n  已存在，跳过: {src_dir.name}")
            continue
        print(f"\\n  复制: {src_dir.name} ...")
        shutil.copytree(src_dir, dst_dir)
        print(f"    [OK] 完成")

    print("\\n[OK] Playwright 浏览器缓存部署完成")


def setup_env():
    print("\\n" + "=" * 60)
    print("步骤 3/3: 初始化配置文件")
    print("=" * 60)

    env_file = BUNDLE_DIR / ".env"
    env_example = BUNDLE_DIR / ".env.example"

    if env_file.exists():
        print(f"\\n.env 文件已存在: {env_file}")
    elif env_example.exists():
        shutil.copy2(env_example, env_file)
        print(f"\\n已从 .env.example 创建 .env")
    else:
        # 创建默认 .env
        env_content = """# RPA 录制工具配置文件
# 智慧运维平台账号
ZHYW_USERNAME=
ZHYW_PASSWORD=

# 浏览器路径（留空则自动检测）
BROWSER_PATH=

# 默认目标地址
DEFAULT_URL=https://www.zhyw.spic
"""
        env_file.write_text(env_content, encoding="utf-8")
        print(f"\\n已创建默认 .env 文件")

    print("\\n[提示] 请编辑 .env 文件填入用户名和密码")
    print(f"       文件位置: {env_file}")


def print_usage():
    print("\\n" + "=" * 60)
    print("安装完成！")
    print("=" * 60)
    print("\\n使用方法:")
    print(f"  cd {BUNDLE_DIR}")
    print("  python gui_recorder.py")
    print("\\n首次使用:")
    print("  1. 编辑 .env 文件填入账号密码")
    print("  2. 运行 python gui_recorder.py")
    print("  3. 输入目标地址，点击「开始录制」")
    print("\\n注意事项:")
    print("  - 内网环境使用本地 Chrome/Edge 浏览器")
    print("  - 自签名证书已配置忽略")
    print("  - 录制文件保存在 recordings/ 目录")
    print("=" * 60)


def main():
    check_python()
    install_pip_packages()
    install_playwright_browsers()
    setup_env()
    print_usage()
    input("\\n按回车键退出...")


if __name__ == "__main__":
    main()
'''

    install_path = SCRIPTS_DIR / "install_offline.py"
    install_path.write_text(install_script, encoding="utf-8")
    print(f"  已生成: {install_path}")

    # 快捷启动脚本（Windows）
    start_bat = BUNDLE_DIR / "启动录制工具.bat"
    bat_content = """@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================
echo   RPA 录制工具
echo ========================================
python gui_recorder.py
if errorlevel 1 (
    echo.
    echo [错误] 启动失败，请检查 Python 是否安装
    pause
)
"""
    start_bat.write_text(bat_content, encoding="utf-8")
    print(f"  已生成: {start_bat}")

    # 安装说明
    readme = BUNDLE_DIR / "README_OFFLINE.md"
    readme_content = """# RPA 录制工具 - 离线部署包

此目录包含所有内网部署所需的文件，**无需联网**即可完成安装。

## 目录说明

```
offline_bundle/
├── packages/              # Python 依赖包（wheel 格式）
├── playwright_cache/      # Playwright 浏览器二进制文件
├── scripts/
│   └── install_offline.py # 内网安装脚本
├── 启动录制工具.bat       # Windows 快捷启动
├── gui_recorder.py        # 主程序
├── recorder_utils.py      # 工具模块
├── config.py              # 配置模块
├── requirements.txt       # 依赖清单
├── .env.example           # 环境变量模板
└── README.md              # 原项目说明
```

## 内网安装步骤

### 前提条件

内网机器需要已安装 **Python 3.8+**（如果未安装，请联系管理员先安装 Python）

### 一键安装

1. 将此 `offline_bundle` 文件夹拷贝到内网机器任意位置
2. 打开命令提示符，进入该目录：
   ```cmd
   cd offline_bundle
   ```
3. 运行安装脚本：
   ```cmd
   python scripts/install_offline.py
   ```
4. 按提示完成安装

### 启动使用

安装完成后，双击运行 `启动录制工具.bat`，或执行：
```cmd
python gui_recorder.py
```

### 配置账号

首次使用前，编辑目录下的 `.env` 文件：
```
ZHYW_USERNAME=你的用户名
ZHYW_PASSWORD=你的密码
```

## 常见问题

### Q: 内网机器没有 Python 怎么办？
A: 需要管理员先在内网机器安装 Python 3.8+。如果无法安装，可以考虑在外网用 PyInstaller 将程序打包为 exe 可执行文件。

### Q: Playwright 浏览器提示未找到？
A: 内网环境会自动使用本地已安装的 Chrome 或 Edge，无需额外下载。如果报错，请确保内网机器已安装 Chrome 或 Edge。

### Q: 如何更新依赖？
A: 在外网机器重新运行 `python scripts/prepare_offline.py`，生成新的离线包后重新拷贝到内网。

---
由 RPA 录制工具自动生成
"""
    readme.write_text(readme_content, encoding="utf-8")
    print(f"  已生成: {readme}")


def print_summary():
    """打印汇总信息"""
    step("离线包准备完成")

    # 计算总大小
    total_size = 0
    for f in BUNDLE_DIR.rglob("*"):
        if f.is_file():
            total_size += f.stat().st_size

    print(f"""
离线包目录: {BUNDLE_DIR}
总大小: {total_size / 1024 / 1024:.1f} MB

部署步骤:
  1. 将整个 offline_bundle 目录拷贝到内网机器
  2. 在内网机器运行: python scripts/install_offline.py
  3. 安装完成后双击 "启动录制工具.bat"

文件清单:
""")
    for item in sorted(BUNDLE_DIR.iterdir()):
        if item.is_dir():
            size = sum(f.stat().st_size for f in item.rglob("*") if f.is_file()) / 1024 / 1024
            print(f"  [DIR] {item.name:20s} {size:8.1f} MB")
        else:
            size = item.stat().st_size / 1024 / 1024
            print(f"  [FILE] {item.name:19s} {size:8.1f} MB")

    print(f"""
提示:
  - 如果内网机器没有 Python，需要先安装 Python 3.8+
  - 如需打包为 exe，可在本机运行: pip install pyinstaller
    然后: pyinstaller --onefile gui_recorder.py
""")


def main():
    print("=" * 60)
    print("  RPA 录制工具 - 外网离线包准备脚本")
    print("=" * 60)
    print("\n此脚本将在外网机器上准备所有内网部署所需的文件\n")

    # 清理旧包
    if BUNDLE_DIR.exists():
        print("清理旧的离线包...")
        shutil.rmtree(BUNDLE_DIR)

    try:
        download_pip_packages()
        download_playwright_browsers()
        copy_project_files()
        generate_install_script()
        print_summary()
    except Exception as e:
        print(f"\n错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
