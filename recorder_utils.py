"""
RPA 录制工具辅助模块
提供浏览器检测、codegen 调用、MD 导出等功能
"""

import os
import sys
import subprocess
import winreg
import glob
import datetime
from pathlib import Path
from typing import Optional, Dict, List


def _get_codegen_executable() -> str:
    """获取可用于执行 playwright codegen 的可执行文件路径。
    在 PyInstaller 打包环境下，使用内嵌的 codegen_helper.exe。
    在源码环境下，使用当前 Python 解释器。"""
    if getattr(sys, "frozen", False):
        # PyInstaller 打包环境：使用内嵌的 codegen_helper.exe
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            helper = Path(meipass) / "codegen_helper.exe"
            if helper.exists():
                return str(helper)
            # 兼容旧版本或不同打包方式
            helper = Path(meipass) / "codegen_helper" / "codegen_helper.exe"
            if helper.exists():
                return str(helper)
        # 尝试 exe 同级目录
        exe_dir = Path(sys.executable).parent
        for candidate in [
            exe_dir / "codegen_helper.exe",
            exe_dir / "codegen_helper",
        ]:
            if candidate.exists():
                return str(candidate)
        # 如果都找不到，fallback 到系统 PATH
        return "codegen_helper.exe"
    # 源码环境：使用当前 Python 解释器
    return sys.executable


# ========== 浏览器自动检测 ==========

def _find_browser_from_registry(browser_name: str, reg_path: str) -> Optional[str]:
    """从注册表查找浏览器安装路径"""
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path) as key:
            path, _ = winreg.QueryValueEx(key, "")
            if path and os.path.isfile(path):
                return path
    except Exception:
        pass
    return None


def _find_browser_from_common_paths(exe_name: str) -> Optional[str]:
    """从常见安装目录查找浏览器"""
    program_files = [
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        os.environ.get("LOCALAPPDATA", r""),
    ]
    patterns = [
        f"Google\\Chrome\\Application\\{exe_name}",
        f"Microsoft\\Edge\\Application\\{exe_name}",
    ]
    for base in program_files:
        if not base:
            continue
        for pattern in patterns:
            full = os.path.join(base, pattern)
            if os.path.isfile(full):
                return full
    return None


