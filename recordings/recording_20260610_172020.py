import re
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(channel="chrome", headless=False)
    context = browser.new_context(ignore_https_errors=True)
    page = context.new_page()
    page.goto("https://www.zhyw.spic/login/?c_url=/")
    page.locator("div").first.click()
    page.get_by_role("link", name="账号登录").locator("span").click()
    page.get_by_role("textbox", name="用户名").click()
    page.get_by_role("textbox", name="用户名").click()
    page.get_by_role("textbox", name="用户名").fill("18162733378")
    page.get_by_role("textbox", name="密码").click()
    page.get_by_role("textbox", name="密码").fill("Lw@18162733378&")
    page.get_by_role("textbox", name="密码").click()
    page.get_by_role("button", name="登录").click()
    page.get_by_role("link", name="服务目录").click()
    page.locator("#service-content span").filter(has_text="用户支持").click()
    page.get_by_role("radio", name="工程师").check()
    page.locator(".bk-select-name.medium-font").first.click()
    page.get_by_text("代用户提单").click()
    page.get_by_text("代用户提单").click()
    page.get_by_text("工程师补录").click()
    page.locator(".popup-mask").click()
    page.get_by_role("textbox", name="请输入组织架构，通用角色或用户名，回车进行搜索").click()
    page.get_by_role("textbox", name="请输入组织架构，通用角色或用户名，回车进行搜索").fill("张建浪")
    page.get_by_role("textbox", name="请输入组织架构，通用角色或用户名，回车进行搜索").press("Enter")
    page.get_by_text("00878568").click()
    page.get_by_role("button", name="确认").click()
    page.close()

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
