#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M3U8 下载器 - 一键安装脚本
检查依赖、安装后启动主程序。
"""

import sys
import subprocess
import importlib.util
from pathlib import Path


def print_banner():
    """打印欢迎信息"""
    print("=" * 48)
    print("  M3U8 下载器 - 安装与启动")
    print("  轻量桌面端 HLS / M3U8 下载工具")
    print("  GitHub: @shayuaidoudou")
    print("=" * 48)


def check_python_version():
    """检查 Python 版本"""
    if sys.version_info < (3, 8):
        print("错误: 需要 Python 3.8 或更高版本")
        print(f"当前版本: {sys.version}")
        input("按回车键退出...")
        return False
    print(
        f"Python 版本检查通过: "
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )
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
        else:
            print(f"已安装: {package}")

    if missing_packages:
        print("\n缺少以下依赖:")
        for package in missing_packages:
            print(f"  - {package}")
        return missing_packages

    print("\n依赖检查通过。")
    return []


def install_dependencies():
    """安装依赖包"""
    print("\n开始安装依赖...")
    try:
        print("正在升级 pip...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--upgrade", "pip"],
            stdout=subprocess.DEVNULL,
        )

        print("正在安装 requirements.txt...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"]
        )
        print("依赖安装完成。")
        return True
    except subprocess.CalledProcessError as e:
        print(f"依赖安装失败: {e}")
        return False


def launch_app():
    """启动应用"""
    print("\n正在启动 M3U8 下载器...")
    try:
        if not Path("main.py").exists():
            print("找不到 main.py，请确认当前目录为项目根目录。")
            return False

        from main import main as app_main

        app_main()
        return True
    except Exception as e:
        print(f"启动失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """主函数"""
    print_banner()

    if not check_python_version():
        return 1

    missing = check_dependencies()

    if missing:
        print("\n是否自动安装缺少的依赖？")
        choice = input("请输入 y/n (默认: y): ").lower().strip()

        if choice == "n":
            print("请手动执行: pip install -r requirements.txt")
            input("按回车键退出...")
            return 1

        if not install_dependencies():
            print("安装失败，请检查网络后重试，或手动安装依赖。")
            input("按回车键退出...")
            return 1

        missing = check_dependencies()
        if missing:
            print("安装后仍缺少必要依赖，请检查安装过程。")
            input("按回车键退出...")
            return 1

    print("\n准备就绪，即将启动程序。")
    input("按回车键继续...")

    if not launch_app():
        input("按回车键退出...")
        return 1

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n已取消。")
        sys.exit(0)
    except Exception as e:
        print(f"\n意外错误: {e}")
        input("按回车键退出...")
        sys.exit(1)
