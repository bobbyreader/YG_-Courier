#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Playwright codegen 辅助程序
用于 PyInstaller 打包环境中，作为子进程调用 playwright codegen
用法:
    codegen_helper.exe codegen [options] URL
"""

import sys


def main():
    """调用 playwright codegen"""
    # playwright 1.60.0+ 的 CLI 入口在 __main__ 模块
    from playwright.__main__ import main as cli_main

    # 透传所有参数
    sys.argv = ["playwright"] + sys.argv[1:]
    cli_main()


if __name__ == "__main__":
    main()
