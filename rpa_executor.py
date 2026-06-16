"""
RPA 执行引擎
功能：
1. 加载录制的脚本
2. 自动注入登录逻辑
3. 支持参数化替换
4. 执行并实时输出日志
"""

import os
import sys
import re
import tempfile
import subprocess
import threading
import datetime
from pathlib import Path
from typing import Optional, Dict, List, Callable


# ========== 参数解析 ==========

def extract_params_from_script(script_content: str) -> List[Dict[str, str]]:
    """
    从录制脚本中提取可参数化的值。
    策略：提取 fill/locator 中的字符串常量作为候选参数。
    返回: [{"name": "参数名", "value": "原始值", "line": 行号}]
    """
    params = []
    seen = set()

    # 匹配 page.fill("selector", "value") 中的 value
    fill_pattern = re.compile(
        r'page\.fill\s*\(\s*["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)["\']\s*\)',
        re.MULTILINE
    )
    # 匹配 locator.fill("value")
    locator_fill_pattern = re.compile(
        r'\.fill\s*\(\s*["\']([^"\']+)["\']\s*\)',
        re.MULTILINE
    )
    # 匹配 type 操作
    type_pattern = re.compile(
        r'\.type\s*\(\s*["\']([^"\']+)["\']\s*\)',
        re.MULTILINE
    )

    for i, line in enumerate(script_content.splitlines(), 1):
        # fill 的双参数形式
        for m in fill_pattern.finditer(line):
            selector, value = m.group(1), m.group(2)
            # 过滤掉常见的非参数值（URL、选择器本身等）
            if _is_param_candidate(value):
                key = f"fill_{_sanitize_key(selector)}"
                if key not in seen:
                    seen.add(key)
                    params.append({"name": key, "value": value, "line": i, "type": "fill"})

        # locator fill
        for m in locator_fill_pattern.finditer(line):
            value = m.group(1)
            if _is_param_candidate(value):
                key = f"input_{_sanitize_key(value)[:30]}"
                if key not in seen:
                    seen.add(key)
                    params.append({"name": key, "value": value, "line": i, "type": "fill"})

        # type
        for m in type_pattern.finditer(line):
            value = m.group(1)
            if _is_param_candidate(value):
                key = f"type_{_sanitize_key(value)[:30]}"
                if key not in seen:
                    seen.add(key)
                    params.append({"name": key, "value": value, "line": i, "type": "type"})

    return params


def _is_param_candidate(value: str) -> bool:
    """判断一个字符串值是否适合作为参数"""
    if not value or len(value) < 2:
        return False
    # 排除 URL
    if value.startswith("http") or value.startswith("/") or value.startswith("./"):
        return False
    # 排除纯数字（可能是索引）
    if value.isdigit():
        return False
    # 排除常见的 CSS 选择器片段
    if value in ("button", "input", "div", "span", "a", "form", "li", "ul", "table", "tr", "td"):
        return False
    # 排除看起来像选择器的值
    if any(c in value for c in "[]#.=>"):
        return False
    return True


def _sanitize_key(text: str) -> str:
    """将文本转换为合法的变量名"""
    text = re.sub(r'[^\w\u4e00-\u9fff]', '_', text)
    text = re.sub(r'_+', '_', text)
    return text.strip('_')[:50]


# ========== 登录逻辑注入 ==========

LOGIN_HEADER_TEMPLATE = '''
# ==================== 自动注入的登录逻辑 ====================
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

USERNAME = os.environ.get("ZHYW_USERNAME", "")
PASSWORD = os.environ.get("ZHYW_PASSWORD", "")

# 参数化变量映射
PARAMS = {params_dict!r}

def _replace_params(text):
    """替换参数化变量"""
    if text in PARAMS:
        return PARAMS[text]
    return text

# ==================== 原始录制脚本（已参数化） ====================
'''


