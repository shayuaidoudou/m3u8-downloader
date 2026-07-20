#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M3U8 下载器启动器
检查依赖后启动主程序。
"""

import sys
import subprocess
import importlib.util


def check_python_version():
    """检查 Python 版本"""
    if sys.version_info < (3, 8):
        print("错误: 需要 Python 3.8 或更高版本")
        print(f"当前版本: {sys.version}")
        return False
    return True


def check_dependencies():
    """检查依赖包"""
    required_packages = [
        "PySide6",
        "requests",
        "cryptography",
        "aiohttp",
    ]

    missing_packages = []

    for package in required_packages:
        if importlib.util.find_spec(package) is None:
            missing_packages.append(package)

    if missing_packages:
        print("缺少以下依赖:")
        for package in missing_packages:
            print(f"  - {package}")
        print("\n请运行: pip install -r requirements.txt")
        return False

    return True


def install_dependencies():
    """自动安装依赖"""
    print("正在安装依赖...")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"]
        )
        print("依赖安装完成。")
        return True
    except subprocess.CalledProcessError as e:
        print(f"依赖安装失败: {e}")
        return False


def main():
    """主函数"""
    print("M3U8 下载器")
    print("=" * 40)

    if not check_python_version():
        input("按回车键退出...")
        return 1

    if not check_dependencies():
        print("\n是否自动安装依赖？(y/n): ", end="")
        choice = input().lower().strip()

        if choice == "y":
            if not install_dependencies():
                input("按回车键退出...")
                return 1

            if not check_dependencies():
                print("依赖安装后仍缺少必要包。")
                input("按回车键退出...")
                return 1
        else:
            input("按回车键退出...")
            return 1

    print("正在启动...")
    try:
        from main import main as app_main

        return app_main()
    except Exception as e:
        print(f"启动失败: {e}")
        import traceback

        traceback.print_exc()
        input("按回车键退出...")
        return 1


if __name__ == "__main__":
    sys.exit(main())
