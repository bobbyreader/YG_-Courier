import os
import re
import sys
import winreg

# ========== 便携模式：优先使用打包自带的 Playwright 浏览器 ==========
if getattr(sys, 'frozen', False):
    _app_dir = os.path.dirname(sys.executable)
else:
    _app_dir = os.path.dirname(os.path.abspath(__file__))

_portable_browsers = os.path.join(_app_dir, "playwright")
if os.path.isdir(_portable_browsers):
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = _portable_browsers
    print(f"[RPA] 使用便携浏览器: {_portable_browsers}")

from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext
from config import config


# ========== 本地浏览器自动检测 ==========
_BROWSER_PATH = None


def _find_browser_from_registry(browser_name: str, reg_path: str) -> str | None:
    """从注册表查找浏览器安装路径"""
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path) as key:
            path, _ = winreg.QueryValueEx(key, "")
            if path and os.path.isfile(path):
                return path
    except Exception:
        pass
    return None


def _find_browser_from_common_paths(exe_name: str) -> str | None:
    """从常见安装目录查找浏览器"""
    program_files = [
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        os.environ.get("LOCALAPPDATA", r""),
    ]
    
    # 常见浏览器安装路径模式
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


def find_local_browser() -> str | None:
    """
    自动检测 Windows 本地已安装的 Chrome 或 Edge。
    优先 Chrome，其次 Edge。
    """
    global _BROWSER_PATH
    if _BROWSER_PATH:
        return _BROWSER_PATH

    candidates = [
        # Chrome
        ("chrome.exe", r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"),
        # Edge
        ("msedge.exe", r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe"),
    ]

    for exe_name, reg_path in candidates:
        # 1. 尝试注册表
        path = _find_browser_from_registry(exe_name, reg_path)
        if path:
            _BROWSER_PATH = path
            return path
        # 2. 尝试常见路径
        path = _find_browser_from_common_paths(exe_name)
        if path:
            _BROWSER_PATH = path
            return path

    return None


def check_browser() -> bool:
    """检查浏览器环境（本地或便携均可）"""
    local = find_local_browser()
    if local:
        print(f"[RPA] 检测到本地浏览器: {local}")
        return True

    # 检查是否有便携浏览器
    portable = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "")
    if portable and os.path.isdir(portable):
        print(f"[RPA] 使用便携浏览器: {portable}")
        return True

    print("\n" + "=" * 50)
    print("[RPA] 错误: 未检测到可用浏览器！")
    print("=" * 50)
    print("\n请确保以下之一:")
    print("  1. 系统已安装 Chrome 或 Edge")
    print("  2. 便携包包含 playwright/ 目录")
    print("\n如果已安装但仍检测不到，请手动指定路径:")
    print('  在 .env 文件中添加: BROWSER_PATH="C:\\...\\chrome.exe"')
    print("=" * 50)
    return False


class ZhywRpaBot:
    def __init__(self):
        self.playwright = None
        self.browser: Browser = None
        self.context: BrowserContext = None
        self.page: Page = None

    def start(self):
        """启动浏览器（优先本地 Chrome/Edge，其次便携 Chromium）"""
        browser_path = config.BROWSER_PATH or find_local_browser()
        
        self.playwright = sync_playwright().start()
        
        launch_kwargs = {
            "headless": config.HEADLESS,
            "slow_mo": config.SLOW_MO,
            "args": [
                '--ignore-certificate-errors',
                '--ignore-certificate-errors-spki-list',
                '--disable-web-security'
            ]
        }
        
        if browser_path:
            print(f"[RPA] 正在启动本地浏览器: {browser_path}")
            launch_kwargs["executable_path"] = browser_path
        else:
            print("[RPA] 未检测到本地 Chrome/Edge，使用自带 Chromium")
        
        self.browser = self.playwright.chromium.launch(**launch_kwargs)
        self.context = self.browser.new_context(
            ignore_https_errors=config.IGNORE_HTTPS_ERRORS,
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        self.page = self.context.new_page()
        print("[RPA] 浏览器已启动，HTTPS 证书验证已关闭")

    def login(self):
        """模拟登录"""
        print(f"[RPA] 正在访问登录页: {config.LOGIN_URL}")
        self.page.goto(config.LOGIN_URL, wait_until="networkidle")

        # 填写用户名
        self.page.get_by_role("textbox", name="用户名").click()
        self.page.get_by_role("textbox", name="用户名").fill(config.USERNAME)
        print(f"[RPA] 已填写用户名: {config.USERNAME}")

        # 填写密码
        self.page.get_by_role("textbox", name="密码").click()
        self.page.get_by_role("textbox", name="密码").fill(config.PASSWORD)
        print("[RPA] 已填写密码")

        # 点击登录
        self.page.get_by_role("button", name="登录").click()
        print("[RPA] 已点击登录按钮")

        # 等待页面加载完成
        self.page.wait_for_load_state("networkidle")
        print(f"[RPA] 当前页面: {self.page.url}")

    def _select_from_dropdown(self, field_label: str, keyword: str, option_text: str):
        """通用下拉框选择：点击字段 -> 输入关键词 -> 点击选项"""
        print(f"[RPA] 正在选择 {field_label}...")
        
        # 方式1：通过 label 文本找到字段，然后点击其旁边的下拉框
        try:
            # 先找包含 label 文本的元素，然后找同级的下拉框
            field = self.page.locator(".bk-form-item").filter(has_text=field_label)
            dropdown = field.locator(".bk-select-name").first
            dropdown.click()
        except Exception:
            # 方式2：直接点页面上的第一个未选中的下拉框（fallback）
            self.page.locator(".bk-select").locator(".bk-select-name").first.click()
        
        # 等待下拉列表弹出
        self.page.wait_for_timeout(300)
        
        # 如果有搜索框则输入关键词过滤
        search_input = self.page.locator(".bk-select-dropdown-content .bk-select-search-input").first
        if search_input.count() > 0 and search_input.is_visible():
            search_input.fill(keyword)
            self.page.wait_for_timeout(300)
        
        # 点击选项（优先匹配完整文本）
        option = self.page.get_by_text(option_text, exact=True)
        if option.count() == 0:
            option = self.page.get_by_text(option_text, exact=False).first
        option.click()
        print(f"[RPA] {field_label} 已选择: {option_text}")
        self.page.wait_for_timeout(300)

    def submit_ticket(self,
                       assignee: str,
                       description: str,
                       system_name: str = "集团公司经营管理平台-报销报账系统",
                       system_keyword: str = "报销",
                       ticket_type: str = "咨询解答",
                       title: str = "报销报账#问题处理(咨询)"):
        """
        提交工单（支持参数化配置）
        """
        print("[RPA] 开始提交工单...")

        # 1. 进入服务目录 -> 用户支持
        self.page.get_by_role("link", name="服务目录").click()
        self.page.locator("#service-content span").filter(has_text="用户支持").click()
        print("[RPA] 已进入服务目录 -> 用户支持")

        # 2. 直达工单创建页
        ticket_url = (
            "https://www.zhyw.spic/o/bk_itsm/#/ticketInfo"
            "?canTicketAgency=false&serviceId=70&catalogId=32&serviceType=support"
        )
        self.page.goto(ticket_url, wait_until="networkidle")
        print("[RPA] 已打开工单创建页")

        # 3. 选择"工程师"
        self.page.get_by_role("radio", name="工程师").check()
        print("[RPA] 已选择: 工程师")

        # 4. 选择"工程师补录"
        self.page.locator(".bk-select-name.medium-font").first.click()
        self.page.get_by_text("工程师补录").click()
        self.page.locator(".popup-mask").click()
        print("[RPA] 已选择: 工程师补录")

        # 5. 搜索并选择受理人（优先匹配路径含"湖北公司"的结果）
        print(f"[RPA] 正在搜索受理人: {assignee}")
        search_box = self.page.get_by_role(
            "textbox",
            name="请输入组织架构，通用角色或用户名，回车进行搜索"
        )
        search_box.click()
        search_box.fill(assignee)
        search_box.press("Enter")
        self.page.wait_for_timeout(1000)  # 等待搜索结果弹窗加载

        # 优先选择包含"湖北公司"的搜索结果项
        # 从截图可见，弹窗里每条结果都显示完整组织路径，直接按文本匹配最可靠
        hubei_candidates = self.page.locator("text=湖北公司")
        total = hubei_candidates.count()
        if total > 0:
            # 遍历所有匹配，点击第一个在弹窗搜索结果区域内的
            for i in range(total):
                candidate = hubei_candidates.nth(i)
                try:
                    candidate.click()
                    print("[RPA] 已选择含'湖北公司'的受理人")
                    break
                except Exception:
                    continue
        else:
            # fallback：直接点第一条搜索结果（通过上下结构定位）
            fallback = self.page.locator("//*[contains(text(),'搜索结果:')]/following::div[contains(text(),'(')]").first
            if fallback.count() > 0:
                fallback.click()
            else:
                self.page.get_by_text(assignee, exact=False).first.click()
            print("[RPA] 未找到'湖北公司'，默认选第一条")
        
        self.page.get_by_role("button", name="确认").click()
        print("[RPA] 已确认受理人选择")
        self.page.wait_for_timeout(500)

        # 6. 选择系统（功能模块）
        self._select_from_dropdown(
            field_label="系统",
            keyword=system_keyword,
            option_text=system_name
        )

        # 7. 选择工单类型
        self._select_from_dropdown(
            field_label="类型",
            keyword="",
            option_text=ticket_type
        )

        # 8. 填写标题
        print("[RPA] 正在填写标题...")
        title_box = self.page.get_by_role(
            "textbox",
            name="类型#系统#关键问题摘要，如咨询#电投壹#临时账号转正式账号"
        )
        title_box.click()
        title_box.fill(title)
        print(f"[RPA] 标题已填写: {title}")

        # 9. 填写问题描述
        print("[RPA] 正在填写问题描述...")
        desc_box = self.page.get_by_role(
            "textbox",
            name="示例： 单位入职新员工，因工作需要创建了临时员工编号，试用期满后，可否将临时员工编号转为正式员工编号。"
        )
        desc_box.click()
        desc_box.fill(description)
        print("[RPA] 问题描述已填写")

        print("[RPA] 工单表单已填写完毕，等待人工审核...")
        self.page.wait_for_load_state("networkidle")

    def _select_assignee(self, assignee: str):
        """通用：搜索并选择受理人（优先匹配湖北公司）"""
        print(f"[RPA] 正在搜索受理人: {assignee}")
        search_box = self.page.get_by_role(
            "textbox",
            name="请输入组织架构，通用角色或用户名，回车进行搜索"
        )
        search_box.click()
        search_box.fill(assignee)
        search_box.press("Enter")
        self.page.wait_for_timeout(1000)

        hubei_candidates = self.page.locator("text=湖北公司")
        total = hubei_candidates.count()
        if total > 0:
            for i in range(total):
                candidate = hubei_candidates.nth(i)
                try:
                    candidate.click()
                    print("[RPA] 已选择含'湖北公司'的受理人")
                    break
                except Exception:
                    continue
        else:
            fallback = self.page.locator(
                "//*[contains(text(),'搜索结果:')]/following::div[contains(text(),'(')]"
            ).first
            if fallback.count() > 0:
                fallback.click()
            else:
                self.page.get_by_text(assignee, exact=False).first.click()
            print("[RPA] 未找到'湖北公司'，默认选第一条")

        self.page.get_by_role("button", name="确认").click()
        print("[RPA] 已确认受理人选择")
        self.page.wait_for_timeout(500)

    def submit_permission(self,
                          assignee: str,
                          description: str,
                          title: str = "报销报账#权限申请#"):
        """
        提交权限申请工单
        """
        print("[RPA] 开始提交权限申请工单...")

        # 1. 进入服务目录 -> 项目相关流程 -> 专业系统账号与权限流程
        self.page.get_by_role("link", name="服务目录").click()
        self.page.get_by_text("项目相关流程").click()
        self.page.locator("#service-content span").filter(
            has_text="专业系统账号与权限流程"
        ).click()
        print("[RPA] 已进入服务目录 -> 专业系统账号与权限流程")

        # 2. 选择"工程师"
        self.page.get_by_role("radio", name="工程师").check()
        print("[RPA] 已选择: 工程师")

        # 3. 选择"代用户提单"
        self.page.locator(".bk-select-name.medium-font").first.click()
        self.page.get_by_text("代用户提单").click()
        self.page.locator(".popup-mask").first.click()
        print("[RPA] 已选择: 代用户提单")

        # 4. 搜索并选择受理人
        self._select_assignee(assignee)

        # 5. 选择系统（复选：合同管理 + 报销报账）
        print("[RPA] 正在选择系统...")
        self.page.get_by_text("集团公司经营管理平台-合同管理系统").click()
        self.page.get_by_text("集团公司经营管理平台-报销报账系统").click()
        print("[RPA] 系统已选择: 合同管理系统、报销报账系统")
        self.page.wait_for_timeout(300)

        # 6. 填写标题
        print("[RPA] 正在填写标题...")
        title_box = self.page.get_by_role(
            "textbox",
            name="类型#系统#关键问题摘要，如咨询#电投壹#临时账号转正式账号"
        )
        title_box.click()
        title_box.fill(title)
        print(f"[RPA] 标题已填写: {title}")

        # 7. 填写问题描述
        print("[RPA] 正在填写问题描述...")
        desc_box = self.page.get_by_role(
            "textbox",
            name="示例： 单位入职新员工，因工作需要创建了临时员工编号，试用期满后，可否将临时员工编号转为正式员工编号。"
        )
        desc_box.click()
        desc_box.fill(description)
        print("[RPA] 问题描述已填写")

        print("[RPA] 权限申请表单已填写完毕，等待人工审核...")
        self.page.wait_for_load_state("networkidle")

    def take_screenshot(self, path: str = "screenshot.png"):
        """截图保存"""
        self.page.screenshot(path=path, full_page=True)
        print(f"[RPA] 截图已保存: {path}")

    def close(self):
        """关闭浏览器"""
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
        print("[RPA] 浏览器已关闭")


class RpaLogger:
    """支持 GUI 回调的日志输出器"""
    def __init__(self, callback=None):
        self.callback = callback

    def log(self, msg: str):
        print(msg)
        if self.callback:
            self.callback(msg)


def run_rpa(assignee: str, description: str, flow_type: str = "support", on_log=None):
    """
    执行RPA工单填写流程（供GUI调用）

    Args:
        assignee: 受理人姓名
        description: 问题描述
        flow_type: 流程类型，"support"=用户支持，"permission"=权限申请
        on_log: 日志回调函数，接收字符串参数
    """
    # 运行时重新加载配置（GUI可能已修改 .env）
    config.refresh()

    logger = RpaLogger(callback=on_log)

    # 检查浏览器
    local = find_local_browser()
    if not local:
        logger.log("\n" + "=" * 50)
        logger.log("[RPA] 错误: 未检测到 Chrome 或 Edge 浏览器！")
        logger.log("=" * 50)
        logger.log("\n请确保已安装 Chrome 或 Edge。")
        logger.log('也可在配置中手动指定 BROWSER_PATH。')
        logger.log("=" * 50)
        return False
    logger.log(f"[RPA] 检测到本地浏览器: {local}")

    bot = ZhywRpaBot()
    success = False
    try:
        bot.start()
        bot.login()
        bot.take_screenshot("login_success.png")

        if flow_type == "permission":
            bot.submit_permission(assignee=assignee, description=description)
            bot.take_screenshot("permission_filled.png")
        else:
            bot.submit_ticket(assignee=assignee, description=description)
            bot.take_screenshot("ticket_filled.png")

        logger.log("\n" + "=" * 50)
        logger.log("[RPA] 工单表单已自动填写完成！")
        logger.log("[RPA] 浏览器保持打开，请人工审核并手动提交/保存。")
        logger.log("=" * 50)
        success = True

    except Exception as e:
        logger.log(f"\n[RPA] 错误: {e}")
        if bot and bot.page:
            try:
                bot.take_screenshot("error.png")
            except Exception as screenshot_error:
                logger.log(f"[RPA] 保存错误截图失败: {screenshot_error}")
        logger.log("[RPA] 浏览器保持打开，请查看错误页面。")
    finally:
        if not success:
            bot.close()
    return bot if success else None


def main():
    """命令行入口（兼容旧版终端交互）"""
    import argparse
    parser = argparse.ArgumentParser(description="内网RPA工单自动填写")
    parser.add_argument("--assignee", required=True, help="受理人姓名")
    parser.add_argument("--description", required=True, help="问题描述")
    args = parser.parse_args()
    run_rpa(assignee=args.assignee, description=args.description)


if __name__ == "__main__":
    main()