def inject_login_and_params(script_content: str, params: Dict[str, str]) -> str:
    """
    向脚本注入登录逻辑和参数化支持。
    返回修改后的完整脚本内容。
    """
    # 构建参数字典（value -> 替换值）
    params_dict = {}
    for name, info in params.items():
        original_value = info["original"]
        new_value = info.get("value", original_value)
        params_dict[original_value] = new_value

    # 替换脚本中的参数值
    modified_content = script_content
    for original_value, new_value in params_dict.items():
        # 只替换 fill/locator 中的值，不替换选择器
        # 使用正则精确替换
        escaped = re.escape(original_value)
        # 替换 fill("selector", "value") 中的 value
        modified_content = re.sub(
            rf'(fill\s*\(\s*["\'][^"\']+["\']\s*,\s*"){escaped}(")',
            rf'\g<1>{new_value}\g<2>',
            modified_content
        )
        # 替换 locator.fill("value") 中的 value
        modified_content = re.sub(
            rf'((?:locator|get_by)[^)]*\.fill\s*\(\s*"){escaped}(")',
            rf'\g<1>{new_value}\g<2>',
            modified_content
        )

    # 注入头部
    header = LOGIN_HEADER_TEMPLATE.format(params_dict=params_dict)
    # 如果脚本已有 import playwright，我们在它前面插入
    if "from playwright.sync_api" in modified_content:
        parts = modified_content.split("from playwright.sync_api", 1)
        modified_content = parts[0] + header + "\nfrom playwright.sync_api" + parts[1]
    elif "import " in modified_content:
        # 在第一个 import 前插入
        idx = modified_content.find("import ")
        modified_content = modified_content[:idx] + header + "\n" + modified_content[idx:]
    else:
        modified_content = header + "\n" + modified_content

    return modified_content


# ========== 辅助功能 ==========

def replace_hardcoded_credentials(script_content: str, env_username: str, env_password: str) -> str:
    """
    替换脚本中的硬编码用户名和密码为 .env 中的值。
    识别 name="用户名" 或 name="密码" 后面的 .fill() 值。
    """
    if not env_username and not env_password:
        return script_content

    # 查找 name="用户名" ... .fill("value") 模式
    username_pattern = re.compile(
        r'(name\s*=\s*["\']用户名["\'][^)]*\.fill\s*\(\s*["\'])([^"\']+)(["\']\s*\))',
        re.DOTALL,
    )
    password_pattern = re.compile(
        r'(name\s*=\s*["\']密码["\'][^)]*\.fill\s*\(\s*["\'])([^"\']+)(["\']\s*\))',
        re.DOTALL,
    )

    replaced = script_content
    if env_username:
        replaced, count = username_pattern.subn(rf'\g<1>{env_username}\g<3>', replaced)
        if count:
            print(f"[RPA] 替换用户名: {count} 处")

    if env_password:
        replaced, count = password_pattern.subn(rf'\g<1>{env_password}\g<3>', replaced)
        if count:
            print(f"[RPA] 替换密码: {count} 处")

    return replaced


def inject_pause_before_close(script_content: str) -> str:
    """
    在执行结束前注入暂停代码，按回车后再关闭浏览器。
    """
    pause_code = '\n    input("\\n[RPA] 执行完成，按回车键关闭浏览器...")\n'

    # 找到 browser.close() 的位置，在它前面插入暂停
    if "browser.close()" in script_content:
        # 获取 browser.close() 所在行的缩进
        lines = script_content.splitlines()
        for i, line in enumerate(lines):
            if "browser.close()" in line:
                indent = _get_line_indent(line)
                pause_line = indent + 'input("[RPA] 执行完成，按回车键关闭浏览器...")'
                lines.insert(i, pause_line)
                break
        script_content = "\n".join(lines)
    else:
        # 兜底：在文件末尾追加
        script_content += '\ninput("[RPA] 执行完成，按回车键关闭浏览器...")\n'

    return script_content


# ========== 脚本执行 ==========

