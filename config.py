import os
from dotenv import load_dotenv


class Config:
    """RPA 配置类，支持运行时刷新"""

    def refresh(self):
        """重新加载 .env 文件"""
        load_dotenv(override=True)
        self.BASE_URL = "https://www.zhyw.spic"
        self.LOGIN_URL = f"{self.BASE_URL}/login/?c_url=/"
        self.USERNAME = os.getenv("ZHYW_USERNAME", "")
        self.PASSWORD = os.getenv("ZHYW_PASSWORD", "")
        self.HEADLESS = False
        self.IGNORE_HTTPS_ERRORS = True
        self.SLOW_MO = 500
        self.BROWSER_PATH = os.getenv("BROWSER_PATH", "")

    def __init__(self):
        self.refresh()


# 全局配置实例（运行时可通过 config.refresh() 刷新）
config = Config()