def find_local_browser(prefer: str = "auto") -> Optional[str]:
    """
    自动检测 Windows 本地已安装的 Chrome 或 Edge。
    prefer: "auto" | "chrome" | "edge"
    """
    candidates = []
    if prefer in ("auto", "chrome"):
        candidates.append(
            ("chrome.exe", r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe")
        )
    if prefer in ("auto", "edge"):
        candidates.append(
            ("msedge.exe", r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe")
        )
    if prefer == "auto":
        # 如果上面只加了一个，把另一个也加上
        if len(candidates) == 1:
            if candidates[0][0] == "chrome.exe":
                candidates.append(
                    ("msedge.exe", r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe")
                )
            else:
                candidates.insert(
                    0,
                    ("chrome.exe", r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe")
                )

    for exe_name, reg_path in candidates:
        path = _find_browser_from_registry(exe_name, reg_path)
        if path:
            return path
        path = _find_browser_from_common_paths(exe_name)
        if path:
            return path
    return None


def get_browser_name(path: str) -> str:
    """根据路径判断浏览器名称"""
    lower = path.lower()
    if "chrome" in lower:
        return "Chrome"
    if "edge" in lower or "msedge" in lower:
        return "Edge"
    return "Unknown"


def get_browser_channel(path: str) -> Optional[str]:
    """根据路径返回 playwright --channel 参数值"""
    lower = path.lower()
    if "chrome" in lower:
        return "chrome"
    if "edge" in lower or "msedge" in lower:
        return "msedge"
    return None


# ========== 配置管理 ==========

ENV_PATH = Path(__file__).parent / ".env"

DEFAULT_ENV = """# RPA 录制工具配置文件
# 智慧运维平台账号
ZHYW_USERNAME=
ZHYW_PASSWORD=

# 浏览器路径（留空则自动检测）
# 示例: BROWSER_PATH=C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe
BROWSER_PATH=

# 默认目标地址
DEFAULT_URL=https://www.zhyw.spic
"""


def ensure_env_exists():
    """确保 .env 文件存在"""
    if not ENV_PATH.exists():
        ENV_PATH.write_text(DEFAULT_ENV, encoding="utf-8")


def load_env_dict() -> Dict[str, str]:
    """读取 .env 文件为字典"""
    ensure_env_exists()
    result = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                result[key.strip()] = value.strip()
    return result


def save_env_dict(data: Dict[str, str]):
    """保存字典到 .env 文件，保留注释"""
    lines = []
    existing = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                lines.append(line)
                continue
            if "=" in stripped:
                key, _ = stripped.split("=", 1)
                key = key.strip()
                if key in data:
                    lines.append(f"{key}={data[key]}")
                    existing[key] = True
                else:
                    lines.append(line)
    # 添加新增项
    for key, value in data.items():
        if key not in existing:
            lines.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ========== Codegen 录制 ==========

OUTPUT_DIR = Path(__file__).parent / "recordings"


def get_output_py_path(name: Optional[str] = None) -> Path:
    """生成输出文件路径"""
    OUTPUT_DIR.mkdir(exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    if name:
        filename = f"{name}_{timestamp}.py"
    else:
        filename = f"recording_{timestamp}.py"
    return OUTPUT_DIR / filename


def build_codegen_cmd(url: str, output_py: Path, browser_path: Optional[str] = None) -> List[str]:
    """构建 playwright codegen 命令"""
    codegen_exe = _get_codegen_executable()

    if getattr(sys, "frozen", False):
        # PyInstaller 打包环境：使用 codegen_helper.exe
        # codegen_helper 的用法：codegen_helper.exe codegen [options] URL
        cmd = [
            codegen_exe,
            "codegen",
            "--target", "python",
            "--ignore-https-errors",
            "-o", str(output_py),
        ]
    else:
        # 源码环境：使用 python -m playwright
        cmd = [
            codegen_exe, "-m", "playwright", "codegen",
            "--target", "python",
            "--ignore-https-errors",
            "-o", str(output_py),
        ]

    if browser_path:
        channel = get_browser_channel(browser_path)
        if channel:
            cmd.extend(["--channel", channel])
        else:
            cmd.extend(["--browser", "chromium"])
    cmd.append(url)
    return cmd


def run_codegen(url: str, output_py: Path, browser_path: Optional[str] = None) -> subprocess.Popen:
    """启动 codegen 子进程"""
    cmd = build_codegen_cmd(url, output_py, browser_path)
    env = os.environ.copy()
    # 如果指定了浏览器路径且 --channel 无法匹配，通过环境变量告知 playwright
    if browser_path and not get_browser_channel(browser_path):
        env["PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH"] = browser_path
    return subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0,
    )


def find_latest_recording() -> Optional[Path]:
    """查找最新的录制文件"""
    if not OUTPUT_DIR.exists():
        return None
    files = list(OUTPUT_DIR.glob("*.py"))
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


# ========== MD 导出 ==========

MD_TEMPLATE = """# RPA 录制脚本

## 录制信息

| 项目 | 内容 |
|------|------|
| 录制时间 | {timestamp} |
| 目标地址 | {url} |
| 使用浏览器 | {browser} |
| 浏览器路径 | {browser_path} |
| 脚本文件 | `{py_file}` |

## 使用说明

### 1. 环境准备

确保已安装依赖：

```bash
pip install playwright python-dotenv
playwright install chromium
```

### 2. 配置账号

在项目目录下创建 `.env` 文件，填入：

```
ZHYW_USERNAME=你的用户名
ZHYW_PASSWORD=你的密码
```

### 3. 运行脚本

```bash
python {py_file}
```

### 4. 脚本说明

- 脚本使用 Playwright 录制生成
- 可直接运行，也可作为基础进行二次开发
- 建议在内网环境中使用本地 Chrome/Edge 浏览器

## 生成的代码

```python
{code}
```

## 内网部署建议

1. **浏览器**：使用内网机器已安装的 Chrome 或 Edge，无需额外下载
2. **依赖**：只需 `pip install playwright`，无需 `playwright install`（因为使用本地浏览器）
3. **配置**：将 `.env` 文件与脚本一起分发，由使用方填写账号
4. **证书**：如目标网站使用自签名证书，代码中已配置 `ignore_https_errors=True`

---
*由 RPA 录制工具自动生成*
"""


def export_to_md(py_file: Path, url: str, browser_path: Optional[str], md_file: Path) -> str:
    """将录制脚本导出为 Markdown"""
    code = py_file.read_text(encoding="utf-8")
    browser_name = get_browser_name(browser_path) if browser_path else "自动检测"
    timestamp = datetime.datetime.fromtimestamp(py_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")

    md_content = MD_TEMPLATE.format(
        timestamp=timestamp,
        url=url,
        browser=browser_name,
        browser_path=browser_path or "自动检测",
        py_file=py_file.name,
        code=code,
    )
    md_file.write_text(md_content, encoding="utf-8")
    return md_content