def execute_script(
    script_path: Path,
    params: Optional[Dict[str, str]] = None,
    auto_login: bool = False,
    login_url: Optional[str] = None,
    replace_credentials: bool = False,
    pause_after_exec: bool = False,
    on_output: Optional[Callable[[str], None]] = None,
    on_finish: Optional[Callable[[int], None]] = None,
) -> subprocess.Popen:
    """
    执行录制脚本。

    Args:
        script_path: 录制的 .py 脚本路径
        params: 参数化替换值 {原始值: 替换值}
        auto_login: 是否在执行前自动登录
        login_url: 登录页面地址
        replace_credentials: 是否替换脚本中的硬编码账号为 .env 的值
        pause_after_exec: 执行后是否暂停，按回车关闭浏览器
        on_output: 输出回调函数
        on_finish: 结束回调函数 (returncode)

    Returns:
        subprocess.Popen 对象
    """
    script_content = script_path.read_text(encoding="utf-8")

    # 加载 .env 中的账号密码
    env_username = ""
    env_password = ""
    try:
        from dotenv import load_dotenv
        env_path = script_path.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
        env_username = os.environ.get("ZHYW_USERNAME", "")
        env_password = os.environ.get("ZHYW_PASSWORD", "")
    except Exception:
        pass

    # 参数化替换
    if params:
        def escape_python_string_value(value: str, quote: str) -> str:
            return value.replace("\\", "\\\\").replace(quote, f"\\{quote}")

        sorted_params = sorted(params.items(), key=lambda kv: len(kv[0]), reverse=True)
        for original, new_val in sorted_params:
            escaped_orig = re.escape(original)

            def replace_with_double_quotes(match):
                escaped_new = escape_python_string_value(new_val, '"')
                return f'{match.group(1)}"{escaped_new}"{match.group(2)}'

            def replace_with_single_quotes(match):
                escaped_new = escape_python_string_value(new_val, "'")
                return f"{match.group(1)}'{escaped_new}'{match.group(2)}"

            script_content = re.sub(
                rf'(fill\s*\(\s*["\'][^"\']*["\']\s*,\s*)"{escaped_orig}"(\s*\))',
                replace_with_double_quotes,
                script_content,
            )
            script_content = re.sub(
                rf"(fill\s*\(\s*['\"][^'\"]*['\"]\s*,\s*)'{escaped_orig}'(\s*\))",
                replace_with_single_quotes,
                script_content,
            )
            for method in ("fill", "type"):
                script_content = re.sub(
                    rf'((?:get_by|locator|page)\S*\.{method}\s*\(\s*)"{escaped_orig}"(\s*\))',
                    replace_with_double_quotes,
                    script_content,
                )
                script_content = re.sub(
                    rf"((?:get_by|locator|page)\S*\.{method}\s*\(\s*)'{escaped_orig}'(\s*\))",
                    replace_with_single_quotes,
                    script_content,
                )

    # 替换硬编码账号
    if replace_credentials and (env_username or env_password):
        script_content = replace_hardcoded_credentials(script_content, env_username, env_password)

    # 自动登录注入
    if auto_login and login_url:
        script_content = _inject_login(script_content, login_url)

    # 执行后暂停注入
    if pause_after_exec:
        script_content = inject_pause_before_close(script_content)

    # 写入临时文件
    temp_dir = Path(tempfile.gettempdir()) / "rpa_executor"
    temp_dir.mkdir(exist_ok=True)
    temp_script = temp_dir / f"rpa_run_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.py"
    temp_script.write_text(script_content, encoding="utf-8")

    # 输出临时脚本路径供调试
    if on_output:
        on_output(f"[RPA] 临时脚本: {temp_script}")

    # 设置环境变量
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    # 启动子进程
    proc = subprocess.Popen(
        [sys.executable, str(temp_script)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        cwd=str(script_path.parent),
    )

    # 读取输出
    def read_output():
        try:
            for line in iter(proc.stdout.readline, ""):
                if not line:
                    break
                if on_output:
                    on_output(line.rstrip())
        except Exception as e:
            if on_output:
                on_output(f"[RPA] 读取输出出错: {e}")
        finally:
            proc.wait()
            if on_finish:
                on_finish(proc.returncode)

    threading.Thread(target=read_output, daemon=True).start()
    return proc


def _get_line_indent(line: str) -> str:
    """获取一行的缩进空格数"""
    stripped = line.lstrip()
    if not stripped:
        return ""
    return line[:len(line) - len(stripped)]


def _inject_login(script_content: str, login_url: str) -> str:
    """向脚本注入自动登录逻辑。确保注入代码的缩进与上下文一致。"""

    # 生成登录代码的核心逻辑（不带缩进）
    login_body_lines = [
        "# ==================== 自动登录注入 ====================",
        "import os",
        "from dotenv import load_dotenv",
        "",
        "_env_path = os.path.join(os.path.dirname(__file__), '.env')",
        "if os.path.exists(_env_path):",
        "    load_dotenv(_env_path)",
        "",
        "_LOGIN_USERNAME = os.environ.get('ZHYW_USERNAME', '')",
        "_LOGIN_PASSWORD = os.environ.get('ZHYW_PASSWORD', '')",
        "",
        "if _LOGIN_USERNAME and _LOGIN_PASSWORD:",
        "    # 尝试自动登录",
        "    try:",
        f'        page.goto("{login_url}")',
        "        page.wait_for_load_state('networkidle')",
        "        # 常见登录字段尝试",
        """        for selector in ['input[name="username"]', 'input[name="userName"]', 'input[id="username"]', '#username', 'input[type="text"]']:""",
        "            try:",
        "                page.fill(selector, _LOGIN_USERNAME)",
        "                break",
        "            except:",
        "                continue",
        """        for selector in ['input[name="password"]', 'input[name="passWord"]', 'input[id="password"]', '#password', 'input[type="password"]']:""",
        "            try:",
        "                page.fill(selector, _LOGIN_PASSWORD)",
        "                break",
        "            except:",
        "                continue",
        """        for selector in ['button[type="submit"]', 'input[type="submit"]', 'button:has-text("登录")', 'button:has-text("Login")', '.login-btn']:""",
        "            try:",
        "                page.click(selector)",
        "                break",
        "            except:",
        "                continue",
        "        page.wait_for_load_state('networkidle')",
        "        print('[RPA] 自动登录完成')",
        "    except Exception as e:",
        "        print(f'[RPA] 自动登录失败: {e}')",
        "# ==================== 原始脚本继续 ====================",
    ]

    def apply_indent(lines: list, indent: str) -> list:
        """给代码块增加缩进，跳过空行"""
        result = []
        for l in lines:
            if not l.strip():
                result.append(l)
            else:
                result.append(indent + l)
        return result

    # 查找插入点：page = context.new_page()
    marker = "page = context.new_page()"
    if marker in script_content:
        parts = script_content.split(marker, 1)
        # 获取 marker 所在行的缩进
        before_lines = parts[0].splitlines()
        if before_lines:
            indent = _get_line_indent(before_lines[-1])
        else:
            indent = ""
        login_code = "\n".join(apply_indent(login_body_lines, indent))
        script_content = parts[0] + marker + "\n" + login_code + "\n" + parts[1]
        return script_content

    # 备选：查找 def run( 或 with sync_playwright()
    lines = script_content.splitlines()
    insert_idx = -1
    for i, line in enumerate(lines):
        if "page = " in line and "new_page()" in line:
            insert_idx = i + 1
            break

    if insert_idx == -1:
        # 再尝试找 browser = 之后的 page.goto
        for i, line in enumerate(lines):
            if "browser = " in line or "context = " in line:
                insert_idx = i + 1
                break

    if insert_idx > 0:
        indent = _get_line_indent(lines[insert_idx - 1])
        login_code = "\n".join(apply_indent(login_body_lines, indent))
        lines.insert(insert_idx, login_code)
        script_content = "\n".join(lines)
        return script_content

    # 兜底：直接放开头
    login_code = "\n".join(login_body_lines)
    script_content = login_code + "\n" + script_content
    return script_content


# ========== 脚本列表 ==========

def list_recordings(directory: Path) -> List[Dict]:
    """列出目录中的所有录制脚本"""
    if not directory.exists():
        return []
    recordings = []
    for f in sorted(directory.glob("*.py"), key=lambda p: p.stat().st_mtime, reverse=True):
        stat = f.stat()
        recordings.append({
            "path": f,
            "name": f.name,
            "size": stat.st_size,
            "mtime": datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        })
    return recordings


if __name__ == "__main__":
    # 简单测试
    test_script = '''
from playwright.sync_api import Playwright, sync_playwright

def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto("https://example.com")
    page.fill("input[name='q']", "测试搜索")
    page.click("button[type='submit']")
    context.close()
    browser.close()

with sync_playwright() as playwright:
    run(playwright)
'''
    params = extract_params_from_script(test_script)
    print("提取的参数:", params)
