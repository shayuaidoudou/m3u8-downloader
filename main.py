#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M3U8 下载器 - 主程序
现代化的PySide6 GUI界面
"""

import sys
import os
import threading
import time
import json
import logging
from pathlib import Path
from threading import Thread
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QFormLayout, QLabel, QLineEdit, QPushButton, QProgressBar,
    QTextEdit, QFileDialog, QSpinBox, QGroupBox, QFrame,
    QSystemTrayIcon, QMenu, QMessageBox, QSplitter, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox,
    QComboBox, QDialog, QDialogButtonBox, QPlainTextEdit, QScrollArea,
    QGraphicsOpacityEffect,
)
from PySide6.QtCore import (
    Qt, QThread, Signal, QTimer, QUrl, QPropertyAnimation, 
    QEasingCurve, QRect, QSize, QObject
)
from PySide6.QtGui import (
    QFont, QPalette, QColor, QIcon, QPixmap, QPainter, QLinearGradient,
    QAction, QDesktopServices, QTextCharFormat, QTextCursor
)
from m3u8_downloader import M3U8Downloader
from utils import (
    is_valid_m3u8_url, sanitize_filename, ensure_extension,
    format_time, get_available_filename, validate_output_path,
    extract_title_from_url, build_spring_log_segments, LOG_LEVEL_COLORS,
    log_console_stylesheet,
)
from config import (
    DEFAULT_CONFIG,
    ERROR_MESSAGES,
    STATUS_MESSAGES,
    THEME_NAMES,
    UI_TOKENS,
    get_theme,
    get_theme_name,
)
from search import (
    CHANNEL_INPUT_COOKIE,
    CHANNEL_INPUT_TYPE,
    IYF_CHANNEL,
    SEARCH_CHANNELS,
    channel_requires_refresh,
    create_search_engine,
    get_channel_input_mode,
    search_with_engine,
)


def get_settings_path():
    """获取settings.json的正确路径"""
    if getattr(sys, 'frozen', False):
        # exe环境：使用exe所在目录
        exe_dir = os.path.dirname(sys.executable)
        return os.path.join(exe_dir, "settings.json")
    else:
        # 开发环境：使用脚本所在目录
        return os.path.join(os.path.dirname(__file__), "settings.json")


def app_base_dir():
    """开发目录或 PyInstaller 资源目录。"""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def asset_path(*parts):
    return app_base_dir().joinpath("assets", *parts)


def resolve_app_icon():
    """优先使用 assets/shayu 头像，兼容打包后的路径。"""
    for name in ("app_icon.png", "app.icns", "shayu.jpg", "favicon.ico"):
        path = asset_path(name)
        if path.exists():
            return str(path)
    return None


def app_font(size, weight=QFont.Normal):
    """继承全局字体族，仅设置字号与字重。"""
    font = QFont()
    font.setPointSize(size)
    font.setWeight(weight)
    return font


def append_spring_boot_log(widget, message, thread_name="main"):
    """把一行日志以 Spring Boot 风格彩色写入 QPlainTextEdit。"""
    if widget is None:
        return

    role_colors = {
        "time": "#8B949E",
        "meta": "#8B949E",
        "message": "#E6EDF3",
    }

    cursor = widget.textCursor()
    cursor.movePosition(QTextCursor.End)

    level = "INFO"
    for text, role in build_spring_log_segments(message, thread_name=thread_name):
        fmt = QTextCharFormat()
        if role == "level":
            level = text.strip() or level
            fmt.setForeground(QColor(LOG_LEVEL_COLORS.get(level, "#98C379")))
            fmt.setFontWeight(QFont.DemiBold)
        else:
            fmt.setForeground(QColor(role_colors.get(role, "#E6EDF3")))
        cursor.insertText(text, fmt)

    widget.setTextCursor(cursor)
    scrollbar = widget.verticalScrollBar()
    scrollbar.setValue(scrollbar.maximum())


def _make_close_button(on_click):
    """无边框关闭按钮，用于自绘对话框标题栏。"""
    btn = QPushButton("×")
    btn.setFixedSize(28, 28)
    btn.setFont(app_font(14, QFont.Normal))
    btn.setCursor(Qt.PointingHandCursor)
    btn.setStyleSheet(f"""
        QPushButton {{
            background: transparent;
            color: {UI_TOKENS['text_subtle']};
            border: none;
            border-radius: {UI_TOKENS['radius_tag']}px;
            padding: 0;
        }}
        QPushButton:hover {{
            background: {UI_TOKENS['surface_alt']};
            color: {UI_TOKENS['text']};
        }}
        QPushButton:pressed {{
            background: {UI_TOKENS['surface_hover']};
        }}
    """)
    btn.clicked.connect(on_click)
    return btn


class DownloadWorker(QThread):
    """下载工作线程"""
    progress_updated = Signal(dict)
    download_finished = Signal(bool)
    
    def __init__(self, downloader, m3u8_url, output_path, max_workers=10, parent=None):
        super().__init__(parent)
        self.downloader = downloader
        self.m3u8_url = m3u8_url
        self.output_path = output_path
        self.max_workers = max_workers
        self._is_running = True
    
    def run(self):
        """运行下载"""
        success = False
        try:
            if not self._is_running:
                self.download_finished.emit(False)
                return
            self.downloader.max_workers = self.max_workers
            success = self.downloader.download(
                self.m3u8_url, 
                self.output_path, 
                self.progress_callback
            )
        except Exception as e:
            if self._is_running:
                self.progress_updated.emit({
                    'status': 'error', 
                    'message': f'下载出错: {str(e)}'
                })
            success = False
        finally:
            # 线程结束前再发一次完成信号，避免对象提前销毁
            if self._is_running:
                self.download_finished.emit(success)
    
    def progress_callback(self, data):
        """进度回调"""
        if self._is_running:
            self.progress_updated.emit(data)
    
    def stop(self):
        """停止下载"""
        self._is_running = False
        if hasattr(self.downloader, 'stop_download'):
            self.downloader.stop_download()

    def requestInterruption(self):
        """兼容 Qt 中断语义。"""
        super().requestInterruption()
        self.stop()


class ModernButton(QPushButton):
    """统一按钮：primary / default / danger 三档，样式集中在此。"""

    def __init__(self, text, primary=False, icon_text="", variant=None):
        super().__init__(text)
        self.primary = primary
        self.icon_text = icon_text
        self._variant = variant or ('primary' if primary else 'default')
        self.setMinimumHeight(36)
        self.setFont(app_font(10, QFont.DemiBold))
        self.setCursor(Qt.PointingHandCursor)

        if icon_text:
            self.setText(f"{icon_text} {text}")

        self._apply_variant()

    def _apply_variant(self):
        radius = UI_TOKENS['radius_control']
        text_muted = UI_TOKENS['text_muted']
        border = UI_TOKENS['border']
        surface_alt = UI_TOKENS['surface_alt']

        if self._variant == 'primary':
            primary_color = UI_TOKENS['primary']
            hover = UI_TOKENS['primary_hover']
            active = UI_TOKENS['primary_active']
            self.setStyleSheet(f"""
                QPushButton {{
                    background: {primary_color};
                    color: #FFFFFF;
                    border: 1px solid {primary_color};
                    border-radius: {radius}px;
                    padding: 8px 18px;
                }}
                QPushButton:hover {{ background: {hover}; border-color: {hover}; }}
                QPushButton:pressed {{ background: {active}; border-color: {active}; }}
                QPushButton:disabled {{
                    background: {surface_alt};
                    color: {text_muted};
                    border-color: {border};
                }}
            """)
        elif self._variant == 'danger':
            danger = UI_TOKENS['danger']
            self.setStyleSheet(f"""
                QPushButton {{
                    background: {UI_TOKENS['surface']};
                    color: {danger};
                    border: 1px solid {border};
                    border-radius: {radius}px;
                    padding: 8px 14px;
                }}
                QPushButton:hover {{
                    background: {surface_alt};
                    border-color: {danger};
                }}
                QPushButton:pressed {{
                    background: {surface_alt};
                }}
                QPushButton:disabled {{
                    background: {surface_alt};
                    color: {text_muted};
                    border-color: {border};
                }}
            """)
        else:  # default
            primary_color = UI_TOKENS['primary']
            self.setStyleSheet(f"""
                QPushButton {{
                    background: {UI_TOKENS['surface']};
                    color: {UI_TOKENS['text']};
                    border: 1px solid {border};
                    border-radius: {radius}px;
                    padding: 8px 14px;
                }}
                QPushButton:hover {{
                    background: {surface_alt};
                    border-color: {UI_TOKENS['border_strong']};
                    color: {primary_color};
                }}
                QPushButton:pressed {{
                    background: {surface_alt};
                    border-color: {primary_color};
                }}
                QPushButton:disabled {{
                    background: {surface_alt};
                    color: {text_muted};
                    border-color: {border};
                }}
            """)


class ModernLineEdit(QLineEdit):
    """现代极简输入框"""

    def __init__(self, placeholder="", icon_text=""):
        super().__init__()
        self.setPlaceholderText(placeholder)
        self.setMinimumHeight(40)
        self.setFont(app_font(10))
        self.setClearButtonEnabled(True)

        if icon_text:
            self.setPlaceholderText(f"{icon_text} {placeholder}")

        self.setStyleSheet(f"""
            QLineEdit {{
                border: 1px solid {UI_TOKENS['border']};
                border-radius: {UI_TOKENS['radius_control']}px;
                padding: 8px 12px;
                background: {UI_TOKENS['surface']};
                color: {UI_TOKENS['text']};
                selection-background-color: {UI_TOKENS['primary']};
                selection-color: #FFFFFF;
            }}
            QLineEdit:focus {{
                border-color: {UI_TOKENS['primary']};
            }}
            QLineEdit:hover {{
                border-color: {UI_TOKENS['border_focus']};
            }}
        """)


class ModernProgressBar(QProgressBar):
    """现代极简进度条"""

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(6)
        self.setMaximumHeight(8)
        self.setTextVisible(False)
        self.setStyleSheet(f"""
            QProgressBar {{
                border: none;
                border-radius: {UI_TOKENS['radius_progress']}px;
                background: {UI_TOKENS['surface_alt']};
            }}
            QProgressBar::chunk {{
                border-radius: {UI_TOKENS['radius_progress']}px;
                background: {UI_TOKENS['primary']};
            }}
        """)


class DownloadTaskWidget(QFrame):
    """下载任务组件"""
    
    # 定义信号
    download_finished = Signal(bool)
    
    def __init__(self, task_name, url, output_path, custom_headers=None):
        super().__init__()
        self.task_name = task_name
        self.url = url
        self.output_path = output_path
        self.custom_headers = custom_headers or {}
        self.worker = None
        
        self.setFrameStyle(QFrame.NoFrame)
        self._apply_card_style()
        
        self.setup_ui()

    def _apply_card_style(self, accent_color=None, border_color=None, hover_color=None):
        """卡片：纯 surface + hover 时边框加深，状态色通过左上圆点表达。"""
        accent = accent_color or UI_TOKENS['primary']
        border = border_color or UI_TOKENS['border']
        hover_border = hover_color or UI_TOKENS['border_strong']
        radius = UI_TOKENS['radius_card']
        self._accent_color = accent
        self.setStyleSheet(f"""
            QFrame#task_card {{
                background: {UI_TOKENS['surface']};
                border-radius: {radius}px;
                border: 1px solid {border};
            }}
            QFrame#task_card:hover {{
                border-color: {hover_border};
            }}
        """)
        if hasattr(self, 'status_dot'):
            self.status_dot.setStyleSheet(
                f"background: {accent}; border-radius: 5px; border: none;"
            )

    def _set_status_accent(self, color):
        """状态圆点与状态文字同步"""
        self._accent_color = color
        if hasattr(self, 'status_dot'):
            self.status_dot.setStyleSheet(
                f"background: {color}; border-radius: 5px; border: none;"
            )
        if hasattr(self, 'status_label'):
            self.status_label.setStyleSheet(
                f"color: {color}; background: transparent; border: none;"
            )

    def setup_ui(self):
        """设置UI"""
        self.setObjectName("task_card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(10)

        # 标题行：圆点 + 任务名 + 状态文字
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)

        self.status_dot = QLabel()
        self.status_dot.setFixedSize(10, 10)
        self.status_dot.setStyleSheet(
            f"background: {UI_TOKENS['primary']}; border-radius: 5px; border: none;"
        )
        header_layout.addWidget(self.status_dot, 0, Qt.AlignVCenter)

        title_label = QLabel(self.task_name)
        title_label.setFont(app_font(11, QFont.DemiBold))
        title_label.setStyleSheet(f"color: {UI_TOKENS['text']}; background: transparent; border: none;")
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        self.status_label = QLabel("准备中")
        self.status_label.setFont(app_font(9, QFont.DemiBold))
        self.status_label.setStyleSheet(
            f"color: {UI_TOKENS['primary']}; background: transparent; border: none;"
        )
        header_layout.addWidget(self.status_label)

        layout.addLayout(header_layout)

        # URL 与保存路径：更细的字号 + subtle 色，标签前缀单独一档色
        url_display = self.url if len(self.url) <= 82 else f"{self.url[:79]}..."
        url_label = QLabel(
            f"<span style='color:{UI_TOKENS['text_subtle']};'>链接</span>"
            f"&nbsp;&nbsp;<span style='color:{UI_TOKENS['text_muted']};'>{url_display}</span>"
        )
        url_label.setTextFormat(Qt.RichText)
        url_label.setFont(app_font(9))
        url_label.setStyleSheet("background: transparent; border: none; padding: 0;")
        url_label.setWordWrap(True)
        layout.addWidget(url_label)

        output_display = self.output_path if len(self.output_path) <= 82 else f"...{self.output_path[-79:]}"
        output_label = QLabel(
            f"<span style='color:{UI_TOKENS['text_subtle']};'>保存</span>"
            f"&nbsp;&nbsp;<span style='color:{UI_TOKENS['text_muted']};'>{output_display}</span>"
        )
        output_label.setTextFormat(Qt.RichText)
        output_label.setFont(app_font(9))
        output_label.setStyleSheet("background: transparent; border: none; padding: 0;")
        output_label.setWordWrap(True)
        layout.addWidget(output_label)

        self.progress_bar = ModernProgressBar()
        layout.addWidget(self.progress_bar)

        control_layout = QHBoxLayout()
        control_layout.setSpacing(8)
        control_layout.addStretch()

        self.start_btn = ModernButton("开始", primary=True)
        self.start_btn.clicked.connect(self.start_download)
        control_layout.addWidget(self.start_btn)

        self.stop_btn = ModernButton("暂停")
        self.stop_btn.clicked.connect(self.stop_download)
        self.stop_btn.setEnabled(False)
        control_layout.addWidget(self.stop_btn)

        self.delete_btn = ModernButton("删除", variant='danger')
        self.delete_btn.clicked.connect(self.delete_task)
        control_layout.addWidget(self.delete_btn)

        layout.addLayout(control_layout)
        self._apply_card_style()
    
    def start_download(self):
        """开始下载"""
        # 若已有线程，先安全停掉，避免旧 QThread 被覆盖后崩溃
        self.shutdown_worker(wait_ms=3000)

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.delete_btn.setEnabled(False)  # 下载时禁用删除
        self._set_status_accent(UI_TOKENS['primary'])
        
        # 获取主窗口的线程数设置
        main_window = self.parent()
        while main_window and not isinstance(main_window, MainWindow):
            main_window = main_window.parent()
        
        max_workers = DEFAULT_CONFIG['max_workers']
        if main_window and hasattr(main_window, 'threads_spin'):
            max_workers = main_window.threads_spin.value()
        
        # 创建下载器和工作线程（父对象绑定到任务卡片，随卡片生命周期管理）
        downloader = M3U8Downloader(custom_headers=self.custom_headers)
        self.worker = DownloadWorker(
            downloader,
            self.url,
            self.output_path,
            max_workers=max_workers,
            parent=self,
        )
        self.worker.progress_updated.connect(self.update_progress)
        self.worker.download_finished.connect(self.on_download_finished)
        self.worker.finished.connect(self._on_worker_thread_finished)
        self.worker.start()

    def _on_worker_thread_finished(self):
        """QThread 真正结束后再放开删除按钮，避免半销毁状态。"""
        if self.worker is not None and not self.worker.isRunning():
            self.delete_btn.setEnabled(True)

    def shutdown_worker(self, wait_ms=5000):
        """安全停止并等待下载线程，防止 QThread 被提前销毁导致进程崩溃。"""
        worker = self.worker
        if worker is None:
            return

        try:
            worker.progress_updated.disconnect(self.update_progress)
        except (RuntimeError, TypeError):
            pass
        try:
            worker.download_finished.disconnect(self.on_download_finished)
        except (RuntimeError, TypeError):
            pass

        if worker.isRunning():
            worker.stop()
            if not worker.wait(wait_ms):
                # 仍卡在网络 IO 时强制终止，避免退出阶段无限挂起
                worker.terminate()
                worker.wait(2000)

        self.worker = None
    
    def stop_download(self):
        """停止下载"""
        self.shutdown_worker(wait_ms=8000)

        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.delete_btn.setEnabled(True)
        self.status_label.setText("已暂停")
        self._set_status_accent(UI_TOKENS['warning'])
        self.progress_bar.setValue(0)

    def update_progress(self, data):
        """更新进度"""
        main_window = self._find_main_window()
        if main_window is not None and getattr(main_window, "is_closing", False):
            return
        try:
            if 'progress' in data:
                self.progress_bar.setValue(int(data['progress']))
                speed = data.get('speed', 0)
                eta = data.get('eta', 0)
                progress_percent = int(data['progress'])

                self.status_label.setText(
                    f"{progress_percent}% · {data['completed']}/{data['total']} · {speed:.1f}/s · {eta:.0f}s"
                )
                self._set_status_accent(UI_TOKENS['primary'])
            elif 'message' in data:
                if data.get('status') == 'error':
                    self.status_label.setText(f"错误：{data['message']}")
                    self._set_status_accent(UI_TOKENS['danger'])
                else:
                    self.status_label.setText(data['message'])
                    self._set_status_accent(UI_TOKENS['primary'])
        except RuntimeError:
            # 控件已被销毁
            return

    def on_download_finished(self, success):
        """下载完成回调"""
        main_window = self._find_main_window()
        if main_window is not None and getattr(main_window, "is_closing", False):
            # 退出过程中不再弹窗/改 UI，避免半销毁对象回调崩溃
            return

        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.delete_btn.setEnabled(True)

        self.download_finished.emit(success)

        if success:
            self.progress_bar.setValue(100)
            self.status_label.setText("下载完成")
            self._set_status_accent(UI_TOKENS['success'])
            self._apply_card_style(
                accent_color=UI_TOKENS['success'],
                border_color=UI_TOKENS['success'],
            )

            if main_window:
                CustomMessageBox.show_success(
                    main_window,
                    "下载完成",
                    f"任务“{self.task_name}”已成功下载完成。\n\n文件保存位置：\n{self.output_path}"
                )
        else:
            self.status_label.setText("下载失败")
            self._set_status_accent(UI_TOKENS['danger'])
            self._apply_card_style(
                accent_color=UI_TOKENS['danger'],
                border_color=UI_TOKENS['danger'],
            )

            if main_window:
                CustomMessageBox.show_error(
                    main_window,
                    "下载失败",
                    f"任务“{self.task_name}”下载失败。\n\n可能的原因：\n• 网络连接问题\n• M3U8 链接失效\n• 视频源访问受限\n\n请检查链接或稍后重试。"
                )
    
    def _find_main_window(self):
        """查找主窗口"""
        parent = self.parent()
        while parent and not isinstance(parent, MainWindow):
            parent = parent.parent()
        return parent
    
    def delete_task(self):
        """删除任务"""
        # 先停线程，再确认删除，避免确认期间线程结束回调碰已删对象
        self.shutdown_worker(wait_ms=8000)
        
        # 确认删除
        main_window = self._find_main_window()
        reply = CustomMessageBox.show_question(
            main_window or self,
            "确认删除",
            f"确定要删除任务 '{self.task_name}' 吗？\n\n删除后无法恢复。"
        )
        
        if reply == QDialog.Accepted:
            # 从界面中移除自己
            parent_widget = self.parent()
            if parent_widget:
                # 找到主窗口
                main_window = parent_widget
                while main_window and not isinstance(main_window, MainWindow):
                    main_window = main_window.parent()
                
                if main_window:
                    # 从任务列表中移除
                    if self in main_window.download_tasks:
                        main_window.download_tasks.remove(self)
                    
                    # 从布局中移除
                    self.setParent(None)
                    self.deleteLater()
                    
                    # 更新状态栏
                    main_window.statusBar().showMessage(f"已删除任务：{self.task_name}")
                    main_window._update_progress_overview()
                else:
                    # 如果找不到主窗口，直接移除
                    self.setParent(None)
                    self.deleteLater()


class CustomMessageBox(QDialog):
    """自定义消息框"""

    # 消息类型常量
    INFO = "info"
    WARNING = "warning"
    QUESTION = "question"
    SUCCESS = "success"
    ERROR = "error"

    def __init__(self, parent=None, title="提示", message="", msg_type=INFO, buttons=None):
        super().__init__(parent)
        self.result = QDialog.Rejected
        self.result_index = -1  # 记录用户点击的按钮索引
        self.msg_type = msg_type
        self.setup_ui(title, message, buttons)

    def setup_ui(self, title, message, buttons):
        """设置UI"""
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )

        self.setWindowTitle("")
        self.resize(480, 260)
        self.setModal(True)

        colors = {
            self.INFO: UI_TOKENS['primary'],
            self.WARNING: UI_TOKENS['warning'],
            self.QUESTION: UI_TOKENS['primary'],
            self.SUCCESS: UI_TOKENS['success'],
            self.ERROR: UI_TOKENS['danger']
        }

        type_labels = {
            self.INFO: "提示",
            self.WARNING: "注意",
            self.QUESTION: "确认",
            self.SUCCESS: "完成",
            self.ERROR: "错误"
        }

        accent = colors.get(self.msg_type, UI_TOKENS['primary'])
        radius_card = UI_TOKENS['radius_card']
        radius_control = UI_TOKENS['radius_control']
        radius_tag = UI_TOKENS['radius_tag']

        self.setStyleSheet(f"""
            QDialog {{
                background-color: transparent;
                border: none;
            }}
        """)

        main_container = QWidget()
        main_container.setObjectName("main_container")
        main_container.setStyleSheet(f"""
            QWidget#main_container {{
                background: {UI_TOKENS['surface']};
                border: 1px solid {UI_TOKENS['border']};
                border-radius: {radius_card}px;
            }}
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(main_container)

        container_layout = QVBoxLayout(main_container)
        container_layout.setContentsMargins(20, 18, 20, 18)
        container_layout.setSpacing(14)

        # 标题栏
        title_layout = QHBoxLayout()
        title_layout.setSpacing(10)

        badge_label = QLabel(type_labels.get(self.msg_type, "提示"))
        badge_label.setFont(app_font(9, QFont.DemiBold))
        badge_label.setStyleSheet(f"""
            QLabel {{
                color: {accent};
                background: {UI_TOKENS['surface_alt']};
                border: 1px solid {UI_TOKENS['border']};
                border-radius: {radius_tag}px;
                padding: 3px 8px;
            }}
        """)

        title_label = QLabel(title if title else "提示")
        title_label.setFont(app_font(13, QFont.DemiBold))
        title_label.setStyleSheet(f"""
            QLabel {{
                color: {UI_TOKENS['text']};
                background: transparent;
                border: none;
            }}
        """)

        close_btn = _make_close_button(self.reject)

        title_layout.addWidget(badge_label)
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        title_layout.addWidget(close_btn)

        container_layout.addLayout(title_layout)

        # 内容区域
        content_layout = QHBoxLayout()
        content_layout.setSpacing(14)

        icons = {
            self.INFO: "ℹ",
            self.WARNING: "",
            self.QUESTION: "？",
            self.SUCCESS: "",
            self.ERROR: ""
        }

        icon_label = QLabel(icons.get(self.msg_type, "ℹ"))
        icon_label.setFont(app_font(22, QFont.DemiBold))
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setFixedSize(48, 48)
        icon_label.setStyleSheet(f"""
            QLabel {{
                color: {accent};
                background: {UI_TOKENS['surface_alt']};
                border-radius: {radius_control}px;
                border: 1px solid {UI_TOKENS['border']};
            }}
        """)
        content_layout.addWidget(icon_label, 0, Qt.AlignTop)

        message_label = QLabel(message)
        message_label.setFont(app_font(10))
        message_label.setWordWrap(True)
        message_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        message_label.setStyleSheet(f"""
            QLabel {{
                color: {UI_TOKENS['text']};
                padding: 6px 0;
                background: transparent;
                border: none;
            }}
        """)
        content_layout.addWidget(message_label, 1)

        container_layout.addLayout(content_layout)

        # 按钮区域
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        if buttons is None:
            if self.msg_type == self.QUESTION:
                buttons = ["取消", "确定"]
            else:
                buttons = ["确定"]

        self.action_button_count = len(buttons)
        button_layout.setSpacing(10)

        for i, button_text in enumerate(buttons):
            btn = QPushButton()
            btn.setText(button_text)
            btn.setFont(app_font(10, QFont.DemiBold))
            btn.setMinimumSize(96, 36)
            btn.setCursor(Qt.PointingHandCursor)
            btn.update()

            if i == len(buttons) - 1:  # 主按钮
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {accent};
                        color: #FFFFFF;
                        border: 1px solid {accent};
                        border-radius: {radius_control}px;
                        padding: 8px 16px;
                        min-width: 96px;
                        min-height: 36px;
                    }}
                    QPushButton:hover {{
                        background: {self._shade(accent, darker=True)};
                        border-color: {self._shade(accent, darker=True)};
                    }}
                    QPushButton:pressed {{
                        background: {self._shade(accent, darker=True)};
                    }}
                """)
            else:  # 次要按钮
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {UI_TOKENS['surface']};
                        color: {UI_TOKENS['text']};
                        border: 1px solid {UI_TOKENS['border']};
                        border-radius: {radius_control}px;
                        padding: 8px 16px;
                        min-width: 96px;
                        min-height: 36px;
                    }}
                    QPushButton:hover {{
                        background: {UI_TOKENS['surface_alt']};
                        border-color: {UI_TOKENS['border_focus']};
                    }}
                    QPushButton:pressed {{
                        background: {UI_TOKENS['surface_alt']};
                    }}
                """)

            btn.clicked.connect(lambda checked, idx=i: self.button_clicked(idx))
            btn.setText(button_text)
            btn.repaint()

            button_layout.addWidget(btn)
            if i < len(buttons) - 1:
                button_layout.addSpacing(6)

        container_layout.addLayout(button_layout)

    def _hex_to_rgb(self, hex_color):
        """将十六进制颜色转换为RGB"""
        hex_color = hex_color.lstrip('#')
        return ', '.join(str(int(hex_color[i:i+2], 16)) for i in (0, 2, 4))

    def _shade(self, hex_color, darker=True):
        """根据 UI_TOKENS 返回对应主色的深/浅色，未知色回退到自身。"""
        primary = UI_TOKENS['primary']
        primary_hover = UI_TOKENS['primary_hover']
        color_map_darker = {
            primary: primary_hover,
            UI_TOKENS['warning']: '#D97706',
            UI_TOKENS['success']: '#059669',
            UI_TOKENS['danger']: '#DC2626',
        }
        color_map_lighter = {
            primary: '#6366F1',
            UI_TOKENS['warning']: '#FBBF24',
            UI_TOKENS['success']: '#34D399',
            UI_TOKENS['danger']: '#F87171',
        }
        if darker:
            return color_map_darker.get(hex_color, hex_color)
        return color_map_lighter.get(hex_color, hex_color)

    def _lighten_color(self, hex_color):
        """兼容旧调用：返回略浅的颜色"""
        return self._shade(hex_color, darker=False)

    def _darken_color(self, hex_color):
        """兼容旧调用：返回略深的颜色"""
        return self._shade(hex_color, darker=True)
    
    def center_on_screen(self):
        """将对话框显示在屏幕上方区域"""
        from PySide6.QtGui import QGuiApplication
        
        screen = QGuiApplication.primaryScreen()
        if screen:
            screen_geometry = screen.availableGeometry()
            dialog_geometry = self.geometry()
            
            # 水平居中
            x = (screen_geometry.width() - dialog_geometry.width()) // 2 + screen_geometry.x()
            # 垂直位置设在屏幕上方三分之一处
            y = screen_geometry.height() // 3 - dialog_geometry.height() // 2 + screen_geometry.y()
            
            # 确保不会超出屏幕顶部
            if y < screen_geometry.y():
                y = screen_geometry.y() + 50  # 距离顶部50像素
            
            self.move(x, y)
    
    def button_clicked(self, index):
        """按钮点击处理"""
        # 记录用户点击的按钮索引
        self.result_index = index
        
        if index == 0 and getattr(self, 'action_button_count', 1) > 1:
            # 多个按钮时，第一个是取消
            self.result = QDialog.Rejected
        else:
            # 单个按钮或最后一个按钮是确定
            self.result = QDialog.Accepted
        self.accept()
    
    @staticmethod
    def show_info(parent, title, message):
        """显示信息对话框"""
        dialog = CustomMessageBox(parent, title, message, CustomMessageBox.INFO)
        dialog.center_on_screen()  # 显示前居中
        return dialog.exec()
    
    @staticmethod
    def show_warning(parent, title, message):
        """显示警告对话框"""
        dialog = CustomMessageBox(parent, title, message, CustomMessageBox.WARNING)
        dialog.center_on_screen()  # 显示前居中
        return dialog.exec()
    
    @staticmethod
    def show_question(parent, title, message):
        """显示询问对话框"""
        dialog = CustomMessageBox(parent, title, message, CustomMessageBox.QUESTION, ["取消", "确定"])
        dialog.center_on_screen()  # 显示前居中
        result = dialog.exec()
        return QDialog.Accepted if dialog.result == QDialog.Accepted else QDialog.Rejected
    
    @staticmethod
    def show_success(parent, title, message):
        """显示成功对话框"""
        dialog = CustomMessageBox(parent, title, message, CustomMessageBox.SUCCESS)
        dialog.center_on_screen()  # 显示前居中
        return dialog.exec()
    
    @staticmethod
    def show_error(parent, title, message):
        """显示错误对话框"""
        dialog = CustomMessageBox(parent, title, message, CustomMessageBox.ERROR)
        dialog.center_on_screen()  # 显示前居中
        return dialog.exec()


class SettingsDialog(QDialog):
    """设置对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.setup_ui()
        self.apply_theme()  # 应用主题
        
    def setup_ui(self):
        """设置UI"""
        self.setWindowTitle("偏好设置")
        self.setFixedSize(780, 640)
        self.setModal(True)

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)

        self.setStyleSheet(f"""
            QDialog {{
                background-color: transparent;
            }}
        """)

        main_container = QWidget()
        main_container.setObjectName("settings_container")
        main_container.setStyleSheet(f"""
            QWidget#settings_container {{
                background: {UI_TOKENS['surface']};
                border: 1px solid {UI_TOKENS['border']};
                border-radius: {UI_TOKENS['radius_card']}px;
                margin: 8px;
            }}
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.addWidget(main_container)

        container_layout = QVBoxLayout(main_container)
        container_layout.setContentsMargins(24, 20, 24, 20)
        container_layout.setSpacing(14)

        # 标题栏
        title_layout = QHBoxLayout()
        title_label = QLabel("偏好设置")
        title_label.setFont(app_font(16, QFont.DemiBold))
        title_label.setStyleSheet(f"""
            QLabel {{
                color: {UI_TOKENS['text']};
                padding: 2px 0;
                background: transparent;
                border: none;
            }}
        """)

        close_btn = _make_close_button(self.reject)

        title_layout.addWidget(title_label)
        title_layout.addStretch()
        title_layout.addWidget(close_btn)

        container_layout.addLayout(title_layout)

        # 创建标签页：底部下划线风格，无边框、无背景，更克制
        from PySide6.QtWidgets import QTabWidget
        tab_widget = QTabWidget()
        tab_widget.setDocumentMode(True)
        tab_widget.setUsesScrollButtons(False)
        tab_widget.tabBar().setElideMode(Qt.ElideNone)
        tab_widget.tabBar().setExpanding(False)
        tab_widget.setStyleSheet(f"""
            QTabWidget::pane {{
                border: none;
                border-top: 1px solid {UI_TOKENS['border']};
                background: transparent;
                margin-top: -1px;
                padding-top: 12px;
            }}
            QTabBar {{
                background: transparent;
            }}
            QTabBar::tab {{
                background: transparent;
                border: none;
                border-bottom: 2px solid transparent;
                padding: 10px 18px;
                margin-right: 4px;
                color: {UI_TOKENS['text_muted']};
                min-width: 88px;
            }}
            QTabBar::tab:selected {{
                color: {UI_TOKENS['primary']};
                border-bottom-color: {UI_TOKENS['primary']};
            }}
            QTabBar::tab:hover {{
                color: {UI_TOKENS['text']};
            }}
        """)
        
        # 网络设置标签
        network_tab = self.create_network_tab()
        tab_widget.addTab(network_tab, "网络设置")
        
        # 界面设置标签
        ui_tab = self.create_ui_tab()
        tab_widget.addTab(ui_tab, "界面设置")
        
        # 下载设置标签
        download_tab = self.create_download_tab()
        tab_widget.addTab(download_tab, "下载设置")
        
        # 高级设置标签
        advanced_tab = self.create_advanced_tab()
        tab_widget.addTab(advanced_tab, "高级设置")
        
        container_layout.addWidget(tab_widget)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        # 恢复默认按钮
        reset_btn = QPushButton("恢复默认")
        reset_btn.setFont(app_font(10, QFont.DemiBold))
        reset_btn.setMinimumSize(112, 36)
        reset_btn.setCursor(Qt.PointingHandCursor)
        reset_btn.setStyleSheet(self._settings_secondary_button_style())
        reset_btn.clicked.connect(self.reset_to_default)

        # 保存按钮
        save_btn = QPushButton("保存并应用")
        save_btn.setFont(app_font(10, QFont.DemiBold))
        save_btn.setMinimumSize(112, 36)
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: {UI_TOKENS['primary']};
                color: #FFFFFF;
                border: 1px solid {UI_TOKENS['primary']};
                border-radius: {UI_TOKENS['radius_control']}px;
                padding: 8px 16px;
            }}
            QPushButton:hover {{
                background: {UI_TOKENS['primary_hover']};
                border-color: {UI_TOKENS['primary_hover']};
            }}
            QPushButton:pressed {{
                background: {UI_TOKENS['primary_active']};
                border-color: {UI_TOKENS['primary_active']};
            }}
        """)
        save_btn.clicked.connect(self.save_settings)
        
        button_layout.addWidget(reset_btn)
        button_layout.addWidget(save_btn)
        
        container_layout.addLayout(button_layout)
        
        # 居中显示
        self.center_on_screen()
        
        # 加载当前设置
        self.load_settings()

    def _settings_groupbox_style(self):
        """设置页分组框样式"""
        return f"""
            QGroupBox {{
                color: {UI_TOKENS['text']};
                border: 1px solid {UI_TOKENS['border']};
                border-radius: {UI_TOKENS['radius_card']}px;
                margin-top: 14px;
                padding: 18px 16px 16px 16px;
                background: {UI_TOKENS['surface']};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 14px;
                padding: 3px 8px;
                color: {UI_TOKENS['primary']};
                background: {UI_TOKENS['surface_alt']};
                border: 1px solid {UI_TOKENS['border']};
                border-radius: {UI_TOKENS['radius_tag']}px;
            }}
        """

    def _settings_label_style(self):
        """设置页标签样式"""
        return f"color: {UI_TOKENS['text']};"

    def _settings_line_edit_style(self):
        """设置页输入框样式"""
        return f"""
            QLineEdit {{
                background: {UI_TOKENS['surface']};
                border: 1px solid {UI_TOKENS['border']};
                border-radius: {UI_TOKENS['radius_control']}px;
                padding: 8px 12px;
                color: {UI_TOKENS['text']};
            }}
            QLineEdit:hover {{
                border-color: {UI_TOKENS['border_focus']};
            }}
            QLineEdit:focus {{
                border-color: {UI_TOKENS['primary']};
            }}
        """

    def _settings_combo_style(self, min_width=120):
        """设置页下拉框样式"""
        return f"""
            QComboBox {{
                background: {UI_TOKENS['surface']};
                border: 1px solid {UI_TOKENS['border']};
                border-radius: {UI_TOKENS['radius_control']}px;
                padding: 8px 12px;
                color: {UI_TOKENS['text']};
                min-width: {min_width}px;
            }}
            QComboBox:hover {{
                border-color: {UI_TOKENS['border_focus']};
            }}
            QComboBox:focus {{
                border-color: {UI_TOKENS['primary']};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid {UI_TOKENS['text_muted']};
                width: 0px;
                height: 0px;
                margin-right: 10px;
            }}
            QComboBox QAbstractItemView {{
                border: 1px solid {UI_TOKENS['border']};
                border-radius: {UI_TOKENS['radius_control']}px;
                background: {UI_TOKENS['surface']};
                selection-background-color: {UI_TOKENS['surface_alt']};
                selection-color: {UI_TOKENS['primary']};
                padding: 4px;
            }}
        """

    def _settings_spinbox_style(self, min_width=110):
        """设置页数字框样式"""
        return f"""
            QSpinBox {{
                background: {UI_TOKENS['surface']};
                border: 1px solid {UI_TOKENS['border']};
                border-radius: {UI_TOKENS['radius_control']}px;
                padding: 8px 12px;
                color: {UI_TOKENS['text']};
                min-width: {min_width}px;
            }}
            QSpinBox:hover {{
                border-color: {UI_TOKENS['border_focus']};
            }}
            QSpinBox:focus {{
                border-color: {UI_TOKENS['primary']};
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                width: 18px;
                border: none;
                background: transparent;
                margin-right: 4px;
            }}
            QSpinBox::up-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-bottom: 5px solid {UI_TOKENS['text_muted']};
                width: 0px;
                height: 0px;
            }}
            QSpinBox::down-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid {UI_TOKENS['text_muted']};
                width: 0px;
                height: 0px;
            }}
        """

    def _settings_checkbox_style(self):
        """设置页勾选框样式"""
        return f"""
            QCheckBox {{
                color: {UI_TOKENS['text']};
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border-radius: {UI_TOKENS['radius_tag']}px;
                border: 1px solid {UI_TOKENS['border']};
                background: {UI_TOKENS['surface']};
            }}
            QCheckBox::indicator:hover {{
                border-color: {UI_TOKENS['border_focus']};
            }}
            QCheckBox::indicator:checked {{
                background: {UI_TOKENS['primary']};
                border-color: {UI_TOKENS['primary']};
            }}
        """

    def _settings_slider_style(self):
        """设置页滑杆样式"""
        return f"""
            QSlider::groove:horizontal {{
                border: none;
                height: 4px;
                background: {UI_TOKENS['surface_alt']};
                border-radius: 2px;
            }}
            QSlider::sub-page:horizontal {{
                background: {UI_TOKENS['primary']};
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {UI_TOKENS['surface']};
                border: 2px solid {UI_TOKENS['primary']};
                width: 14px;
                height: 14px;
                margin: -6px 0;
                border-radius: 7px;
            }}
        """

    def _settings_secondary_button_style(self):
        """设置页次按钮样式"""
        return f"""
            QPushButton {{
                background: {UI_TOKENS['surface']};
                color: {UI_TOKENS['text']};
                border: 1px solid {UI_TOKENS['border']};
                border-radius: {UI_TOKENS['radius_control']}px;
                padding: 8px 14px;
            }}
            QPushButton:hover {{
                background: {UI_TOKENS['surface_alt']};
                border-color: {UI_TOKENS['border_focus']};
                color: {UI_TOKENS['primary']};
            }}
            QPushButton:pressed {{
                background: {UI_TOKENS['surface_alt']};
            }}
        """

    def _settings_warning_button_style(self):
        """设置页强调按钮样式"""
        return f"""
            QPushButton {{
                background: {UI_TOKENS['warning']};
                color: #FFFFFF;
                border: 1px solid {UI_TOKENS['warning']};
                border-radius: {UI_TOKENS['radius_control']}px;
                padding: 8px 14px;
            }}
            QPushButton:hover {{
                background: #D97706;
                border-color: #D97706;
            }}
            QPushButton:pressed {{
                background: #B45309;
                border-color: #B45309;
            }}
        """

    def _setup_form_layout(self, form_layout):
        """统一表单布局"""
        form_layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form_layout.setFormAlignment(Qt.AlignTop)
        form_layout.setHorizontalSpacing(18)
        form_layout.setVerticalSpacing(14)
        form_layout.setContentsMargins(10, 8, 10, 6)
    
    def create_network_tab(self):
        """创建网络设置标签"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(16)
        
        # 代理设置组
        proxy_group = QGroupBox("代理设置")
        proxy_group.setFont(app_font(12, QFont.Bold))
        proxy_group.setStyleSheet(self._settings_groupbox_style())
        proxy_layout = QVBoxLayout(proxy_group)
        proxy_layout.setContentsMargins(14, 10, 14, 12)
        proxy_layout.setSpacing(14)
        
        # 启用代理
        self.proxy_enabled = QCheckBox("启用代理服务器")
        self.proxy_enabled.setFont(app_font(11))
        self.proxy_enabled.setStyleSheet(self._settings_checkbox_style())
        proxy_layout.addWidget(self.proxy_enabled)
        
        # 代理类型和地址
        proxy_info_layout = QHBoxLayout()
        
        # 代理类型
        type_label = QLabel("代理类型:")
        type_label.setFont(app_font(10))
        type_label.setStyleSheet(self._settings_label_style())
        
        from PySide6.QtWidgets import QComboBox
        self.proxy_type = QComboBox()
        self.proxy_type.addItems(["HTTP", "SOCKS5"])
        self.proxy_type.setStyleSheet(self._settings_combo_style(92))
        
        proxy_info_layout.addWidget(type_label)
        proxy_info_layout.addWidget(self.proxy_type)
        proxy_info_layout.addStretch()
        
        proxy_layout.addLayout(proxy_info_layout)
        
        # 代理地址
        addr_layout = QHBoxLayout()
        addr_layout.setSpacing(10)
        
        addr_label = QLabel("代理地址:")
        addr_label.setFont(app_font(10))
        addr_label.setStyleSheet(self._settings_label_style())
        
        self.proxy_host = QLineEdit()
        self.proxy_host.setPlaceholderText("例如: 127.0.0.1")
        self.proxy_host.setStyleSheet(self._settings_line_edit_style())
        
        port_label = QLabel("端口:")
        port_label.setFont(app_font(10))
        port_label.setStyleSheet(self._settings_label_style())
        
        from PySide6.QtWidgets import QSpinBox
        self.proxy_port = QSpinBox()
        self.proxy_port.setRange(1, 65535)
        self.proxy_port.setValue(8080)
        self.proxy_port.setStyleSheet(self._settings_spinbox_style(84))
        
        addr_layout.addWidget(addr_label)
        addr_layout.addWidget(self.proxy_host, 2)
        addr_layout.addWidget(port_label)
        addr_layout.addWidget(self.proxy_port)
        
        proxy_layout.addLayout(addr_layout)
        
        layout.addWidget(proxy_group)
        
        # 连接设置组
        conn_group = QGroupBox("连接设置")
        conn_group.setFont(app_font(12, QFont.Bold))
        conn_group.setStyleSheet(self._settings_groupbox_style())
        conn_layout = QFormLayout(conn_group)
        self._setup_form_layout(conn_layout)
        
        # 超时时间
        timeout_label = QLabel("连接超时:")
        timeout_label.setFont(app_font(10))
        timeout_label.setStyleSheet(self._settings_label_style())
        
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 300)
        self.timeout_spin.setValue(30)
        self.timeout_spin.setSuffix(" 秒")
        self.timeout_spin.setStyleSheet(self._settings_spinbox_style(120))
        
        conn_layout.addRow(timeout_label, self.timeout_spin)
        
        # 重试次数
        retry_label = QLabel("重试次数:")
        retry_label.setFont(app_font(10))
        retry_label.setStyleSheet(self._settings_label_style())
        
        self.retry_spin = QSpinBox()
        self.retry_spin.setRange(0, 10)
        self.retry_spin.setValue(3)
        self.retry_spin.setSuffix(" 次")
        self.retry_spin.setStyleSheet(self._settings_spinbox_style(120))
        
        conn_layout.addRow(retry_label, self.retry_spin)
        
        layout.addWidget(conn_group)
        layout.addStretch()
        
        return tab
    
    def create_ui_tab(self):
        """创建界面设置标签"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(16)
        
        # 主题设置组
        theme_group = QGroupBox("主题设置")
        theme_group.setFont(app_font(12, QFont.Bold))
        theme_group.setStyleSheet(self._settings_groupbox_style())
        theme_layout = QFormLayout(theme_group)
        self._setup_form_layout(theme_layout)
        
        # 主题色选择
        color_layout = QHBoxLayout()
        
        color_label = QLabel("主题色彩:")
        color_label.setFont(app_font(10))
        color_label.setStyleSheet(self._settings_label_style())
        
        from PySide6.QtWidgets import QComboBox
        self.theme_color = QComboBox()
        self.theme_color.addItems(THEME_NAMES)
        self.theme_color.setStyleSheet(self._settings_combo_style(188))
        
        # 连接主题预览
        self.theme_color.currentIndexChanged.connect(self.preview_theme)
        
        theme_layout.addRow(color_label, self.theme_color)
        
        layout.addWidget(theme_group)
        
        # 显示设置组
        display_group = QGroupBox("显示设置")
        display_group.setFont(app_font(12, QFont.Bold))
        display_group.setStyleSheet(self._settings_groupbox_style())
        display_layout = QFormLayout(display_group)
        self._setup_form_layout(display_layout)
        
        # 字体大小
        font_label = QLabel("字体大小:")
        font_label.setFont(app_font(10))
        font_label.setStyleSheet(self._settings_label_style())
        
        self.font_size = QSpinBox()
        self.font_size.setRange(8, 24)
        self.font_size.setValue(12)
        self.font_size.setSuffix(" pt")
        self.font_size.setStyleSheet(self._settings_spinbox_style(120))
        
        display_layout.addRow(font_label, self.font_size)
        
        # 窗口透明度
        opacity_label = QLabel("窗口透明度:")
        opacity_label.setFont(app_font(10))
        opacity_label.setStyleSheet(self._settings_label_style())
        
        from PySide6.QtWidgets import QSlider
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(70, 100)
        self.opacity_slider.setValue(95)
        self.opacity_slider.setTickPosition(QSlider.TicksBelow)
        self.opacity_slider.setTickInterval(10)
        self.opacity_slider.setStyleSheet(self._settings_slider_style())
        
        display_layout.addRow(opacity_label, self.opacity_slider)
        
        layout.addWidget(display_group)
        layout.addStretch()
        
        return tab
    
    def create_download_tab(self):
        """创建下载设置标签"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(16)
        
        # 路径设置组
        path_group = QGroupBox("路径设置")
        path_group.setFont(app_font(12, QFont.Bold))
        path_group.setStyleSheet(self._settings_groupbox_style())
        path_layout = QVBoxLayout(path_group)
        path_layout.setContentsMargins(14, 10, 14, 12)
        path_layout.setSpacing(14)
        
        # 默认保存路径
        default_path_layout = QHBoxLayout()
        default_path_layout.setSpacing(10)
        
        path_label = QLabel("默认保存路径:")
        path_label.setFont(app_font(10))
        path_label.setStyleSheet(self._settings_label_style())
        
        self.default_path = QLineEdit()
        self.default_path.setPlaceholderText("选择默认的视频保存文件夹...")
        self.default_path.setText(os.path.expanduser("~/Downloads"))
        self.default_path.setStyleSheet(self._settings_line_edit_style())
        
        browse_btn = QPushButton("浏览")
        browse_btn.setFont(app_font(10))
        browse_btn.setMinimumWidth(96)
        browse_btn.setStyleSheet(self._settings_secondary_button_style())
        browse_btn.clicked.connect(self.browse_default_path)
        
        default_path_layout.addWidget(path_label)
        default_path_layout.addWidget(self.default_path, 2)
        default_path_layout.addWidget(browse_btn)
        
        path_layout.addLayout(default_path_layout)
        
        layout.addWidget(path_group)
        
        # 下载设置组
        download_group = QGroupBox("下载设置")
        download_group.setFont(app_font(12, QFont.Bold))
        download_group.setStyleSheet(self._settings_groupbox_style())
        download_layout = QFormLayout(download_group)
        self._setup_form_layout(download_layout)
        
        # 默认线程数
        threads_label = QLabel("默认线程数:")
        threads_label.setFont(app_font(10))
        threads_label.setStyleSheet(self._settings_label_style())
        
        self.default_threads = QSpinBox()
        self.default_threads.setRange(1, 32)
        self.default_threads.setValue(8)
        self.default_threads.setSuffix(" 个")
        self.default_threads.setStyleSheet(self._settings_spinbox_style(120))
        
        download_layout.addRow(threads_label, self.default_threads)
        
        # 文件命名规则
        naming_label = QLabel("文件命名:")
        naming_label.setFont(app_font(10))
        naming_label.setStyleSheet(self._settings_label_style())
        
        from PySide6.QtWidgets import QComboBox
        self.naming_rule = QComboBox()
        self.naming_rule.addItems([
            "任务名称", "时间戳", "任务名称+时间戳", "原始URL标题"
        ])
        self.naming_rule.setStyleSheet(self._settings_combo_style(170))
        
        download_layout.addRow(naming_label, self.naming_rule)
        
        layout.addWidget(download_group)
        layout.addStretch()
        
        return tab
    
    def create_advanced_tab(self):
        """创建高级设置标签"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(16)
        
        # 调试设置组
        debug_group = QGroupBox("调试设置")
        debug_group.setFont(app_font(12, QFont.Bold))
        debug_group.setStyleSheet(self._settings_groupbox_style())
        debug_layout = QVBoxLayout(debug_group)
        debug_layout.setContentsMargins(14, 10, 14, 12)
        debug_layout.setSpacing(14)
        
        # 启用调试日志
        self.debug_enabled = QCheckBox("启用详细调试日志")
        self.debug_enabled.setFont(app_font(11))
        self.debug_enabled.setStyleSheet(self._settings_checkbox_style())
        debug_layout.addWidget(self.debug_enabled)
        
        # 日志级别
        log_level_layout = QHBoxLayout()
        
        log_label = QLabel("日志级别:")
        log_label.setFont(app_font(10))
        log_label.setStyleSheet(self._settings_label_style())
        
        from PySide6.QtWidgets import QComboBox
        self.log_level = QComboBox()
        self.log_level.addItems(["ERROR", "WARNING", "INFO", "DEBUG"])
        self.log_level.setCurrentText("INFO")
        self.log_level.setStyleSheet(self._settings_combo_style(120))
        
        log_level_layout.addWidget(log_label)
        log_level_layout.addWidget(self.log_level)
        log_level_layout.addStretch()
        
        debug_layout.addLayout(log_level_layout)
        
        layout.addWidget(debug_group)
        
        # 缓存设置组
        cache_group = QGroupBox("缓存设置")
        cache_group.setFont(app_font(12, QFont.Bold))
        cache_group.setStyleSheet(self._settings_groupbox_style())
        cache_layout = QFormLayout(cache_group)
        self._setup_form_layout(cache_layout)
        
        # 缓存大小限制
        cache_label = QLabel("缓存大小限制:")
        cache_label.setFont(app_font(10))
        cache_label.setStyleSheet(self._settings_label_style())
        
        self.cache_size = QSpinBox()
        self.cache_size.setRange(10, 1000)
        self.cache_size.setValue(100)
        self.cache_size.setSuffix(" MB")
        self.cache_size.setStyleSheet(self._settings_spinbox_style(120))
        
        cache_layout.addRow(cache_label, self.cache_size)
        
        # 清理缓存按钮
        clear_cache_btn = QPushButton("清理缓存")
        clear_cache_btn.setFont(app_font(10))
        clear_cache_btn.setStyleSheet(self._settings_warning_button_style())
        clear_cache_btn.clicked.connect(self.clear_cache)
        
        cache_layout.addRow(QLabel(""), clear_cache_btn)
        
        layout.addWidget(cache_group)
        layout.addStretch()
        
        return tab
    
    def browse_default_path(self):
        """浏览默认保存路径"""
        from PySide6.QtWidgets import QFileDialog
        
        folder = QFileDialog.getExistingDirectory(
            self, 
            "选择默认保存文件夹", 
            self.default_path.text()
        )
        
        if folder:
            self.default_path.setText(folder)
    
    def clear_cache(self):
        """清理缓存"""
        reply = CustomMessageBox.show_question(
            self,
            "清理缓存",
            "确定要清理所有缓存文件吗？\n\n这将删除临时文件和下载缓存，可释放磁盘空间，但可能影响后续下载速度。"
        )
        
        if reply == QDialog.Accepted:
            # 这里添加清理缓存的逻辑
            CustomMessageBox.show_success(
                self,
                "清理完成",
                "缓存文件已清理。"
            )
    
    def load_settings(self):
        """加载当前设置"""
        settings_file = get_settings_path()
        
        try:
            if os.path.exists(settings_file):
                with open(settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                
                # 加载网络设置
                network = settings.get('network', {})
                self.proxy_enabled.setChecked(network.get('proxy_enabled', False))
                proxy_type = network.get('proxy_type', 'HTTP')
                if proxy_type in ['HTTP', 'SOCKS5']:
                    self.proxy_type.setCurrentText(proxy_type)
                self.proxy_host.setText(network.get('proxy_host', ''))
                self.proxy_port.setValue(network.get('proxy_port', 8080))
                self.timeout_spin.setValue(network.get('timeout', 30))
                self.retry_spin.setValue(network.get('retry_count', 3))
                
                # 加载界面设置
                ui = settings.get('ui', {})
                self.theme_color.setCurrentIndex(ui.get('theme_color', 0))
                self.font_size.setValue(ui.get('font_size', 12))
                self.opacity_slider.setValue(ui.get('opacity', 95))
                
                # 加载下载设置
                download = settings.get('download', {})
                self.default_path.setText(download.get('default_path', os.path.expanduser("~/Downloads")))
                self.default_threads.setValue(download.get('default_threads', 8))
                self.naming_rule.setCurrentIndex(download.get('naming_rule', 0))
                
                # 加载高级设置
                advanced = settings.get('advanced', {})
                self.debug_enabled.setChecked(advanced.get('debug_enabled', False))
                log_level = advanced.get('log_level', 'INFO')
                if log_level in ['ERROR', 'WARNING', 'INFO', 'DEBUG']:
                    self.log_level.setCurrentText(log_level)
                self.cache_size.setValue(advanced.get('cache_size', 100))
                
        except Exception as e:
            print(f"加载设置失败: {e}")
            # 使用默认值
    
    def save_settings(self):
        """保存设置"""
        # 收集所有设置
        settings = {
            'network': {
                'proxy_enabled': self.proxy_enabled.isChecked(),
                'proxy_type': self.proxy_type.currentText(),
                'proxy_host': self.proxy_host.text(),
                'proxy_port': self.proxy_port.value(),
                'timeout': self.timeout_spin.value(),
                'retry_count': self.retry_spin.value()
            },
            'ui': {
                'theme_color': self.theme_color.currentIndex(),
                'font_size': self.font_size.value(),
                'opacity': self.opacity_slider.value()
            },
            'download': {
                'default_path': self.default_path.text(),
                'default_threads': self.default_threads.value(),
                'naming_rule': self.naming_rule.currentIndex()
            },
            'advanced': {
                'debug_enabled': self.debug_enabled.isChecked(),
                'log_level': self.log_level.currentText(),
                'cache_size': self.cache_size.value()
            }
        }
        
        # 保存设置到配置文件
        settings_file = get_settings_path()
        
        try:
            with open(settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
            
            CustomMessageBox.show_success(
                self,
                "保存成功",
                "设置已成功保存。\n\n部分设置将在重启应用后生效。"
            )
            
            # 应用部分设置到主窗口
            if self.main_window:
                self.apply_settings_to_main_window(settings)
            
            self.accept()
            
        except Exception as e:
            CustomMessageBox.show_error(
                self,
                "保存失败",
                f"保存设置时出现错误：\n{str(e)}\n\n请检查文件权限或磁盘空间。"
            )
    
    def apply_settings_to_main_window(self, settings):
        """将设置应用到主窗口"""
        # 应用透明度设置
        opacity = settings['ui']['opacity'] / 100.0
        self.main_window.setWindowOpacity(opacity)
        
        # 应用主题设置
        theme_index = settings['ui']['theme_color']
        self.main_window.apply_theme(theme_index)
        
        # 应用下载设置
        if hasattr(self.main_window, 'threads_spin'):
            self.main_window.threads_spin.setValue(settings['download']['default_threads'])
        
        if hasattr(self.main_window, 'output_input'):
            default_path = settings['download']['default_path']
            if default_path and os.path.exists(default_path):
                self.main_window.output_input.setText(default_path)
        
        # 更新状态栏
        if hasattr(self.main_window, 'status_bar'):
            self.main_window.status_bar.showMessage("设置已更新并应用")
    
    def reset_to_default(self):
        """恢复默认设置"""
        reply = CustomMessageBox.show_question(
            self,
            "恢复默认",
            "确定要恢复所有设置到默认状态吗？\n\n这将清除当前的个性化配置。"
        )
        
        if reply == QDialog.Accepted:
            # 重置所有设置为默认值
            self.proxy_enabled.setChecked(False)
            self.proxy_type.setCurrentIndex(0)
            self.proxy_host.clear()
            self.proxy_port.setValue(8080)
            self.timeout_spin.setValue(30)
            self.retry_spin.setValue(3)
            
            self.theme_color.setCurrentIndex(0)
            self.font_size.setValue(12)
            self.opacity_slider.setValue(95)
            
            self.default_path.setText(os.path.expanduser("~/Downloads"))
            self.default_threads.setValue(8)
            self.naming_rule.setCurrentIndex(0)
            
            self.debug_enabled.setChecked(False)
            self.log_level.setCurrentText("INFO")
            self.cache_size.setValue(100)
            
            CustomMessageBox.show_success(
                self,
                "恢复成功",
                "所有设置已恢复到默认状态。"
            )
    
    def preview_theme(self, theme_index):
        """实时预览主题"""
        if self.main_window and hasattr(self.main_window, 'apply_theme'):
            self.main_window.apply_theme(theme_index)
            # 同时更新设置对话框的主题
            self.apply_theme()
    
    def get_current_theme(self):
        """获取当前主题"""
        if self.main_window and hasattr(self.main_window, 'current_theme_data'):
            return self.main_window.current_theme_data
        # 默认亮色主题
        return {
            'primary': '#667eea',
            'text_color': '#2c3e50',
            'input_bg': 'white',
            'input_border': '#e5e7eb',
            'bg_start': '#fef7ff',
            'bg_mid': '#f0f9ff',
            'is_dark': False
        }
    
    def apply_theme(self):
        """应用主题到设置对话框"""
        theme = self.get_current_theme()
        is_dark = theme.get('is_dark', False)
        surface = theme.get('groupbox_bg', UI_TOKENS['surface'])
        text = theme.get('text_color', UI_TOKENS['text'])
        border = theme.get('input_border', UI_TOKENS['border'])
        primary = theme.get('primary', UI_TOKENS['primary'])
        overlay = 'rgba(15, 23, 42, 0.35)' if is_dark else 'rgba(15, 23, 42, 0.18)'

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {overlay};
            }}
        """)

        main_container = self.findChild(QWidget, "settings_container")
        if main_container:
            main_container.setStyleSheet(f"""
                QWidget#settings_container {{
                    background: {surface};
                    border: 1px solid {border};
                    border-radius: {UI_TOKENS['radius_card']}px;
                    margin: 8px;
                }}
            """)

        title_labels = self.findChildren(QLabel)
        for label in title_labels:
            if "偏好设置" in label.text():
                label.setStyleSheet(f"""
                    QLabel {{
                        color: {text};
                        padding: 2px 0;
                        background: transparent;
                        border: none;
                    }}
                """)
                break

        for btn in self.findChildren(QPushButton):
            if btn.text() == "":
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: transparent;
                        color: {UI_TOKENS['text_muted']};
                        border: 1px solid {border};
                        border-radius: {UI_TOKENS['radius_tag']}px;
                    }}
                    QPushButton:hover {{
                        background: {UI_TOKENS['surface_alt']};
                        color: {text};
                    }}
                """)
                break

        tab_widget = self.findChild(QTabWidget)
        if tab_widget:
            tab_widget.setStyleSheet(f"""
                QTabWidget::pane {{
                    border: 1px solid {border};
                    border-radius: {UI_TOKENS['radius_card']}px;
                    background: {surface};
                    margin-top: 8px;
                    top: -1px;
                }}
                QTabBar::tab {{
                    background: {UI_TOKENS['surface_alt']};
                    border: 1px solid {border};
                    border-bottom: none;
                    border-radius: {UI_TOKENS['radius_control']}px {UI_TOKENS['radius_control']}px 0 0;
                    padding: 10px 16px;
                    margin-right: 4px;
                    color: {UI_TOKENS['text_muted']};
                    min-width: 96px;
                }}
                QTabBar::tab:selected {{
                    background: {surface};
                    border-color: {primary};
                    color: {primary};
                    border-bottom: 2px solid {surface};
                }}
                QTabBar::tab:hover {{
                    background: {surface};
                    border-color: {UI_TOKENS['border_focus']};
                }}
            """)

        for groupbox in self.findChildren(QGroupBox):
            groupbox.setStyleSheet(f"""
                QGroupBox {{
                    color: {text};
                    border: 1px solid {border};
                    border-radius: {UI_TOKENS['radius_card']}px;
                    margin-top: 14px;
                    padding: 18px 16px 16px 16px;
                    background: {surface};
                }}
                QGroupBox::title {{
                    subcontrol-origin: margin;
                    subcontrol-position: top left;
                    left: 14px;
                    padding: 3px 8px;
                    color: {primary};
                    background: {UI_TOKENS['surface_alt']};
                    border: 1px solid {border};
                    border-radius: {UI_TOKENS['radius_tag']}px;
                }}
            """)
    
    def _hex_to_rgb(self, hex_color):
        """将十六进制颜色转换为RGB"""
        hex_color = hex_color.lstrip('#')
        return ', '.join(str(int(hex_color[i:i+2], 16)) for i in (0, 2, 4))
    
    def center_on_screen(self):
        """将对话框居中显示"""
        from PySide6.QtGui import QGuiApplication
        
        screen = QGuiApplication.primaryScreen()
        if screen:
            screen_geometry = screen.availableGeometry()
            dialog_geometry = self.geometry()
            
            x = (screen_geometry.width() - dialog_geometry.width()) // 2 + screen_geometry.x()
            y = (screen_geometry.height() - dialog_geometry.height()) // 2 + screen_geometry.y()
            
            self.move(x, y)


class HeadersDialog(QDialog):
    """请求头配置对话框"""
    
    def __init__(self, parent=None, current_headers=None):
        super().__init__(parent)
        self.current_headers = current_headers or {}
        self.setup_ui()
    
    def setup_ui(self):
        self.setWindowTitle("请求头配置")
        self.setMinimumSize(600, 400)

        self.setStyleSheet(f"""
            QDialog {{
                background: {UI_TOKENS['bg']};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        info_label = QLabel("请输入自定义请求头（JSON 格式或每行一个键值对）")
        info_label.setFont(app_font(10, QFont.DemiBold))
        info_label.setStyleSheet(f"color: {UI_TOKENS['text']}; background: transparent; border: none;")
        layout.addWidget(info_label)

        example_text = '''示例格式：
{
    "referer": "https://example.com/",
    "origin": "https://example.com",
    "sec-ch-ua": "\\"Not;A=Brand\\";v=\\"99\\", \\"Google Chrome\\";v=\\"139\\"",
    "sec-fetch-site": "cross-site"
}

或者每行一个：
referer: https://example.com/
origin: https://example.com'''

        example_label = QLabel(example_text)
        example_label.setFont(QFont("Consolas", 9))
        example_label.setStyleSheet(f"""
            background: {UI_TOKENS['surface_alt']};
            padding: 12px;
            border-radius: {UI_TOKENS['radius_control']}px;
            color: {UI_TOKENS['text_muted']};
            border: 1px solid {UI_TOKENS['border']};
        """)
        layout.addWidget(example_label)

        self.text_edit = QPlainTextEdit()
        self.text_edit.setFont(QFont("Consolas", 10))
        self.text_edit.setPlainText(self._headers_to_text())
        self.text_edit.setStyleSheet(f"""
            QPlainTextEdit {{
                border: 1px solid {UI_TOKENS['border']};
                border-radius: {UI_TOKENS['radius_control']}px;
                padding: 12px;
                background: {UI_TOKENS['surface']};
                color: {UI_TOKENS['text']};
                selection-background-color: {UI_TOKENS['primary']};
                selection-color: #FFFFFF;
                font-family: "Consolas";
            }}
            QPlainTextEdit:focus {{
                border-color: {UI_TOKENS['primary']};
            }}
        """)
        layout.addWidget(self.text_edit)

        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            parent=self
        )
        button_box.setStyleSheet(f"""
            QDialogButtonBox QPushButton {{
                background: {UI_TOKENS['primary']};
                color: #FFFFFF;
                border: 1px solid {UI_TOKENS['primary']};
                border-radius: {UI_TOKENS['radius_control']}px;
                padding: 8px 16px;
                min-width: 80px;
                min-height: 32px;
                margin: 2px;
            }}
            QDialogButtonBox QPushButton:hover {{
                background: {UI_TOKENS['primary_hover']};
                border-color: {UI_TOKENS['primary_hover']};
            }}
            QDialogButtonBox QPushButton:pressed {{
                background: {UI_TOKENS['primary_active']};
                border-color: {UI_TOKENS['primary_active']};
            }}
        """)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def _headers_to_text(self):
        """将请求头字典转换为文本"""
        if not self.current_headers:
            return ""
        
        import json
        return json.dumps(self.current_headers, indent=2, ensure_ascii=False)
    
    def get_headers(self):
        """获取用户输入的请求头"""
        text = self.text_edit.toPlainText().strip()
        if not text:
            return {}
        
        try:
            # 尝试解析为JSON
            import json
            return json.loads(text)
        except json.JSONDecodeError:
            # 尝试按行解析
            headers = {}
            for line in text.split('\n'):
                line = line.strip()
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip().strip('"').strip("'")
                    value = value.strip().rstrip(',').strip().strip('"').strip("'")
                    if key:
                        headers[key] = value
            return headers


class SearchSignals(QObject):
    """搜索信号类"""
    search_completed = Signal(list, str)
    search_error = Signal(str)
    extraction_completed = Signal(dict)
    show_route_dialog = Signal(dict, str, list)  # (routes, title, result_container)
    log_message = Signal(str, str)  # message, thread_name


class RouteSelectionDialog(QDialog):
    """线路选择对话框"""
    
    def __init__(self, routes_data, video_title, parent=None):
        """
        初始化线路选择对话框
        :param routes_data: 线路数据 {线路名: {"total": 集数, "episodes": [(集名, URL), ...]}}
        :param video_title: 视频标题
        :param parent: 父窗口
        """
        super().__init__(parent)
        self.routes_data = routes_data
        self.video_title = video_title
        self.selected_route = None
        self.setup_ui()
    
    def setup_ui(self):
        """设置UI"""
        self.setWindowTitle(f"选择播放线路 - {self.video_title}")
        self.setMinimumSize(600, 400)
        self.setModal(True)

        self.setStyleSheet(f"""
            QDialog {{
                background: {UI_TOKENS['bg']};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        title_label = QLabel(self.video_title)
        title_label.setFont(app_font(14, QFont.DemiBold))
        title_label.setStyleSheet(f"color: {UI_TOKENS['text']}; padding: 4px 0; background: transparent; border: none;")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        info_label = QLabel("请选择一个播放线路，将提取该线路的所有剧集：")
        info_label.setFont(app_font(10))
        info_label.setStyleSheet(f"color: {UI_TOKENS['text_muted']}; padding: 2px 0; background: transparent; border: none;")
        layout.addWidget(info_label)

        self.route_list = QTableWidget()
        self.route_list.setColumnCount(3)
        self.route_list.setHorizontalHeaderLabels(["线路名称", "集数", "状态"])
        self.route_list.horizontalHeader().setStretchLastSection(True)
        self.route_list.setSelectionBehavior(QTableWidget.SelectRows)
        self.route_list.setSelectionMode(QTableWidget.SingleSelection)
        self.route_list.setEditTriggers(QTableWidget.NoEditTriggers)
        self.route_list.setAlternatingRowColors(True)
        self.route_list.setStyleSheet(f"""
            QTableWidget {{
                border: 1px solid {UI_TOKENS['border']};
                border-radius: {UI_TOKENS['radius_control']}px;
                background: {UI_TOKENS['surface']};
                gridline-color: {UI_TOKENS['border']};
            }}
            QTableWidget::item {{
                padding: 8px;
                color: {UI_TOKENS['text']};
            }}
            QTableWidget::item:selected {{
                background: {UI_TOKENS['primary']};
                color: #FFFFFF;
            }}
            QHeaderView::section {{
                background: {UI_TOKENS['surface_alt']};
                padding: 8px;
                border: none;
                border-bottom: 1px solid {UI_TOKENS['border']};
                color: {UI_TOKENS['text']};
            }}
        """)

        self.route_list.setRowCount(len(self.routes_data))
        for idx, (route_name, route_info) in enumerate(self.routes_data.items()):
            name_item = QTableWidgetItem(route_name)
            name_item.setFont(app_font(10, QFont.DemiBold))
            self.route_list.setItem(idx, 0, name_item)

            total_item = QTableWidgetItem(f"{route_info['total']} 集")
            total_item.setTextAlignment(Qt.AlignCenter)
            self.route_list.setItem(idx, 1, total_item)

            episodes_count = len(route_info['episodes'])
            if episodes_count == route_info['total']:
                status = "完整"
                status_color = UI_TOKENS['success']
            elif episodes_count > 0:
                status = f"部分 ({episodes_count} 集)"
                status_color = UI_TOKENS['warning']
            else:
                status = "无剧集"
                status_color = UI_TOKENS['danger']

            status_item = QTableWidgetItem(status)
            status_item.setTextAlignment(Qt.AlignCenter)
            status_item.setForeground(QColor(status_color))
            self.route_list.setItem(idx, 2, status_item)

        self.route_list.setColumnWidth(0, 250)
        self.route_list.setColumnWidth(1, 100)

        self.route_list.itemDoubleClicked.connect(self.accept)
        layout.addWidget(self.route_list)

        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = ModernButton("取消")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        ok_btn = ModernButton("确定提取", primary=True)
        ok_btn.clicked.connect(self.accept)
        button_layout.addWidget(ok_btn)

        layout.addLayout(button_layout)

        if self.route_list.rowCount() > 0:
            self.route_list.selectRow(0)
    
    def accept(self):
        """确认选择"""
        selected_row = self.route_list.currentRow()
        print(f"线路选择对话框 - 当前选中行: {selected_row}")
        
        if selected_row >= 0:
            route_keys = list(self.routes_data.keys())
            print(f"   可用线路: {route_keys}")
            self.selected_route = route_keys[selected_row]
            print(f"确认选择线路: {self.selected_route}")
        else:
            print("未选择任何线路")
            self.selected_route = None
        
        super().accept()
    
    def get_selected_route(self):
        """获取选中的线路"""
        print(f"返回选中的线路: {self.selected_route}")
        return self.selected_route


class M3u8SearchDialog(QDialog):
    """M3U8搜索对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.search_engine = None
        self.search_results = []
        self.m3u8_results = {}
        self.search_threads = []
        
        # 创建信号对象
        self.signals = SearchSignals()
        self.signals.search_completed.connect(self._on_search_complete)
        self.signals.search_error.connect(self._on_search_error)
        self.signals.extraction_completed.connect(self._on_extraction_complete)
        self.signals.show_route_dialog.connect(self._on_show_route_dialog)
        self.signals.log_message.connect(self._append_log_line)

        # 线路选择结果（用于线程间传递）
        self.route_selection_result = None
        self.route_selection_event = None
        self._log_stdout = None
        self._log_stderr = None
        self._orig_stdout = None
        self._orig_stderr = None
        self._log_handler = None

        self.setup_ui()
        # 初始化时根据默认搜索引擎设置类型选择框的显示状态
        self.update_type_visibility()
        # 先显示窗口，再异步初始化引擎，避免点击「搜索」后卡住几秒才弹出。
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self.init_search_engine)
        QTimer.singleShot(0, self._install_log_capture)

    def setup_ui(self):
        """设置UI界面"""
        self.setWindowTitle("M3U8 搜索器")
        self.setMinimumSize(1100, 700)
        self.setModal(False)  # 非模态对话框
        
        self.setStyleSheet(f"""
            QDialog {{
                background: {UI_TOKENS['bg']};
            }}
        """)
        
        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # 标题
        title_label = QLabel("M3U8 搜索器")
        title_label.setFont(app_font(18, QFont.Bold))
        title_label.setStyleSheet(f"color: {UI_TOKENS['text']}; padding: 4px 0;")
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)
        
        # 搜索区域
        search_group = QGroupBox("搜索设置")
        search_group.setFont(app_font(12, QFont.Bold))
        search_group.setStyleSheet(f"""
            QGroupBox {{
                color: {UI_TOKENS['text']};
                padding-top: 14px;
                border: 1px solid {UI_TOKENS['border']};
                border-radius: {UI_TOKENS['radius_card']}px;
                background: {UI_TOKENS['surface']};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 14px;
                padding: 4px 8px;
                background: {UI_TOKENS['surface_alt']};
                border-radius: {UI_TOKENS['radius_tag']}px;
            }}
        """)
        
        search_layout = QVBoxLayout(search_group)
        search_layout.setSpacing(10)
        
        # 关键词输入
        keyword_layout = QHBoxLayout()
        keyword_label = QLabel("关键词")
        keyword_label.setFont(app_font(10, QFont.Bold))
        keyword_label.setStyleSheet(f"color: {UI_TOKENS['text_muted']};")

        self.keyword_input = QLineEdit()
        self.keyword_input.setPlaceholderText("请输入要搜索的影视名称...")
        self.keyword_input.returnPressed.connect(self.start_search)
        self.keyword_input.setStyleSheet(f"""
            QLineEdit {{
                padding: 8px 12px;
                border: 1px solid {UI_TOKENS['border']};
                border-radius: {UI_TOKENS['radius_control']}px;
                background: {UI_TOKENS['surface']};
                color: {UI_TOKENS['text']};
            }}
            QLineEdit:focus {{
                border-color: {UI_TOKENS['primary']};
            }}
        """)
        
        keyword_layout.addWidget(keyword_label)
        keyword_layout.addWidget(self.keyword_input, 3)
        search_layout.addLayout(keyword_layout)
        
        # 类型选择 / NCat Cookie 输入（根据搜索引擎切换）
        type_layout = QHBoxLayout()
        
        # 爱瓜影视的类型选择
        self.type_label = QLabel("类型")
        self.type_label.setFont(app_font(10, QFont.Bold))
        self.type_label.setStyleSheet(f"color: {UI_TOKENS['text_muted']};")

        self.type_combo = QComboBox()
        self.type_combo.addItems(["电影", "电视剧/动漫/综艺"])
        self.type_combo.setStyleSheet(f"""
            QComboBox {{
                padding: 8px 12px;
                border: 1px solid {UI_TOKENS['border']};
                border-radius: {UI_TOKENS['radius_control']}px;
                background: {UI_TOKENS['surface']};
                color: {UI_TOKENS['text']};
            }}
            QComboBox:focus {{
                border-color: {UI_TOKENS['primary']};
            }}
        """)

        self.ncat_cookie_label = QLabel("NCat Cookie")
        self.ncat_cookie_label.setFont(app_font(10, QFont.Bold))
        self.ncat_cookie_label.setStyleSheet(f"color: {UI_TOKENS['text_muted']};")

        self.ncat_cookie_input = QLineEdit()
        self.ncat_cookie_input.setPlaceholderText("请输入cdndefend_js_cookie值（从浏览器Cookie中获取）...")
        self.ncat_cookie_input.setStyleSheet(f"""
            QLineEdit {{
                padding: 8px 12px;
                border: 1px solid {UI_TOKENS['border']};
                border-radius: {UI_TOKENS['radius_control']}px;
                background: {UI_TOKENS['surface']};
                color: {UI_TOKENS['text']};
                font-family: 'Consolas', 'Monaco', monospace;
            }}
            QLineEdit:focus {{
                border-color: {UI_TOKENS['primary']};
            }}
        """)

        self.search_btn = ModernButton("开始搜索", primary=True)
        self.search_btn.clicked.connect(self.start_search)
        
        type_layout.addWidget(self.type_label)
        type_layout.addWidget(self.type_combo, 2)
        type_layout.addWidget(self.ncat_cookie_label)
        type_layout.addWidget(self.ncat_cookie_input, 2)
        type_layout.addStretch()
        type_layout.addWidget(self.search_btn)
        search_layout.addLayout(type_layout)
        
        # 搜索引擎选择
        engine_layout = QHBoxLayout()
        engine_label = QLabel("内容渠道")
        engine_label.setFont(app_font(10, QFont.Bold))
        engine_label.setStyleSheet(f"color: {UI_TOKENS['text_muted']};")

        self.engine_combo = QComboBox()
        self.engine_combo.addItems(SEARCH_CHANNELS)
        self.engine_combo.currentIndexChanged.connect(self.on_engine_changed)
        self.engine_combo.setStyleSheet(f"""
            QComboBox {{
                padding: 8px 12px;
                border: 1px solid {UI_TOKENS['border']};
                border-radius: {UI_TOKENS['radius_control']}px;
                background: {UI_TOKENS['surface']};
                color: {UI_TOKENS['text']};
            }}
            QComboBox:focus {{
                border-color: {UI_TOKENS['primary']};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
        """)
        
        engine_layout.addWidget(engine_label)
        engine_layout.addWidget(self.engine_combo, 2)
        engine_layout.addStretch()
        search_layout.addLayout(engine_layout)
        
        main_layout.addWidget(search_group)
        
        # 结果显示区域
        results_group = QGroupBox("搜索结果")
        results_group.setFont(app_font(12, QFont.Bold))
        results_group.setStyleSheet(f"""
            QGroupBox {{
                color: {UI_TOKENS['text']};
                padding-top: 14px;
                border: 1px solid {UI_TOKENS['border']};
                border-radius: {UI_TOKENS['radius_card']}px;
                background: {UI_TOKENS['surface']};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 14px;
                padding: 4px 8px;
                background: {UI_TOKENS['surface_alt']};
                border-radius: {UI_TOKENS['radius_tag']}px;
            }}
        """)

        results_layout = QVBoxLayout(results_group)

        panel_style = f"""
            QTextEdit, QPlainTextEdit {{
                border: 1px solid {UI_TOKENS['border']};
                border-radius: {UI_TOKENS['radius_control']}px;
                padding: 10px;
                background: {UI_TOKENS['surface']};
                color: {UI_TOKENS['text']};
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 11px;
            }}
        """

        results_splitter = QSplitter(Qt.Horizontal)
        results_splitter.setChildrenCollapsible(False)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)
        left_title = QLabel("结果")
        left_title.setStyleSheet(f"color: {UI_TOKENS['text_muted']}; font-weight: 600;")
        self.results_text = QTextEdit()
        self.results_text.setPlaceholderText("搜索结果将在这里显示...")
        self.results_text.setStyleSheet(panel_style)
        left_layout.addWidget(left_title)
        left_layout.addWidget(self.results_text)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)
        right_header = QHBoxLayout()
        right_title = QLabel("实时日志")
        right_title.setStyleSheet(f"color: {UI_TOKENS['text_muted']}; font-weight: 600;")
        self.clear_log_btn = ModernButton("清空日志")
        self.clear_log_btn.clicked.connect(self.clear_logs)
        right_header.addWidget(right_title)
        right_header.addStretch()
        right_header.addWidget(self.clear_log_btn)
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setPlaceholderText("搜索/提取过程日志会实时显示在这里...")
        self.log_text.setStyleSheet(log_console_stylesheet(border=UI_TOKENS['border'], radius=UI_TOKENS['radius_card']))
        right_layout.addLayout(right_header)
        right_layout.addWidget(self.log_text)

        results_splitter.addWidget(left_panel)
        results_splitter.addWidget(right_panel)
        results_splitter.setStretchFactor(0, 1)
        results_splitter.setStretchFactor(1, 1)
        results_splitter.setSizes([520, 520])
        results_layout.addWidget(results_splitter)

        action_layout = QHBoxLayout()

        self.extract_selected_btn = ModernButton("提取选中")
        self.extract_selected_btn.clicked.connect(self.extract_selected)
        self.extract_selected_btn.setEnabled(False)

        self.extract_all_btn = ModernButton("提取全部", primary=True)
        self.extract_all_btn.clicked.connect(self.extract_all)
        self.extract_all_btn.setEnabled(False)

        self.clear_btn = ModernButton("清空结果")
        self.clear_btn.clicked.connect(self.clear_results)

        self.copy_btn = ModernButton("复制结果")
        self.copy_btn.clicked.connect(self.copy_results)
        self.copy_btn.setEnabled(False)
        
        action_layout.addWidget(self.extract_selected_btn)
        action_layout.addWidget(self.extract_all_btn)
        action_layout.addStretch()
        action_layout.addWidget(self.copy_btn)
        action_layout.addWidget(self.clear_btn)
        
        results_layout.addLayout(action_layout)
        main_layout.addWidget(results_group)
        
        # 状态栏
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet(f"""
            QLabel {{
                color: {UI_TOKENS['text_muted']};
                padding: 8px 12px;
                background: {UI_TOKENS['surface_alt']};
                border-radius: {UI_TOKENS['radius_tag']}px;
                border: 1px solid {UI_TOKENS['border']};
            }}
        """)
        main_layout.addWidget(self.status_label)
    
    def init_search_engine(self):
        """初始化搜索引擎"""
        try:
            proxy_config = self.get_proxy_config()
            engine_type = self.engine_combo.currentText()
            self.search_engine = create_search_engine(
                engine_type,
                proxy_config=proxy_config,
                ncat_cookie=self.ncat_cookie_input.text().strip(),
                iyf_cookie=self.ncat_cookie_input.text().strip(),
            )
            self.update_status(f"{engine_type} 搜索引擎初始化完成")
        except Exception as e:
            print(f"搜索引擎初始化失败: {e}")
            import traceback
            traceback.print_exc()
            self.update_status(f"搜索引擎初始化失败: {e}")
    
    def update_type_visibility(self):
        """根据搜索引擎类型更新UI组件的可见性"""
        engine_type = self.engine_combo.currentText()
        input_mode = get_channel_input_mode(engine_type)
        show_type = input_mode == CHANNEL_INPUT_TYPE
        show_cookie = input_mode == CHANNEL_INPUT_COOKIE
        if engine_type == IYF_CHANNEL:
            self.ncat_cookie_label.setText("爱壹帆 Cookie（可选）")
            self.ncat_cookie_input.setPlaceholderText("可留空：搜索时会用 DrissionPage 自动过盾；也可粘贴完整 Cookie")
        else:
            self.ncat_cookie_label.setText("NCat Cookie")
            self.ncat_cookie_input.setPlaceholderText("请输入cdndefend_js_cookie值（从浏览器Cookie中获取）...")
        self.type_label.setVisible(show_type)
        self.type_combo.setVisible(show_type)
        self.ncat_cookie_label.setVisible(show_cookie)
        self.ncat_cookie_input.setVisible(show_cookie)
    
    def on_engine_changed(self):
        """搜索引擎改变时重新初始化"""
        engine_type = self.engine_combo.currentText()
        print(f"搜索引擎切换到: {engine_type}")
        
        # 更新类型选择框的可见性
        self.update_type_visibility()
        
        self.search_engine = None
        self.search_results = []
        self.m3u8_results = {}
        self.results_text.clear()
        self.update_status(f" 切换到{engine_type}，等待搜索...")
        self.extract_selected_btn.setEnabled(False)
        self.extract_all_btn.setEnabled(False)
        self.copy_btn.setEnabled(False)
        # 重新初始化搜索引擎
        self.init_search_engine()
    
    def get_proxy_config(self):
        """从主窗口获取代理配置"""
        try:
            settings_file = get_settings_path()
            if os.path.exists(settings_file):
                with open(settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                
                network = settings.get('network', {})
                return {
                    'enabled': network.get('proxy_enabled', False),
                    'type': network.get('proxy_type', 'HTTP'),
                    'host': network.get('proxy_host', ''),
                    'port': network.get('proxy_port', 8080)
                }
        except Exception as e:
            print(f"获取代理配置失败: {e}")
        
        return {'enabled': False}
    
    def update_status(self, message):
        """更新状态"""
        self.status_label.setText(message)
        self.append_log(message)
        QApplication.processEvents()  # 立即更新UI

    def append_log(self, message):
        """线程安全地追加实时日志。"""
        text = str(message or "").rstrip()
        if text:
            thread_name = threading.current_thread().name or "search"
            self.signals.log_message.emit(text, thread_name)

    def _append_log_line(self, message, thread_name="search"):
        """主线程写入日志面板。"""
        if not hasattr(self, "log_text") or self.log_text is None:
            return
        append_spring_boot_log(self.log_text, message, thread_name=thread_name)

    def clear_logs(self):
        if hasattr(self, "log_text") and self.log_text is not None:
            self.log_text.clear()
            self.append_log("日志已清空")

    class _TeeStream:
        """把 stdout/stderr 同时写回原流并推送到日志面板。"""

        def __init__(self, original, emit_fn):
            self._original = original
            self._emit = emit_fn
            self._buffer = ""

        def write(self, text):
            if self._original is not None:
                try:
                    self._original.write(text)
                except Exception:
                    pass
            if not text:
                return 0
            self._buffer += str(text)
            while "\n" in self._buffer:
                line, self._buffer = self._buffer.split("\n", 1)
                line = line.rstrip()
                if line:
                    self._emit(line)
            return len(text)

        def flush(self):
            if self._original is not None:
                try:
                    self._original.flush()
                except Exception:
                    pass
            if self._buffer.strip():
                self._emit(self._buffer.rstrip())
                self._buffer = ""

        def isatty(self):
            return False

        def fileno(self):
            if self._original is not None and hasattr(self._original, "fileno"):
                return self._original.fileno()
            raise OSError("tee stream has no fileno")

    class _QtLogHandler(logging.Handler):
        def __init__(self, emit_fn):
            super().__init__()
            self._emit = emit_fn

        def emit(self, record):
            try:
                self._emit(self.format(record))
            except Exception:
                pass

    def _install_log_capture(self):
        """捕获 print / logging，显示到右侧实时日志。"""
        import logging

        if self._log_stdout is not None:
            return

        self._orig_stdout = sys.stdout
        self._orig_stderr = sys.stderr
        self._log_stdout = self._TeeStream(self._orig_stdout, self.append_log)
        self._log_stderr = self._TeeStream(self._orig_stderr, self.append_log)
        sys.stdout = self._log_stdout
        sys.stderr = self._log_stderr

        handler = self._QtLogHandler(self.append_log)
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        if root_logger.level > logging.INFO or root_logger.level == logging.NOTSET:
            root_logger.setLevel(logging.INFO)
        self._log_handler = handler
        self.append_log("实时日志已启动")

    def _uninstall_log_capture(self):
        import logging

        if self._orig_stdout is not None:
            sys.stdout = self._orig_stdout
            self._orig_stdout = None
        if self._orig_stderr is not None:
            sys.stderr = self._orig_stderr
            self._orig_stderr = None
        self._log_stdout = None
        self._log_stderr = None
        if self._log_handler is not None:
            logging.getLogger().removeHandler(self._log_handler)
            self._log_handler = None

    def closeEvent(self, event):
        self._uninstall_log_capture()
        super().closeEvent(event)
    
    def start_search(self):
        """开始搜索"""
        keyword = self.keyword_input.text().strip()
        print(f" 开始搜索，关键词: '{keyword}'")
        
        if not keyword:
            CustomMessageBox.show_error(self, "错误", "请输入搜索关键词!")
            return
        
        # 获取搜索引擎类型
        engine_type = self.engine_combo.currentText()

        if channel_requires_refresh(engine_type):
            # 爱壹帆：只刷新 Cookie，保留已缓存密钥，避免每次搜索都重建引擎卡顿。
            if (
                engine_type == IYF_CHANNEL
                and self.search_engine is not None
                and hasattr(self.search_engine, "_apply_cookie")
            ):
                self.search_engine._apply_cookie(self.ncat_cookie_input.text().strip())
            else:
                self.init_search_engine()
        elif not self.search_engine:
            print("搜索引擎未初始化，正在初始化...")
            self.init_search_engine()
        
        if not self.search_engine:
            CustomMessageBox.show_error(self, "错误", "搜索引擎未初始化!")
            return
        
        # 禁用搜索按钮
        self.search_btn.setEnabled(False)
        self.update_status(f" 正在搜索: {keyword}...")
        
        # 获取搜索类型（仅爱瓜影视需要）
        choice = self.type_combo.currentIndex()  # 0=电影, 1=电视剧等
        
        if engine_type == "爱瓜影视":
            print(f"搜索类型: {choice} ({'电影' if choice == 0 else '电视剧/动漫/综艺'})")
        
        # 在线程中执行搜索
        search_thread = threading.Thread(target=self._do_search, args=(keyword, choice))
        search_thread.daemon = True
        search_thread.start()
        print("搜索线程已启动")
    
    def _do_search(self, keyword, choice):
        """执行搜索（在线程中）"""
        try:
            engine_type = self.engine_combo.currentText()
            results = search_with_engine(engine_type, self.search_engine, keyword, choice)
            self.signals.search_completed.emit(results, keyword)

        except Exception as e:
            print(f"搜索异常: {e}")
            import traceback
            traceback.print_exc()
            # 使用信号通知UI更新错误
            self.signals.search_error.emit(str(e))
    
    def _on_search_complete(self, results, keyword):
        """搜索完成回调"""
        print(f"UI更新回调被调用: 结果数量={len(results)}, 关键词={keyword}")
        self.search_results = results
        self.search_btn.setEnabled(True)
        
        if results:
            engine_type = self.engine_combo.currentText()
            self.update_status(f"找到 {len(results)} 个结果")
            print(f"正在设置结果文本...")
            
            # 显示结果
            result_text = f" 搜索关键词: {keyword}\n"
            result_text += f" 搜索引擎: {engine_type}\n"
            result_text += f" 共找到 {len(results)} 个结果:\n\n"
            
            if engine_type == "爱瓜影视":
                # 爱瓜影视返回 [url, url, ...]
                for i, url in enumerate(results):
                    result_text += f"{i}: {url}\n"
            elif engine_type == "NCat22影视":
                # NCat22影视返回 [{dict}, {dict}, ...]
                for i, item in enumerate(results):
                    if isinstance(item, dict):
                        result_text += f"{'='*60}\n"
                        result_text += f"[{i}] {item.get('title', '未知')}\n"
                        result_text += f"{'='*60}\n"
                        result_text += f" 分类：{item.get('category', '未知')}"
                        result_text += f"  |   年份：{item.get('year', '未知')}"
                        result_text += f"  |   地区：{item.get('region', '未知')}\n"
                        if item.get('genre'):
                            result_text += f" 类型：{item.get('genre')}\n"
                        if item.get('actors'):
                            actors = item.get('actors', '')
                            # 如果演员信息太长，截断显示
                            if len(actors) > 80:
                                result_text += f"演员：{actors[:80]}...\n"
                            else:
                                result_text += f"演员：{actors}\n"
                        if item.get('description'):
                            desc = item.get('description', '')
                            # 简介截断显示
                            if len(desc) > 100:
                                result_text += f"简介：{desc[:100]}...\n"
                            else:
                                result_text += f"简介：{desc}\n"
                        result_text += f"链接：{item.get('detail_url', '')}\n"
                        result_text += f"\n"
                    else:
                        # 兼容性处理
                        result_text += f"{i}: {item}\n"
            elif engine_type == "魔法影视":
                # 魔法影视返回 [{dict}, {dict}, ...]，直接包含播放链接
                for i, item in enumerate(results):
                    if isinstance(item, dict):
                        result_text += f"{'='*60}\n"
                        result_text += f"[{i}] {item.get('title', '未知')}\n"
                        result_text += f"{'='*60}\n"
                        result_text += f" 分类：{item.get('category', '未知')}"
                        result_text += f"  |   年份：{item.get('year', '未知')}"
                        result_text += f"  |   地区：{item.get('region', '未知')}\n"
                        if item.get('genre'):
                            result_text += f" 类型：{item.get('genre')}\n"
                        if item.get('remarks'):
                            result_text += f" 备注：{item.get('remarks')}\n"
                        if item.get('score'):
                            result_text += f"评分：{item.get('score')}\n"
                        if item.get('actors'):
                            actors = item.get('actors', '')
                            if len(actors) > 80:
                                result_text += f" 演员：{actors[:80]}...\n"
                            else:
                                result_text += f" 演员：{actors}\n"
                        if item.get('total'):
                            result_text += f" 总集数：{item.get('total')}集\n"
                        result_text += f" 播放源：{item.get('play_from', '默认')}\n"
                        result_text += f"\n"
                    else:
                        result_text += f"{i}: {item}\n"
            elif engine_type == IYF_CHANNEL:
                for i, item in enumerate(results):
                    if not isinstance(item, dict):
                        result_text += f"{i}: {item}\n"
                        continue
                    result_text += f"{'='*60}\n"
                    result_text += f"[{i}] {item.get('title', '未知')}\n"
                    result_text += f"{'='*60}\n"
                    result_text += f" 分类：{item.get('category', '未知')}"
                    result_text += f"  |   年份：{item.get('year', '未知')}"
                    result_text += f"  |   地区：{item.get('region', '未知')}\n"
                    if item.get('genre'):
                        result_text += f" 类型：{item.get('genre')}\n"
                    if item.get('score'):
                        result_text += f"评分：{item.get('score')}\n"
                    if item.get('actors'):
                        result_text += f" 演员：{item.get('actors')}\n"
                    if item.get('director'):
                        result_text += f" 导演：{item.get('director')}\n"
                    result_text += f" 剧集：{item.get('total', 0)} 集"
                    if item.get('remarks'):
                        result_text += f"  |  更新至：{item.get('remarks')}"
                    result_text += "\n\n"

            print(f"结果文本长度: {len(result_text)}")
            self.results_text.setText(result_text)
            print(f"已设置结果文本到UI")
            
            # 强制刷新UI
            self.results_text.update()
            QApplication.processEvents()
            
            # 启用提取按钮和复制按钮
            self.extract_selected_btn.setEnabled(True)
            self.extract_all_btn.setEnabled(True)
            self.copy_btn.setEnabled(True)
            print(f"已启用提取按钮")
            
        else:
            self.update_status("未找到相关结果")
            self.results_text.setText(f"未找到与 '{keyword}' 相关的结果")
            print("设置了无结果信息")
    
    def _on_search_error(self, error):
        """搜索错误回调"""
        print(f"搜索错误回调被调用: {error}")
        self.search_btn.setEnabled(True)
        self.update_status(f"搜索失败: {error}")
        CustomMessageBox.show_error(self, "搜索失败", f"搜索过程中发生错误:\n{error}")
    
    def extract_selected(self):
        """提取选中的m3u8"""
        if not self.search_results:
            CustomMessageBox.show_error(self, "错误", "没有搜索结果!")
            return
        
        # 创建选择对话框
        from PySide6.QtWidgets import QInputDialog
        
        # 创建选择项列表
        engine_type = self.engine_combo.currentText()
        items = []
        
        if engine_type == "爱瓜影视":
            # 爱瓜影视返回 [url, url, ...]
            for i, url in enumerate(self.search_results):
                display_name = url.split('/')[-1] if '/' in url else url
                items.append(f"{i}: {display_name}")
        elif engine_type == "NCat22影视":
            # NCat22影视返回 [{dict}, {dict}, ...]
            for i, item in enumerate(self.search_results):
                if isinstance(item, dict):
                    title = item.get('title', '未知')
                    items.append(f"{i}: {title}")
                else:
                    items.append(f"{i}: {item}")
        elif engine_type == "魔法影视":
            # 魔法影视返回 [{dict}, {dict}, ...]
            for i, item in enumerate(self.search_results):
                if isinstance(item, dict):
                    title = item.get('title', '未知')
                    remarks = item.get('remarks', '')
                    items.append(f"{i}: {title} ({remarks})")
                else:
                    items.append(f"{i}: {item}")
        elif engine_type == IYF_CHANNEL:
            for i, item in enumerate(self.search_results):
                title = item.get('title', '未知') if isinstance(item, dict) else str(item)
                items.append(f"{i}: {title}")

        # 弹出选择对话框
        item, ok = QInputDialog.getItem(
            self, 
            "选择要提取的项目", 
            "请选择要提取M3U8的项目:", 
            items, 
            0, 
            False
        )
        
        if ok and item:
            # 解析选择的索引
            try:
                selected_index = int(item.split(':')[0])
                if 0 <= selected_index < len(self.search_results):
                    self.extract_m3u8([self.search_results[selected_index]])
                else:
                    CustomMessageBox.show_error(self, "错误", "选择的索引无效!")
            except (ValueError, IndexError):
                CustomMessageBox.show_error(self, "错误", "解析选择失败!")
    
    def extract_all(self):
        """提取所有m3u8"""
        if not self.search_results:
            CustomMessageBox.show_error(self, "错误", "没有搜索结果!")
            return
        
        self.extract_m3u8(self.search_results)
    
    def extract_m3u8(self, items):
        """提取m3u8链接"""
        if not self.search_engine:
            CustomMessageBox.show_error(self, "错误", "搜索引擎未初始化!")
            return
        
        engine_type = self.engine_combo.currentText()
        
        if engine_type == "爱瓜影视":
            # 爱瓜影视：直接提取m3u8
            self._extract_aigua(items)
        elif engine_type == "NCat22影视":
            # NCat22影视：需要先获取详情页，解析线路和剧集
            self._extract_ncat(items)
        elif engine_type == "魔法影视":
            # 魔法影视：直接从搜索结果中提取播放链接
            self._extract_mofa(items)
        elif engine_type == IYF_CHANNEL:
            # 爱壹帆：搜索结果含剧集 key，走播放接口取标清 m3u8
            self._extract_iyf(items)

    def _extract_aigua(self, urls):
        """爱瓜影视提取m3u8"""
        # 清空之前的结果
        if hasattr(self.search_engine, 'clear_results'):
            self.search_engine.clear_results()
        self.m3u8_results = {}
        
        # 禁用按钮
        self.extract_selected_btn.setEnabled(False)
        self.extract_all_btn.setEnabled(False)
        
        self.update_status(f"开始提取 {len(urls)} 个M3U8链接...")
        
        # 使用多线程并发提取（按照search.py的逻辑）
        self.search_threads = []
        for url in urls:
            thread = Thread(target=self.search_engine.get_m3u8, args=(url,))
            thread.daemon = True
            self.search_threads.append(thread)
            thread.start()
        
        # 启动监控线程
        monitor_thread = threading.Thread(target=self._monitor_extraction)
        monitor_thread.daemon = True
        monitor_thread.start()
    
    def _extract_ncat(self, items):
        """NCat22影视提取m3u8"""
        self.m3u8_results = {}

        # 禁用按钮
        self.extract_selected_btn.setEnabled(False)
        self.extract_all_btn.setEnabled(False)

        self.update_status(f"开始提取 {len(items)} 个详情页...")

        # 在线程中执行提取
        extract_thread = threading.Thread(target=self._do_ncat_extraction, args=(items,))
        extract_thread.daemon = True
        extract_thread.start()

    def _do_ncat_extraction(self, items):
        """执行NCat22影视的提取（在线程中）"""
        try:
            all_results = {}

            for idx, item in enumerate(items, 1):
                # 提取URL和标题
                if isinstance(item, dict):
                    title = item.get('title', f'视频{idx}')
                    url = item.get('detail_url', '')
                else:
                    # 兼容性处理
                    if isinstance(item, tuple) and len(item) == 2:
                        title, url = item
                    else:
                        url = item
                        title = f"视频{idx}"

                if not url:
                    print(f"跳过无效URL: {title}")
                    continue

                self.update_status(f"正在获取线路信息: {title} ({idx}/{len(items)})")
                print(f"\n处理: {title}")
                print(f"URL: {url}")

                # 获取详情页
                detail_html = self.search_engine.fetch_detail_page(url)
                if not detail_html:
                    print(f"获取详情页失败: {title}")
                    continue

                # 解析线路和剧集
                routes = self.search_engine.parse_detail_routes(detail_html, url)
                if not routes:
                    print(f"未找到播放线路，跳过: {title}")
                    continue

                print(f"找到 {len(routes)} 个播放线路")

                # 在主线程中显示线路选择对话框
                selected_route = self._show_route_selection_dialog(routes, title)

                if not selected_route:
                    print(f"用户取消选择线路: {title}")
                    continue

                # 获取选中线路的所有剧集
                route_data = routes[selected_route]
                episodes = route_data['episodes']
                total_episodes = len(episodes)

                print(f"选择线路: {selected_route}")
                print(f"开始提取 {total_episodes} 集...")

                self.update_status(f"正在提取: {title} - {selected_route} (0/{total_episodes})")

                # 使用多线程并发提取所有剧集
                from concurrent.futures import ThreadPoolExecutor, as_completed
                import threading

                # 创建线程锁保护共享数据
                results_lock = threading.Lock()
                completed_count = [0]  # 使用列表以便在闭包中修改

                def extract_single_episode(ep_info):
                    """提取单个剧集的m3u8链接"""
                    ep_idx, ep_name, ep_url = ep_info
                    try:
                        print(f"  [{ep_idx}/{total_episodes}] 提取: {ep_name}")

                        # 获取播放URL
                        _, m3u8_url = self.search_engine.get_episode_play_url(ep_url)

                        with results_lock:
                            completed_count[0] += 1
                            current = completed_count[0]

                        # 更新UI进度
                        self.update_status(f"正在提取: {title} - {selected_route} ({current}/{total_episodes})")

                        if m3u8_url:
                            key = f"{title}_{selected_route}_{ep_name}"
                            print(f"    [{current}/{total_episodes}] 成功: {ep_name}")
                            return (key, m3u8_url)
                        else:
                            print(f"    [{current}/{total_episodes}] 提取失败: {ep_name}")
                            return None

                    except Exception as e:
                        print(f"    提取失败: {ep_name} - {e}")
                        return None

                # 准备任务列表
                tasks = [(idx, ep_name, ep_url) for idx, (ep_name, ep_url) in enumerate(episodes, 1)]

                # 使用线程池并发处理（最多10个并发线程）
                max_workers = min(10, total_episodes)
                print(f"使用 {max_workers} 个线程并发提取...")

                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    # 提交所有任务
                    future_to_episode = {executor.submit(extract_single_episode, task): task for task in tasks}

                    # 收集结果
                    for future in as_completed(future_to_episode):
                        result = future.result()
                        if result:
                            key, m3u8_url = result
                            all_results[key] = m3u8_url

                success_count = len([k for k in all_results.keys() if k.startswith(f"{title}_{selected_route}")])
                print(f"完成提取: {title} - 共成功 {success_count}/{total_episodes} 集")

            # 使用信号通知UI更新
            self.signals.extraction_completed.emit(all_results)

        except Exception as e:
            print(f"NCat22影视提取异常: {e}")
            import traceback
            traceback.print_exc()
            # 发送空结果
            self.signals.extraction_completed.emit({})

    def _extract_mofa(self, items):
        """魔法影视提取m3u8（直接从搜索结果中提取）"""
        self.m3u8_results = {}

        # 禁用按钮
        self.extract_selected_btn.setEnabled(False)
        self.extract_all_btn.setEnabled(False)

        self.update_status("正在提取 M3U8 链接...")

        # 在线程中执行提取
        extract_thread = threading.Thread(target=self._do_mofa_extraction, args=(items,))
        extract_thread.daemon = True
        extract_thread.start()

    def _extract_iyf(self, items):
        """爱壹帆影视提取标清 m3u8"""
        self.m3u8_results = {}
        if hasattr(self.search_engine, "clear_results"):
            self.search_engine.clear_results()

        self.extract_selected_btn.setEnabled(False)
        self.extract_all_btn.setEnabled(False)
        self.update_status(f"开始提取爱壹帆标清 M3U8（{len(items)} 部）...")

        extract_thread = threading.Thread(target=self._do_iyf_extraction, args=(items,))
        extract_thread.daemon = True
        extract_thread.start()

    def _do_iyf_extraction(self, items):
        """执行爱壹帆提取（在线程中）"""
        try:
            all_results = {}
            for idx, item in enumerate(items, 1):
                if not isinstance(item, dict):
                    print(f"跳过无效爱壹帆结果: {item}")
                    continue

                title = item.get("title", f"视频{idx}")
                brief_count = len(item.get("episodes") or [])
                self.update_status(
                    f"正在提取: {title} ({idx}/{len(items)}, {brief_count} 集)"
                )
                print(f"\n处理爱壹帆: {title} | 搜索结果约 {brief_count} 集")

                try:
                    extracted = self.search_engine.extract_item(item)
                except Exception as exc:
                    print(f"爱壹帆提取失败: {title} - {exc}")
                    continue

                all_results.update(extracted)
                total_episodes = (
                    item.get("total")
                    or len(item.get("episodes") or [])
                    or brief_count
                )
                print(f"完成提取: {title} - 成功 {len(extracted)}/{total_episodes} 集")

            self.signals.extraction_completed.emit(all_results)
        except Exception as e:
            print(f"爱壹帆提取异常: {e}")
            import traceback
            traceback.print_exc()
            self.signals.extraction_completed.emit({})

    def _do_mofa_extraction(self, items):
        """执行魔法影视的提取（在线程中）"""
        try:
            all_results = {}

            for item in items:
                if isinstance(item, dict):
                    title = item.get('title', '未知')
                    play_url = item.get('play_url', '')
                    play_from = item.get('play_from', 'default')

                    if not play_url:
                        print(f"{title} 没有播放链接")
                        continue

                    print(f"\n正在处理: {title}")

                    # 解析播放链接
                    routes = self.search_engine.parse_detail_routes(item)

                    if not routes:
                        print(f"{title} 没有可用的播放线路")
                        continue

                    # 显示线路信息
                    for route_name, route_info in routes.items():
                        print(f"   线路: {route_name} | 共 {route_info['total']} 集")

                    # 如果只有一个线路，直接使用
                    if len(routes) == 1:
                        selected_route = list(routes.keys())[0]
                    else:
                        # 多个线路时，让用户选择
                        selected_route = self._show_route_selection_dialog(routes, title)
                        if not selected_route:
                            print("用户取消了线路选择")
                            continue

                    # 获取选中线路的剧集
                    route_info = routes[selected_route]
                    episodes = route_info['episodes']
                    total_episodes = route_info['total']

                    print(f"选择线路: {selected_route} | 共 {total_episodes} 集")

                    # 魔法影视的播放链接已经是m3u8格式，直接添加到结果
                    for ep_name, ep_url in episodes:
                        key = f"{title}_{selected_route}_{ep_name}"
                        all_results[key] = ep_url
                        print(f"    {ep_name}: {ep_url[:60]}...")

                    print(f"完成提取: {title} - 共 {len(episodes)} 集")

            # 使用信号通知UI更新
            self.signals.extraction_completed.emit(all_results)

        except Exception as e:
            print(f"魔法影视提取异常: {e}")
            import traceback
            traceback.print_exc()
            # 发送空结果
            self.signals.extraction_completed.emit({})

    def _show_route_selection_dialog(self, routes, title):
        """
        显示线路选择对话框（线程安全）
        :param routes: 线路数据
        :param title: 视频标题
        :return: 选中的线路名称，如果取消则返回None
        """
        import threading
        
        # 创建事件对象
        self.route_selection_event = threading.Event()
        self.route_selection_result = None
        
        print("[工作线程] 准备发送信号显示对话框...")
        
        # 发送信号到主线程显示对话框
        self.signals.show_route_dialog.emit(routes, title, None)
        
        # 等待对话框完成
        print("[工作线程] 等待对话框完成...")
        self.route_selection_event.wait()
        
        result = self.route_selection_result
        print(f"[工作线程] 对话框完成，返回结果: {result}")
        
        return result
    
    def _on_show_route_dialog(self, routes, title, _):
        """在主线程中显示线路选择对话框"""
        try:
            print(f"[主线程] 准备显示线路选择对话框: {title}")
            print(f"   可用线路数: {len(routes)}")
            
            dialog = RouteSelectionDialog(routes, title, self)
            dialog_result = dialog.exec()
            
            print(f"   对话框返回值: {dialog_result} ({'Accepted' if dialog_result == QDialog.Accepted else 'Rejected'})")
            
            if dialog_result == QDialog.Accepted:
                selected = dialog.get_selected_route()
                self.route_selection_result = selected
                print(f"[主线程] 用户选择了线路: {selected}")
                print(f"   存储到 self.route_selection_result: {self.route_selection_result}")
            else:
                print("[主线程] 用户取消了选择")
                self.route_selection_result = None
                
        except Exception as e:
            print(f"显示线路选择对话框失败: {e}")
            import traceback
            traceback.print_exc()
            self.route_selection_result = None
        finally:
            # 无论成功失败都要设置事件，避免死锁
            print("[主线程] 设置事件，通知工作线程继续...")
            if self.route_selection_event:
                self.route_selection_event.set()
    
    def _monitor_extraction(self):
        """监控提取进程"""
        try:
            # 等待所有线程完成
            for thread in self.search_threads:
                thread.join()
            
            # 获取结果
            results = self.search_engine.get_result()
            
            # 使用信号通知UI更新
            self.signals.extraction_completed.emit(results)
        except Exception as e:
            print(f"监控提取进程异常: {e}")
            # 发送空结果
            self.signals.extraction_completed.emit({})
    
    def _on_extraction_complete(self, results):
        """提取完成回调"""
        self.m3u8_results = results
        
        # 重新启用按钮
        self.extract_selected_btn.setEnabled(True)
        self.extract_all_btn.setEnabled(True)
        
        if results:
            self.update_status(f"提取完成: 获得 {len(results)} 个M3U8链接")
            
            # 显示结果
            result_text = self.results_text.toPlainText() + "\n\n"
            result_text += "=" * 50 + "\n"
            result_text += f" M3U8提取结果 ({len(results)}个):\n"
            result_text += "=" * 50 + "\n\n"
            
            for i, (chapter_id, m3u8_url) in enumerate(results.items(), 1):
                result_text += f"{i}. Chapter ID: {chapter_id}\n"
                result_text += f"   M3U8: {m3u8_url}\n\n"
            
            self.results_text.setText(result_text)
            
            # 启用复制按钮
            self.copy_btn.setEnabled(True)
            
        else:
            self.update_status("提取失败，未获得有效 M3U8 链接")
    
    def copy_results(self):
        """复制结果到剪贴板"""
        if not self.m3u8_results:
            CustomMessageBox.show_error(self, "错误", "没有可复制的结果!")
            return
        
        # 只复制M3U8链接
        m3u8_urls = list(self.m3u8_results.values())
        clipboard_text = "\n".join(m3u8_urls)
        
        clipboard = QApplication.clipboard()
        clipboard.setText(clipboard_text)
        
        self.update_status(f" 已复制 {len(m3u8_urls)} 个M3U8链接到剪贴板")
    
    def clear_results(self):
        """清空结果"""
        self.results_text.clear()
        self.search_results = []
        self.m3u8_results = {}
        
        if self.search_engine:
            self.search_engine.clear_results()
        
        # 禁用按钮
        self.extract_selected_btn.setEnabled(False)
        self.extract_all_btn.setEnabled(False)
        self.copy_btn.setEnabled(False)
        
        self.update_status("已清空所有结果")


class MainWindow(QMainWindow):
    """主窗口"""
    log_message = Signal(str, str)  # message, thread_name

    def __init__(self):
        super().__init__()
        self.download_tasks = []
        self.custom_headers = {}  # 存储用户自定义请求头
        self.active_downloads = 0  # 当前活跃下载数
        self.download_queue = []   # 下载队列
        self.is_closing = False  # 标记是否正在关闭
        self._stat_counts = {
            'total': 0, 'active': 0, 'waiting': 0, 'completed': 0, 'failed': 0,
        }
        self._empty_anim = None
        self._empty_anim_running = False
        self._active_pulse_bright = False
        self._active_pulse_timer = QTimer(self)
        self._active_pulse_timer.setInterval(800)
        self._active_pulse_timer.timeout.connect(self._toggle_active_pulse)
        self._entrance_done = False
        self._log_stdout = None
        self._log_stderr = None
        self._orig_stdout = None
        self._orig_stderr = None
        self._log_handler = None
        self.setup_ui()
        self.setup_tray()  # 设置系统托盘
        self.load_user_settings()  # 加载用户设置
        self.log_message.connect(self._append_main_log)
        QTimer.singleShot(0, self._install_main_log_capture)
        
    def setup_ui(self):
        """设置UI"""
        self.setWindowTitle("M3U8 下载器 v1.0")
        self.setMinimumSize(1000, 720)
        self.resize(1100, 800)

        try:
            icon_path = resolve_app_icon()
            if icon_path:
                self.setWindowIcon(QIcon(icon_path))
        except Exception as e:
            print(f"设置窗口图标失败: {e}")

        central_widget = QWidget()
        central_widget.setObjectName("main_surface")
        self.setCentralWidget(central_widget)
        self._main_surface = central_widget

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(16)

        self.top_bar = QFrame()
        self.top_bar.setObjectName("top_bar")
        top_bar_layout = QHBoxLayout(self.top_bar)
        top_bar_layout.setContentsMargins(0, 0, 0, 12)
        top_bar_layout.setSpacing(12)

        brand_text_layout = QVBoxLayout()
        brand_text_layout.setContentsMargins(0, 0, 0, 0)
        brand_text_layout.setSpacing(2)

        self.app_title = QLabel("M3U8 下载器")
        self.app_title.setFont(app_font(18, QFont.DemiBold))
        brand_text_layout.addWidget(self.app_title)

        self.app_subtitle = QLabel("轻量、稳定的视频抓取与合并工作台")
        self.app_subtitle.setFont(app_font(9))
        brand_text_layout.addWidget(self.app_subtitle)
        top_bar_layout.addLayout(brand_text_layout)
        top_bar_layout.addStretch()

        search_btn = ModernButton("搜索")
        search_btn.clicked.connect(self.show_m3u8_search_dialog)
        top_bar_layout.addWidget(search_btn)

        headers_top_btn = ModernButton("请求头")
        headers_top_btn.clicked.connect(self.show_headers_dialog)
        top_bar_layout.addWidget(headers_top_btn)

        folder_btn = ModernButton("下载目录")
        folder_btn.clicked.connect(self.open_download_folder)
        top_bar_layout.addWidget(folder_btn)

        settings_btn = ModernButton("设置")
        settings_btn.clicked.connect(self.show_settings)
        top_bar_layout.addWidget(settings_btn)

        main_layout.addWidget(self.top_bar, 0)

        workspace = QWidget()
        workspace.setObjectName("workspace")
        workspace_layout = QHBoxLayout(workspace)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(14)

        self.compose_card = QFrame()
        self.compose_card.setObjectName("compose_card")
        self.compose_card.setMinimumWidth(360)
        self.compose_card.setMaximumWidth(420)
        compose_layout = QVBoxLayout(self.compose_card)
        compose_layout.setContentsMargins(22, 20, 22, 22)
        compose_layout.setSpacing(11)

        self.compose_title = QLabel("新建下载")
        self.compose_title.setFont(app_font(18, QFont.DemiBold))
        compose_layout.addWidget(self.compose_title)

        self.compose_desc = QLabel("填写链接与保存位置，加入后自动排队。")
        self.compose_desc.setFont(app_font(9))
        self.compose_desc.setWordWrap(True)
        compose_layout.addWidget(self.compose_desc)

        compose_layout.addSpacing(4)

        mode_label = self._create_form_label("输入方式")
        compose_layout.addWidget(mode_label)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["单个链接", "批量链接"])
        self.mode_combo.setMinimumHeight(40)
        self.mode_combo.setStyleSheet(self._control_combo_style())
        self.mode_combo.currentTextChanged.connect(self.on_mode_changed)
        compose_layout.addWidget(self.mode_combo)

        url_label = self._create_form_label("视频链接")
        compose_layout.addWidget(url_label)

        self.url_input = ModernLineEdit("请输入 M3U8 视频链接")
        self.url_input.returnPressed.connect(self.add_download_task)
        compose_layout.addWidget(self.url_input)

        self.batch_url_input = QTextEdit()
        self.batch_url_input.setPlaceholderText("每行一个 M3U8 链接")
        self.batch_url_input.setMinimumHeight(120)
        self.batch_url_input.setMaximumHeight(180)
        self.batch_url_input.setStyleSheet(self._text_edit_style())
        self.batch_url_input.setVisible(False)
        compose_layout.addWidget(self.batch_url_input)

        output_label = self._create_form_label("保存位置")
        compose_layout.addWidget(output_label)

        output_row = QHBoxLayout()
        output_row.setSpacing(8)

        self.output_input = ModernLineEdit("选择保存路径")
        output_row.addWidget(self.output_input, 1)

        self.browse_btn = ModernButton("浏览")
        self.browse_btn.clicked.connect(self.browse_output_path)
        output_row.addWidget(self.browse_btn)
        compose_layout.addLayout(output_row)

        task_name_label = self._create_form_label("任务名称 · 可选")
        compose_layout.addWidget(task_name_label)

        self.task_name_input = ModernLineEdit("留空将自动从链接推断")
        self.task_name_input.returnPressed.connect(self.add_download_task)
        compose_layout.addWidget(self.task_name_input)

        performance_row = QHBoxLayout()
        performance_row.setSpacing(10)

        threads_field = QVBoxLayout()
        threads_field.setSpacing(5)
        self.threads_label = self._create_form_label("单视频线程")
        threads_field.addWidget(self.threads_label)

        self.threads_spin = self._create_number_input(
            1,
            32,
            DEFAULT_CONFIG['max_workers'],
            "一个视频同时下载的分片数。",
        )
        self.threads_spin.setAccessibleName("单任务线程")
        threads_field.addWidget(self.threads_spin)
        performance_row.addLayout(threads_field, 1)

        concurrent_field = QVBoxLayout()
        concurrent_field.setSpacing(5)
        self.concurrent_label = self._create_form_label("同时下载")
        concurrent_field.addWidget(self.concurrent_label)

        self.concurrent_spin = self._create_number_input(
            1,
            20,
            10,
            "队列中同时运行的下载任务数。",
        )
        self.concurrent_spin.setAccessibleName("同时任务")
        concurrent_field.addWidget(self.concurrent_spin)
        performance_row.addLayout(concurrent_field, 1)

        self.performance_panel = QFrame()
        self.performance_panel.setObjectName("performance_panel")
        performance_panel_layout = QVBoxLayout(self.performance_panel)
        performance_panel_layout.setContentsMargins(12, 10, 12, 10)
        performance_panel_layout.setSpacing(0)
        performance_panel_layout.addLayout(performance_row)
        compose_layout.addWidget(self.performance_panel)

        template_label = self._create_form_label("请求头模板")
        compose_layout.addWidget(template_label)
        self.template_combo = self._create_template_combo()
        compose_layout.addWidget(self.template_combo)

        compose_layout.addStretch()

        self.add_task_btn = ModernButton("加入下载队列", primary=True)
        self.add_task_btn.setMinimumHeight(44)
        self.add_task_btn.clicked.connect(self.add_download_task)
        compose_layout.addWidget(self.add_task_btn)

        workspace_layout.addWidget(self.compose_card, 0)

        self.queue_section = QFrame()
        self.queue_section.setObjectName("queue_section")
        queue_layout = QVBoxLayout(self.queue_section)
        queue_layout.setContentsMargins(12, 12, 12, 12)
        queue_layout.setSpacing(0)

        self.right_tabs = QTabWidget()
        self.right_tabs.setObjectName("right_tabs")
        self.right_tabs.setDocumentMode(True)

        # ---- Tab 1: 下载队列 ----
        queue_tab = QWidget()
        queue_tab_layout = QVBoxLayout(queue_tab)
        queue_tab_layout.setContentsMargins(8, 10, 8, 8)
        queue_tab_layout.setSpacing(12)

        queue_header = QHBoxLayout()
        queue_header.setSpacing(12)

        queue_title_layout = QVBoxLayout()
        queue_title_layout.setSpacing(0)
        self.queue_title = QLabel("下载队列")
        self.queue_title.setFont(app_font(16, QFont.DemiBold))
        queue_title_layout.addWidget(self.queue_title)
        self.queue_desc = QLabel("任务状态和整体进度")
        self.queue_desc.setFont(app_font(9))
        queue_title_layout.addWidget(self.queue_desc)
        queue_header.addLayout(queue_title_layout)
        queue_header.addStretch()

        self.clear_all_tasks_btn = ModernButton("清理已完成", variant='danger')
        self.clear_all_tasks_btn.setMinimumHeight(34)
        self.clear_all_tasks_btn.clicked.connect(self.clear_all_tasks)
        self.clear_all_tasks_btn.setEnabled(False)
        queue_header.addWidget(self.clear_all_tasks_btn)
        queue_tab_layout.addLayout(queue_header)

        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(8)
        self.total_tasks_label = self._create_overview_pill("总任务 0", UI_TOKENS['primary'])
        stats_layout.addWidget(self.total_tasks_label)
        self.active_downloads_label = self._create_overview_pill("活跃 0", UI_TOKENS['primary'])
        stats_layout.addWidget(self.active_downloads_label)
        self.waiting_tasks_label = self._create_overview_pill("等待 0", UI_TOKENS['warning'])
        stats_layout.addWidget(self.waiting_tasks_label)
        self.completed_tasks_label = self._create_overview_pill("完成 0", UI_TOKENS['success'])
        stats_layout.addWidget(self.completed_tasks_label)
        self.failed_tasks_label = self._create_overview_pill("失败 0", UI_TOKENS['danger'])
        stats_layout.addWidget(self.failed_tasks_label)
        stats_layout.addStretch()
        queue_tab_layout.addLayout(stats_layout)

        self.progress_overview = self._create_progress_overview()
        queue_tab_layout.addWidget(self.progress_overview)

        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("task_scroll")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setStyleSheet(self._scroll_area_style())

        self.task_container = QWidget()
        self.task_container.setObjectName("task_container")
        self.task_container_layout = QVBoxLayout(self.task_container)
        self.task_container_layout.setContentsMargins(0, 4, 0, 4)
        self.task_container_layout.setSpacing(8)
        self.empty_state_card = self._create_empty_state_card()
        self.task_container_layout.addWidget(self.empty_state_card)
        self.task_container_layout.addStretch()

        self.scroll_area.setWidget(self.task_container)
        queue_tab_layout.addWidget(self.scroll_area, 1)

        # ---- Tab 2: 实时日志 ----
        log_tab = QWidget()
        log_tab_layout = QVBoxLayout(log_tab)
        log_tab_layout.setContentsMargins(8, 10, 8, 8)
        log_tab_layout.setSpacing(10)

        log_header = QHBoxLayout()
        log_title_layout = QVBoxLayout()
        log_title_layout.setSpacing(0)
        self.log_panel_title = QLabel("实时日志")
        self.log_panel_title.setFont(app_font(16, QFont.DemiBold))
        log_title_layout.addWidget(self.log_panel_title)
        self.log_panel_desc = QLabel("下载与搜索过程输出")
        self.log_panel_desc.setFont(app_font(9))
        log_title_layout.addWidget(self.log_panel_desc)
        log_header.addLayout(log_title_layout)
        log_header.addStretch()
        self.clear_main_log_btn = ModernButton("清空日志")
        self.clear_main_log_btn.setMinimumHeight(34)
        self.clear_main_log_btn.clicked.connect(self.clear_main_logs)
        log_header.addWidget(self.clear_main_log_btn)
        log_tab_layout.addLayout(log_header)

        self.main_log_text = QPlainTextEdit()
        self.main_log_text.setReadOnly(True)
        self.main_log_text.setPlaceholderText("下载、搜索、过盾等过程日志会显示在这里...")
        self.main_log_text.setStyleSheet(
            log_console_stylesheet(border=UI_TOKENS['border'], radius=UI_TOKENS['radius_card'])
        )
        log_tab_layout.addWidget(self.main_log_text, 1)

        self.right_tabs.addTab(queue_tab, "下载队列")
        self.right_tabs.addTab(log_tab, "实时日志")
        queue_layout.addWidget(self.right_tabs)

        workspace_layout.addWidget(self.queue_section, 1)
        main_layout.addWidget(workspace, 1)

        self.statusBar().showMessage("准备就绪")
        self.setup_menu()
        self._apply_dashboard_accents(get_theme(0))
        if not self.download_tasks:
            QTimer.singleShot(0, self._start_empty_state_animation)

    def _create_form_label(self, text):
        """创建左侧任务表单的小标签。"""
        label = QLabel(text)
        label.setProperty("role", "form_label")
        label.setFont(app_font(9, QFont.DemiBold))
        return label

    def _control_combo_style(self):
        """创建区下拉框样式"""
        return f"""
            QComboBox {{
                border: 1px solid {UI_TOKENS['border']};
                border-radius: {UI_TOKENS['radius_control']}px;
                padding: 8px 12px;
                background: {UI_TOKENS['surface']};
                color: {UI_TOKENS['text']};
                min-height: 36px;
            }}
            QComboBox:focus {{
                border-color: {UI_TOKENS['primary']};
            }}
            QComboBox:hover {{
                border-color: {UI_TOKENS['border_focus']};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid {UI_TOKENS['primary']};
                width: 0px;
                height: 0px;
                margin-right: 8px;
            }}
            QComboBox QAbstractItemView {{
                border: 1px solid {UI_TOKENS['border']};
                border-radius: {UI_TOKENS['radius_control']}px;
                background: {UI_TOKENS['surface']};
                selection-background-color: {UI_TOKENS['surface_alt']};
                selection-color: {UI_TOKENS['primary']};
                padding: 4px;
            }}
        """

    def _text_edit_style(self):
        """批量链接输入框样式"""
        return f"""
            QTextEdit {{
                border: 1px solid {UI_TOKENS['border']};
                border-radius: {UI_TOKENS['radius_control']}px;
                padding: 8px 12px;
                background: {UI_TOKENS['surface']};
                color: {UI_TOKENS['text']};
            }}
            QTextEdit:focus {{
                border-color: {UI_TOKENS['primary']};
            }}
            QTextEdit:hover {{
                border-color: {UI_TOKENS['border_focus']};
            }}
        """

    def _scroll_area_style(self, background="#F8FAFF", border=None):
        """任务列表滚动区域样式"""
        border = border or UI_TOKENS['border']
        return f"""
            QScrollArea#task_scroll {{
                border: 1px solid {border};
                border-radius: {UI_TOKENS['radius_card']}px;
                background: {background};
            }}
            QWidget#qt_scrollarea_viewport,
            QWidget#task_container {{
                background: transparent;
            }}
            QScrollBar:vertical {{
                border: none;
                background: {UI_TOKENS['surface_alt']};
                width: 8px;
                border-radius: {UI_TOKENS['radius_progress']}px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {UI_TOKENS['border']};
                border-radius: {UI_TOKENS['radius_progress']}px;
                min-height: 24px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {UI_TOKENS['text_muted']};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """

    def _apply_dashboard_accents(self, theme):
        """将当前主题的强调色应用到主工作台。极简 solid + 底部分割线，无渐变。"""
        primary = theme.get('primary', UI_TOKENS['primary'])
        primary_hover = theme.get('secondary', UI_TOKENS['primary_hover'])
        surface = theme.get('groupbox_bg', UI_TOKENS['surface'])
        border = theme.get('input_border', UI_TOKENS['border'])
        text = theme.get('text_color', UI_TOKENS['text'])
        is_dark = theme.get('is_dark', False)
        muted_text = '#94A3B8' if is_dark else UI_TOKENS['text_muted']
        subtle_text = '#64748B' if is_dark else UI_TOKENS['text_subtle']
        radius_card = UI_TOKENS['radius_card']
        radius_control = UI_TOKENS['radius_control']

        # 顶栏：底部单条细分割线，无背景色差
        if hasattr(self, 'top_bar'):
            self.top_bar.setStyleSheet(f"""
                QFrame#top_bar {{
                    background: transparent;
                    border: none;
                    border-bottom: 1px solid {border};
                }}
            """)
        # 新建下载卡片：solid surface，去左侧色条
        if hasattr(self, 'compose_card'):
            self.compose_card.setStyleSheet(f"""
                QFrame#compose_card {{
                    background: {surface};
                    border: 1px solid {border};
                    border-radius: {radius_card}px;
                }}
            """)
        # 队列区容器
        if hasattr(self, 'queue_section'):
            self.queue_section.setStyleSheet(f"""
                QFrame#queue_section {{
                    background: {surface};
                    border: 1px solid {border};
                    border-radius: {radius_card}px;
                }}
            """)
        if hasattr(self, 'right_tabs'):
            tab_bg = UI_TOKENS['surface_alt']
            self.right_tabs.setStyleSheet(f"""
                QTabWidget#right_tabs::pane {{
                    border: none;
                    background: transparent;
                    top: -1px;
                }}
                QTabWidget#right_tabs > QTabBar::tab {{
                    background: transparent;
                    color: {muted_text};
                    border: none;
                    border-bottom: 2px solid transparent;
                    padding: 8px 16px;
                    margin-right: 4px;
                    font-size: 13px;
                }}
                QTabWidget#right_tabs > QTabBar::tab:selected {{
                    color: {primary};
                    border-bottom: 2px solid {primary};
                    font-weight: 600;
                }}
                QTabWidget#right_tabs > QTabBar::tab:hover:!selected {{
                    color: {text};
                    background: {tab_bg};
                    border-radius: 6px 6px 0 0;
                }}
            """)
        if hasattr(self, 'app_title'):
            self.app_title.setStyleSheet(f"color: {text}; background: transparent;")
        if hasattr(self, 'app_subtitle'):
            self.app_subtitle.setStyleSheet(f"color: {muted_text}; background: transparent;")
        if hasattr(self, 'compose_title'):
            self.compose_title.setStyleSheet(f"color: {text}; background: transparent;")
        if hasattr(self, 'compose_desc'):
            self.compose_desc.setStyleSheet(f"color: {muted_text}; background: transparent;")
        if hasattr(self, 'queue_title'):
            self.queue_title.setStyleSheet(f"color: {text}; background: transparent;")
        if hasattr(self, 'queue_desc'):
            self.queue_desc.setStyleSheet(f"color: {subtle_text}; background: transparent;")
        if hasattr(self, 'log_panel_title'):
            self.log_panel_title.setStyleSheet(f"color: {text}; background: transparent;")
        if hasattr(self, 'log_panel_desc'):
            self.log_panel_desc.setStyleSheet(f"color: {subtle_text}; background: transparent;")
        if hasattr(self, 'main_log_text'):
            self.main_log_text.setStyleSheet(
                log_console_stylesheet(border=border, radius=radius_card)
            )
        if hasattr(self, 'performance_panel'):
            # 表单里的性能面板：更克制的浅底
            self.performance_panel.setStyleSheet(f"""
                QFrame#performance_panel {{
                    background: {UI_TOKENS['surface_alt']};
                    border: 1px solid {border};
                    border-radius: {radius_control}px;
                }}
            """)
        if hasattr(self, 'threads_label'):
            self.threads_label.setStyleSheet(f"color: {muted_text}; background: transparent;")
        if hasattr(self, 'concurrent_label'):
            self.concurrent_label.setStyleSheet(f"color: {muted_text}; background: transparent;")
        if hasattr(self, 'empty_state_card'):
            # 去掉 100px 硬编码 margin：让 QVBoxLayout 自然管理
            self.empty_state_card.setStyleSheet(f"""
                QFrame#empty_state_card {{
                    background: transparent;
                    border: none;
                }}
            """)
        if hasattr(self, 'empty_state_title'):
            self.empty_state_title.setStyleSheet(f"color: {text}; background: transparent;")
        if hasattr(self, 'empty_state_desc'):
            self.empty_state_desc.setStyleSheet(f"color: {muted_text}; background: transparent;")
        if hasattr(self, 'empty_state_hint'):
            self.empty_state_hint.setStyleSheet(f"color: {subtle_text}; background: transparent;")
        if hasattr(self, 'scroll_area'):
            self.scroll_area.setStyleSheet(
                self._scroll_area_style(UI_TOKENS['surface_alt'], border)
            )
        if hasattr(self, 'overall_progress'):
            self.overall_progress.setStyleSheet(f"""
                QProgressBar {{
                    border: none;
                    border-radius: {UI_TOKENS['radius_progress']}px;
                    background: {UI_TOKENS['surface_alt']};
                }}
                QProgressBar::chunk {{
                    border-radius: {UI_TOKENS['radius_progress']}px;
                    background: {primary};
                }}
            """)
        if hasattr(self, 'add_task_btn'):
            # 主 CTA：solid + hover 一档深色，去渐变
            self.add_task_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {primary};
                    color: #FFFFFF;
                    border: 1px solid {primary};
                    border-radius: {radius_control}px;
                    padding: 10px 18px;
                    font-weight: 600;
                }}
                QPushButton:hover {{
                    background: {primary_hover};
                    border-color: {primary_hover};
                }}
                QPushButton:pressed {{
                    background: {UI_TOKENS['primary_active']};
                    border-color: {UI_TOKENS['primary_active']};
                }}
                QPushButton:disabled {{
                    background: {UI_TOKENS['surface_alt']};
                    color: {UI_TOKENS['text_muted']};
                    border-color: {border};
                }}
            """)
        self._active_pill_color = primary
        if hasattr(self, 'active_downloads_label'):
            self._apply_overview_pill_style(
                self.active_downloads_label,
                primary,
                bright=self._active_pulse_bright and self._active_pulse_timer.isActive(),
            )

    def _create_field_label(self, text):
        """创建表单字段标签"""
        label = QLabel(text)
        label.setFont(app_font(10, QFont.DemiBold))
        label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        label.setMinimumWidth(82)
        label.setStyleSheet(f"color: {UI_TOKENS['text_muted']}; padding-right: 6px;")
        return label

    def _create_number_input(self, minimum, maximum, value, tooltip):
        """创建统一样式的数字输入框"""
        spin_box = QSpinBox()
        spin_box.setRange(minimum, maximum)
        spin_box.setValue(value)
        spin_box.setMinimumHeight(40)
        spin_box.setMinimumWidth(72)
        spin_box.setToolTip(tooltip)
        spin_box.setStyleSheet(f"""
            QSpinBox {{
                border: 1px solid {UI_TOKENS['border']};
                border-radius: {UI_TOKENS['radius_control']}px;
                padding: 8px 10px;
                background: {UI_TOKENS['surface']};
                color: {UI_TOKENS['text']};
            }}
            QSpinBox:focus {{
                border-color: {UI_TOKENS['primary']};
            }}
            QSpinBox:hover {{
                border-color: {UI_TOKENS['border_focus']};
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                width: 18px;
                border: none;
                background: transparent;
            }}
            QSpinBox::up-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-bottom: 5px solid {UI_TOKENS['primary']};
                width: 0px;
                height: 0px;
            }}
            QSpinBox::down-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid {UI_TOKENS['primary']};
                width: 0px;
                height: 0px;
            }}
        """)
        return spin_box

    def _create_quick_action_button(self, text, slot, emphasis=False):
        """创建快捷操作按钮（菜单等场景复用）"""
        button = QPushButton(text)
        button.setCursor(Qt.PointingHandCursor)
        button.setMinimumHeight(36)
        button.setFont(app_font(10, QFont.DemiBold if emphasis else QFont.Normal))
        accent = UI_TOKENS['primary']
        button.setStyleSheet(f"""
            QPushButton {{
                text-align: left;
                padding: 8px 12px;
                color: {accent if emphasis else UI_TOKENS['text']};
                background: {UI_TOKENS['surface_alt'] if emphasis else UI_TOKENS['surface']};
                border: 1px solid {UI_TOKENS['border']};
                border-radius: {UI_TOKENS['radius_control']}px;
            }}
            QPushButton:hover {{
                background: {UI_TOKENS['surface_alt']};
                border-color: {UI_TOKENS['border_focus']};
            }}
        """)
        button.clicked.connect(slot)
        return button

    def _pill_stylesheet(self, text_color, alpha=0.08):
        """概览统计 chip：不加边框，只有淡淡的底色 + 强调色文字。"""
        color = QColor(text_color)
        background = f"rgba({color.red()}, {color.green()}, {color.blue()}, {alpha})"
        return f"""
            QLabel {{
                color: {text_color};
                background: {background};
                border: none;
                border-radius: {UI_TOKENS['radius_tag']}px;
                padding: 4px 10px;
                letter-spacing: 0.2px;
            }}
        """

    def _apply_overview_pill_style(self, label, text_color, bright=False):
        """应用 pill 样式（bright 用于活跃下载脉冲）"""
        alpha = 0.28 if bright else 0.10
        label.setStyleSheet(self._pill_stylesheet(text_color, alpha))

    def _flash_overview_pill(self, label):
        """统计数字变化时短暂高亮 pill"""
        text_color = label.property('pill_color') or UI_TOKENS['primary']
        label.setStyleSheet(self._pill_stylesheet(text_color, 0.32))
        QTimer.singleShot(
            200,
            lambda: self._apply_overview_pill_style(
                label,
                text_color,
                bright=(
                    label is getattr(self, 'active_downloads_label', None)
                    and self._active_pulse_timer.isActive()
                    and self._active_pulse_bright
                ),
            ),
        )

    def _create_empty_state_card(self):
        """空状态：无边框、垂直居中，靠间距与字重营造层级。"""
        card = QFrame()
        card.setObjectName("empty_state_card")
        card.setStyleSheet("QFrame#empty_state_card { background: transparent; border: none; }")

        wrapper = QVBoxLayout(card)
        wrapper.setContentsMargins(24, 40, 24, 40)
        wrapper.setSpacing(10)
        wrapper.addStretch(1)

        self.empty_state_icon = QLabel()
        self.empty_state_icon.setAlignment(Qt.AlignCenter)
        self.empty_state_icon.setFixedSize(56, 56)
        self.empty_state_icon.setStyleSheet(
            f"background: {UI_TOKENS['primary_soft']};"
            f" border-radius: 28px;"
            f" border: none;"
        )
        wrapper.addWidget(self.empty_state_icon, 0, Qt.AlignHCenter)

        wrapper.addSpacing(4)

        self.empty_state_title = QLabel("还没有下载任务")
        self.empty_state_title.setAlignment(Qt.AlignCenter)
        self.empty_state_title.setFont(app_font(14, QFont.DemiBold))
        wrapper.addWidget(self.empty_state_title)

        self.empty_state_desc = QLabel("在左侧粘贴 M3U8 链接，选择保存位置后加入队列。")
        self.empty_state_desc.setAlignment(Qt.AlignCenter)
        self.empty_state_desc.setWordWrap(True)
        wrapper.addWidget(self.empty_state_desc)

        self.empty_state_hint = QLabel("支持批量链接与自定义请求头")
        self.empty_state_hint.setAlignment(Qt.AlignCenter)
        self.empty_state_hint.setFont(app_font(9))
        wrapper.addWidget(self.empty_state_hint)

        wrapper.addSpacing(4)

        start_button = ModernButton("填写下载链接", primary=True)
        start_button.setMaximumWidth(180)
        start_button.setMinimumHeight(38)
        start_button.clicked.connect(self._focus_download_input)
        wrapper.addWidget(start_button, 0, Qt.AlignHCenter)

        wrapper.addStretch(1)

        return card

    def _focus_download_input(self):
        """聚焦当前模式的链接输入框"""
        target = self.batch_url_input if "批量" in self.mode_combo.currentText() else self.url_input
        target.setFocus()

    def _create_overview_pill(self, text, text_color):
        """创建概览统计标签"""
        label = QLabel(text)
        label.setProperty('pill_color', text_color)
        label.setFont(app_font(9, QFont.DemiBold))
        label.setAlignment(Qt.AlignCenter)
        label.setMinimumHeight(26)
        label.setStyleSheet(self._pill_stylesheet(text_color))
        return label

    def _create_progress_overview(self):
        """创建进度概览（摘要 + 整体进度条）"""
        overview_widget = QWidget()
        overview_widget.setStyleSheet("background: transparent; border: none;")

        layout = QVBoxLayout(overview_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        summary_row = QHBoxLayout()
        self.progress_summary_label = QLabel("队列会根据并发限制自动启动")
        self.progress_summary_label.setFont(app_font(9))
        self.progress_summary_label.setStyleSheet(f"color: {UI_TOKENS['text_muted']};")
        summary_row.addWidget(self.progress_summary_label)
        summary_row.addStretch()
        layout.addLayout(summary_row)

        self.overall_progress = ModernProgressBar()
        self.overall_progress.setMaximumHeight(8)
        self.overall_progress.setValue(0)
        layout.addWidget(self.overall_progress)

        overview_widget.setVisible(False)
        return overview_widget

    def _create_template_combo(self):
        """创建预设模板下拉框"""
        combo = QComboBox()
        combo.setMinimumHeight(40)
        combo.setStyleSheet(self._control_combo_style())
        
        # 预设模板
        templates = {
            "默认（无特殊请求头）": {},
            "通用反爬虫": {
                "referer": "https://www.google.com/",
                "sec-ch-ua": '"Not;A=Brand";v="99", "Google Chrome";v="139", "Chromium";v="139"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "cross-site",
            },
            "Aigua TV": {
                "accept": "*/*",
                "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
                "cache-control": "no-cache",
                "origin": "https://aigua.tv",
                "pragma": "no-cache",
                "priority": "u=1, i",
                "referer": "https://aigua.tv/",
                "sec-ch-ua": '"Not;A=Brand";v="99", "Google Chrome";v="139", "Chromium";v="139"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "cross-site",
            },
            "移动端模拟": {
                "user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
                "sec-ch-ua-mobile": "?1",
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "cross-site",
            }
        }
        
        for name, headers in templates.items():
            combo.addItem(name, headers)
        
        combo.currentTextChanged.connect(self._on_template_changed)
        return combo
    
    def _on_template_changed(self):
        """模板选择改变时的处理"""
        current_data = self.template_combo.currentData()
        if current_data:
            self.custom_headers = current_data.copy()
            # 显示已选择模板的提示
            if current_data:
                self.statusBar().showMessage(f"已选择模板: {self.template_combo.currentText()}")
    
    def show_headers_dialog(self):
        """显示请求头配置对话框"""
        dialog = HeadersDialog(self, self.custom_headers)
        if dialog.exec() == QDialog.Accepted:
            self.custom_headers = dialog.get_headers()
            # 重置模板选择
            self.template_combo.setCurrentIndex(0)
            if self.custom_headers:
                self.statusBar().showMessage(f"已配置 {len(self.custom_headers)} 个自定义请求头")
            else:
                self.statusBar().showMessage("已清除自定义请求头")
    
    def show_m3u8_search_dialog(self):
        """显示M3U8搜索对话框"""
        try:
            dialog = M3u8SearchDialog(self)
            dialog.show()  # 使用show()而不是exec()来允许非模态显示
            self.statusBar().showMessage("已打开M3U8搜索窗口")
        except Exception as e:
            CustomMessageBox.show_error(
                self, 
                "错误", 
                f"打开M3U8搜索窗口失败:\n{str(e)}"
            )
    
    def setup_tray(self):
        """设置系统托盘"""
        # 创建系统托盘图标
        self.tray_icon = QSystemTrayIcon(self)
        
        # 设置托盘图标
        try:
            icon_path = resolve_app_icon()
            if icon_path:
                self.tray_icon.setIcon(QIcon(icon_path))
            else:
                # 如果没有图标文件，使用窗口图标
                self.tray_icon.setIcon(self.style().standardIcon(self.style().SP_ComputerIcon))
        except Exception as e:
            print(f"设置托盘图标失败: {e}")
            self.tray_icon.setIcon(self.style().standardIcon(self.style().SP_ComputerIcon))
        
        # 设置托盘提示
        self.tray_icon.setToolTip("M3U8 下载器")
        
        # 创建托盘菜单
        tray_menu = QMenu()
        
        # 显示主窗口
        show_action = QAction("显示主窗口", self)
        show_action.triggered.connect(self.show_from_tray)
        tray_menu.addAction(show_action)
        
        tray_menu.addSeparator()
        
        # 退出程序
        quit_action = QAction("退出程序", self)
        quit_action.triggered.connect(self.quit_application)
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        
        # 双击托盘图标显示窗口
        self.tray_icon.activated.connect(self.on_tray_activated)
        
        # 显示托盘图标
        self.tray_icon.show()
    
    def on_tray_activated(self, reason):
        """托盘图标激活事件"""
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_from_tray()
    
    def show_from_tray(self):
        """从托盘显示窗口"""
        self.show()
        self.activateWindow()
        self.raise_()
    
    def minimize_to_tray(self):
        """最小化到托盘"""
        self.hide()
        self.tray_icon.showMessage(
            "M3U8 下载器",
            "程序已最小化到系统托盘，双击托盘图标可重新打开窗口。",
            QSystemTrayIcon.Information,
            2000
        )
    
    def append_main_log(self, message):
        """线程安全地追加主窗口实时日志。"""
        text = str(message or "").rstrip()
        if text:
            thread_name = threading.current_thread().name or "main"
            self.log_message.emit(text, thread_name)

    def _append_main_log(self, message, thread_name="main"):
        """主线程写入主窗口日志面板。"""
        if not hasattr(self, "main_log_text") or self.main_log_text is None:
            return
        append_spring_boot_log(self.main_log_text, message, thread_name=thread_name)

    def clear_main_logs(self):
        if hasattr(self, "main_log_text") and self.main_log_text is not None:
            self.main_log_text.clear()
            self.append_main_log("日志已清空")

    class _MainTeeStream:
        """把 stdout/stderr 同时写回原流并推送到主窗口日志面板。"""

        def __init__(self, original, emit_fn):
            self._original = original
            self._emit = emit_fn
            self._buffer = ""

        def write(self, text):
            if self._original is not None:
                try:
                    self._original.write(text)
                except Exception:
                    pass
            if not text:
                return 0
            self._buffer += str(text)
            while "\n" in self._buffer:
                line, self._buffer = self._buffer.split("\n", 1)
                line = line.rstrip()
                if line:
                    self._emit(line)
            return len(text)

        def flush(self):
            if self._original is not None:
                try:
                    self._original.flush()
                except Exception:
                    pass
            if self._buffer.strip():
                self._emit(self._buffer.rstrip())
                self._buffer = ""

        def isatty(self):
            return False

        def fileno(self):
            if self._original is not None and hasattr(self._original, "fileno"):
                return self._original.fileno()
            raise OSError("tee stream has no fileno")

    class _MainQtLogHandler(logging.Handler):
        def __init__(self, emit_fn):
            super().__init__()
            self._emit = emit_fn

        def emit(self, record):
            try:
                self._emit(self.format(record))
            except Exception:
                pass

    def _install_main_log_capture(self):
        """捕获 print / logging，显示到主窗口「实时日志」页。"""
        if self._log_stdout is not None:
            return

        self._orig_stdout = sys.stdout
        self._orig_stderr = sys.stderr
        self._log_stdout = self._MainTeeStream(self._orig_stdout, self.append_main_log)
        self._log_stderr = self._MainTeeStream(self._orig_stderr, self.append_main_log)
        sys.stdout = self._log_stdout
        sys.stderr = self._log_stderr

        handler = self._MainQtLogHandler(self.append_main_log)
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        if root_logger.level > logging.INFO or root_logger.level == logging.NOTSET:
            root_logger.setLevel(logging.INFO)
        self._log_handler = handler
        self.append_main_log("实时日志已启动")

    def _uninstall_main_log_capture(self):
        if self._orig_stdout is not None:
            sys.stdout = self._orig_stdout
            self._orig_stdout = None
        if self._orig_stderr is not None:
            sys.stderr = self._orig_stderr
            self._orig_stderr = None
        self._log_stdout = None
        self._log_stderr = None
        if self._log_handler is not None:
            logging.getLogger().removeHandler(self._log_handler)
            self._log_handler = None

    def quit_application(self):
        """退出应用程序"""
        self.is_closing = True
        self._shutdown_all_download_workers()
        self._uninstall_main_log_capture()
        if hasattr(self, "tray_icon") and self.tray_icon is not None:
            self.tray_icon.hide()
        QApplication.quit()

    def _shutdown_all_download_workers(self):
        """退出前停掉所有下载 QThread，避免进程崩溃。"""
        for task in list(getattr(self, "download_tasks", []) or []):
            try:
                if hasattr(task, "shutdown_worker"):
                    task.shutdown_worker(wait_ms=5000)
            except Exception as exc:
                print(f"停止下载任务失败: {exc}")
    
    def closeEvent(self, event):
        """窗口关闭事件"""
        if self.is_closing:
            # 如果是真正退出，接受关闭事件
            self._shutdown_all_download_workers()
            self._uninstall_main_log_capture()
            event.accept()
            return
        
        # 弹出对话框让用户选择
        dialog = CustomMessageBox(
            self,
            "关闭窗口",
            "你想如何处理当前窗口？\n\n最小化到托盘：程序继续在后台运行\n直接退出：完全关闭程序",
            CustomMessageBox.QUESTION,
            ["最小化到托盘", "直接退出"]
        )
        
        result = dialog.exec()
        
        if result == QDialog.Accepted:
            # 获取用户点击的按钮索引
            button_index = dialog.result_index if hasattr(dialog, 'result_index') else 1
            
            if button_index == 0:  # 最小化到托盘
                event.ignore()
                self.minimize_to_tray()
            else:  # 直接退出
                self.quit_application()
                event.accept()
        else:
            # 用户取消，不关闭窗口
            event.ignore()
    
    def setup_menu(self):
        """设置菜单栏"""
        menubar = self.menuBar()
        
        # 文件菜单
        file_menu = menubar.addMenu("文件")
        
        open_action = QAction("打开下载目录", self)
        open_action.triggered.connect(self.open_download_folder)
        file_menu.addAction(open_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # 工具菜单
        tools_menu = menubar.addMenu("工具")
        
        # 设置选项
        settings_action = QAction("偏好设置", self)
        settings_action.triggered.connect(self.show_settings)
        tools_menu.addAction(settings_action)
        
        tools_menu.addSeparator()
        
        # 请求头配置
        headers_action = QAction("请求头配置", self)
        headers_action.triggered.connect(self.show_headers_dialog)
        tools_menu.addAction(headers_action)
        
        tools_menu.addSeparator()
        
        # M3U8搜索功能
        search_action = QAction("片源搜索", self)
        search_action.triggered.connect(self.show_m3u8_search_dialog)
        tools_menu.addAction(search_action)
        
        # 帮助菜单
        help_menu = menubar.addMenu("帮助")
        
        about_action = QAction("关于", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        
        # GitHub菜单 - 更可靠的显示方式
        github_menu = menubar.addMenu("GitHub")
        
        github_action = QAction("打开仓库主页", self)
        github_action.triggered.connect(self.open_github_repo)
        github_menu.addAction(github_action)
        
        # 可选：如果系统支持，仍然尝试在右上角添加按钮
        try:
            github_btn = QPushButton("GitHub")
            github_btn.setFixedSize(62, 28)
            github_btn.setFont(app_font(9, QFont.Bold))
            github_btn.setCursor(Qt.PointingHandCursor)
            github_btn.setToolTip("打开 GitHub 仓库")
            github_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(99, 102, 241, 0.08);
                    border: 1px solid rgba(99, 102, 241, 0.18);
                    border-radius: 12px;
                    color: #4338ca;
                    font-weight: bold;
                    padding: 0 10px;
                }
                QPushButton:hover {
                    background: rgba(99, 102, 241, 0.14);
                    border-color: rgba(99, 102, 241, 0.28);
                }
                QPushButton:pressed {
                    background: rgba(99, 102, 241, 0.20);
                }
            """)
            github_btn.clicked.connect(self.open_github_repo)
            menubar.setCornerWidget(github_btn, Qt.TopRightCorner)
        except Exception:
            # 如果角落组件不支持，忽略错误
            pass
    
    def open_github_repo(self):
        """打开GitHub仓库"""
        try:
            github_url = "https://github.com/shayuaidoudou/m3u8-downloader"
            QDesktopServices.openUrl(QUrl(github_url))
            self.statusBar().showMessage("正在打开 GitHub 仓库…")
        except Exception as e:
            self.statusBar().showMessage(f"打开GitHub失败: {str(e)}")
    
    def on_mode_changed(self, mode_text):
        """模式切换处理"""
        is_batch_mode = "批量" in mode_text
        self.url_input.setVisible(not is_batch_mode)
        self.batch_url_input.setVisible(is_batch_mode)
        
        # 调整批量输入框的高度
        if is_batch_mode:
            self.batch_url_input.setMinimumHeight(150)
            self.batch_url_input.setMaximumHeight(250)
        else:
            # 恢复默认高度
            self.batch_url_input.setMinimumHeight(120)
            self.batch_url_input.setMaximumHeight(200)
        
        # 更新按钮文本
        if is_batch_mode:
            self.add_task_btn.setText("批量加入队列")
            self.output_input.setPlaceholderText("选择保存文件夹")
        else:
            self.add_task_btn.setText("加入队列")
            self.output_input.setPlaceholderText("选择保存路径")
    
    def browse_output_path(self):
        """浏览输出路径"""
        is_batch_mode = "批量" in self.mode_combo.currentText()
        
        if is_batch_mode:
            # 批量模式选择文件夹
            folder_path = QFileDialog.getExistingDirectory(
                self, 
                "选择保存文件夹", 
                os.path.expanduser("~/Downloads")
            )
            if folder_path:
                self.output_input.setText(folder_path)
        else:
            # 单个模式选择文件
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "选择保存路径",
                os.path.expanduser("~/Downloads/video.mp4"),
                "MP4文件 (*.mp4);;TS文件 (*.ts);;所有文件 (*.*)"
            )
            if file_path:
                self.output_input.setText(file_path)
    
    def add_download_task(self):
        """添加下载任务"""
        is_batch_mode = "批量" in self.mode_combo.currentText()
        
        if is_batch_mode:
            self._add_batch_tasks()
        else:
            self._add_single_task()
    
    def _add_single_task(self):
        """添加单个下载任务"""
        url = self.url_input.text().strip()
        output_path = self.output_input.text().strip()
        task_name = self.task_name_input.text().strip()
        
        # 验证URL
        if not url:
            CustomMessageBox.show_warning(self, "提示", "请输入 M3U8 链接。")
            return
        
        if not is_valid_m3u8_url(url):
            CustomMessageBox.show_warning(self, "提示", "请输入有效的 M3U8 链接。")
            return
        
        # 验证输出路径
        if not output_path:
            CustomMessageBox.show_warning(self, "提示", "请选择保存路径。")
            return
        
        # 确保文件扩展名
        output_path = ensure_extension(output_path)
        
        # 验证输出路径
        is_valid, error_msg = validate_output_path(output_path)
        if not is_valid:
            CustomMessageBox.show_warning(self, "提示", f"输出路径不可用：{error_msg}")
            return
        
        # 避免文件名冲突
        output_path = get_available_filename(output_path)
        
        # 生成任务名称
        if not task_name:
            task_name = extract_title_from_url(url)
            if not task_name or task_name == "未知视频":
                task_name = f"下载任务_{len(self.download_tasks) + 1}"
        
        # 创建并添加任务
        self._create_task_widget(task_name, url, output_path)
        
        # 清空输入框
        self.url_input.clear()
        self.task_name_input.clear()
        
        # 显示任务信息
        headers_info = f" (包含 {len(self.custom_headers)} 个自定义请求头)" if self.custom_headers else ""
        self.statusBar().showMessage(f"已添加任务: {task_name}{headers_info}")
    
    def _add_batch_tasks(self):
        """添加批量下载任务"""
        urls_text = self.batch_url_input.toPlainText().strip()
        output_folder = self.output_input.text().strip()
        base_task_name = self.task_name_input.text().strip()
        
        # 验证输入
        if not urls_text:
            CustomMessageBox.show_warning(self, "提示", "请输入 M3U8 链接。")
            return
        
        if not output_folder:
            CustomMessageBox.show_warning(self, "提示", "请选择保存文件夹。")
            return
        
        if not os.path.exists(output_folder):
            CustomMessageBox.show_warning(self, "提示", "保存文件夹不存在。")
            return
        
        # 解析URL列表
        urls = []
        for line in urls_text.split('\n'):
            url = line.strip()
            if url and is_valid_m3u8_url(url):
                urls.append(url)
        
        if not urls:
            CustomMessageBox.show_warning(self, "提示", "没有找到有效的 M3U8 链接。")
            return
        
        # 确认批量添加
        reply = CustomMessageBox.show_question(
            self, 
            "批量添加",
            f"检测到 {len(urls)} 个有效链接，是否加入下载队列？\n\n任务会按照当前并发设置自动启动。"
        )
        
        if reply != QDialog.Accepted:
            return
        
        # 批量创建任务
        added_count = 0
        for i, url in enumerate(urls):
            try:
                # 生成任务名称
                if base_task_name:
                    task_name = f"{base_task_name}_{i+1:03d}"
                else:
                    extracted_name = extract_title_from_url(url)
                    if extracted_name and extracted_name != "未知视频":
                        task_name = f"{extracted_name}_{i+1:03d}"
                    else:
                        task_name = f"批量任务_{len(self.download_tasks) + i + 1:03d}"
                
                # 生成输出文件路径
                safe_name = "".join(c for c in task_name if c.isalnum() or c in (' ', '-', '_', '.')).rstrip()
                output_path = os.path.join(output_folder, f"{safe_name}.mp4")
                output_path = get_available_filename(output_path)
                
                # 创建任务
                self._create_task_widget(task_name, url, output_path)
                added_count += 1
                
            except Exception as e:
                print(f"创建任务失败 {i+1}: {e}")
                continue
        
        # 清空输入框
        self.batch_url_input.clear()
        self.task_name_input.clear()
        
        # 显示结果
        headers_info = f" (包含 {len(self.custom_headers)} 个自定义请求头)" if self.custom_headers else ""
        self.statusBar().showMessage(f"批量添加完成: {added_count}/{len(urls)} 个任务{headers_info}")
        
        # 自动开始下载队列中的任务
        self._process_download_queue()
    
    def _create_task_widget(self, task_name, url, output_path):
        """创建任务组件"""
        # 创建任务组件（包含自定义请求头）
        task_widget = DownloadTaskWidget(task_name, url, output_path, self.custom_headers.copy())
        
        # 连接任务完成信号
        task_widget.download_finished.connect(self._on_task_finished)
        
        # 插入到任务容器的最后一个位置（stretch之前）
        self.task_container_layout.insertWidget(
            self.task_container_layout.count() - 1, 
            task_widget
        )
        
        self.download_tasks.append(task_widget)
        
        # 更新进度概览
        self._update_progress_overview()
        
        return task_widget
    
    def clear_all_tasks(self):
        """清理已完成的下载任务"""
        if not self.download_tasks:
            CustomMessageBox.show_info(
                self,
                "提示",
                "当前还没有下载任务。"
            )
            return
        
        # 筛选出已完成的任务
        completed_tasks = []
        for task in self.download_tasks:
            # 通过状态文本判断任务是否完成
            if hasattr(task, 'status_label'):
                status_text = task.status_label.text()
                # 判断是否包含完成、失败或错误的关键词
                if any(keyword in status_text for keyword in ["完成", "失败", "错误", "成功"]):
                    # 如果有worker，确保它不在运行中
                    if hasattr(task, 'worker') and task.worker:
                        if not task.worker.isRunning():
                            completed_tasks.append(task)
                    else:
                        # 没有worker或worker为None，直接添加
                        completed_tasks.append(task)
        
        if not completed_tasks:
            CustomMessageBox.show_info(
                self,
                "提示",
                "当前没有可清理的任务。\n\n只有下载完成或失败的任务才会被清理。"
            )
            return
        
        # 确认删除
        reply = CustomMessageBox.show_question(
            self,
            "确认清理",
            f"发现 {len(completed_tasks)} 个已完成任务。\n\n确认清理这些任务吗？\n进行中的任务不会被删除。"
        )
        
        if reply == QDialog.Accepted:
            # 删除已完成的任务
            for task in completed_tasks:
                # 从任务列表中移除
                if task in self.download_tasks:
                    self.download_tasks.remove(task)
                
                # 从布局中移除
                task.setParent(None)
                task.deleteLater()
            
            # 更新进度概览
            self._update_progress_overview()
            
            # 更新状态栏
            self.statusBar().showMessage(f"已清理 {len(completed_tasks)} 个已完成任务")
            
            # 显示成功提示
            CustomMessageBox.show_success(
                self,
                "清理完成",
                f"已清理 {len(completed_tasks)} 个已完成任务。\n进行中的任务会继续保留。"
            )
    
    def open_download_folder(self):
        """打开下载文件夹"""
        if self.download_tasks:
            last_output = self.download_tasks[-1].output_path
            folder_path = os.path.dirname(last_output)
            if os.path.exists(folder_path):
                QDesktopServices.openUrl(QUrl.fromLocalFile(folder_path))
            else:
                CustomMessageBox.show_info(self, "提示", "下载文件夹不存在。")
        else:
            CustomMessageBox.show_info(self, "提示", "还没有下载任务，请先添加一个任务。")
    
    def show_settings(self):
        """显示设置对话框"""
        settings_dialog = SettingsDialog(self)
        settings_dialog.exec()
    
    def show_about(self):
        """显示关于对话框"""
        about_message = """M3U8 下载器 v1.0

基于 PySide6 的桌面端 HLS / M3U8 下载工具，界面采用简约工作台风格，将下载、任务队列、请求头配置与片源搜索放在同一处。

主要能力：
• 多线程下载与任务队列
• AES 加密流解密与 FFmpeg 合并
• 自定义请求头与模板
• 实时日志与进度概览
• 可选片源搜索与提取

开源地址：
github.com/shayuaidoudou/m3u8-downloader"""
        
        CustomMessageBox.show_info(
            self,
            "关于 M3U8 下载器",
            about_message
        )
    
    def apply_theme(self, theme_index):
        """应用主题颜色"""
        theme = get_theme(theme_index)
        self.current_theme_data = theme.copy()

        primary = theme.get('primary', UI_TOKENS['primary'])
        bg = theme.get('bg_start', UI_TOKENS['bg'])
        surface = theme.get('groupbox_bg', UI_TOKENS['surface'])
        text = theme.get('text_color', UI_TOKENS['text'])
        border = theme.get('input_border', UI_TOKENS['border'])
        input_bg = theme.get('input_bg', UI_TOKENS['surface'])
        radius_card = UI_TOKENS['radius_card']
        radius_control = UI_TOKENS['radius_control']

        self.setStyleSheet(f"""
            QMainWindow {{
                background: {bg};
            }}
            QWidget#top_bar {{
                background: transparent;
                border: none;
            }}
            QFrame#compose_card {{
                background: {surface};
                border: 1px solid {border};
                border-radius: {radius_card}px;
            }}
            QFrame#queue_section {{
                background: transparent;
                border: none;
            }}
            QLabel {{
                color: {text};
            }}
            QLineEdit {{
                background: {input_bg};
                border: 1px solid {border};
                border-radius: {radius_control}px;
                padding: 8px 12px;
                color: {text};
            }}
            QLineEdit:focus {{
                border-color: {primary};
            }}
            QTextEdit, QPlainTextEdit {{
                background: {input_bg};
                border: 1px solid {border};
                border-radius: {radius_control}px;
                padding: 8px 12px;
                color: {text};
            }}
            QTextEdit:focus, QPlainTextEdit:focus {{
                border-color: {primary};
            }}
            QComboBox {{
                background: {input_bg};
                border: 1px solid {border};
                border-radius: {radius_control}px;
                padding: 8px 12px;
                color: {text};
            }}
            QComboBox:focus {{
                border-color: {primary};
            }}
            QComboBox::down-arrow {{
                border-top-color: {primary};
            }}
            QSpinBox {{
                background: {input_bg};
                border: 1px solid {border};
                border-radius: {radius_control}px;
                padding: 8px 10px;
                color: {text};
            }}
            QSpinBox:focus {{
                border-color: {primary};
            }}
            QSpinBox::up-arrow {{
                border-bottom-color: {primary};
            }}
            QSpinBox::down-arrow {{
                border-top-color: {primary};
            }}
            QStatusBar {{
                background: {surface};
                border-top: 1px solid {border};
                color: {text};
                padding: 6px 10px;
            }}
            QMenuBar {{
                background: {surface};
                border-bottom: 1px solid {border};
                padding: 4px;
            }}
            QMenuBar::item {{
                padding: 6px 12px;
                border-radius: {radius_control}px;
                color: {text};
            }}
            QMenuBar::item:selected {{
                background: {UI_TOKENS['surface_alt']};
                color: {primary};
            }}
            QMenu {{
                background: {surface};
                border: 1px solid {border};
                border-radius: {radius_control}px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 8px 14px;
                border-radius: {radius_control}px;
                color: {text};
            }}
            QMenu::item:selected {{
                background: {UI_TOKENS['surface_alt']};
                color: {primary};
            }}
            QScrollBar:vertical {{
                background: {UI_TOKENS['surface_alt']};
                width: 8px;
                border-radius: {UI_TOKENS['radius_progress']}px;
            }}
            QScrollBar::handle:vertical {{
                background: {border};
                border-radius: {UI_TOKENS['radius_progress']}px;
                min-height: 24px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {primary};
            }}
            QProgressBar {{
                border: none;
                border-radius: {UI_TOKENS['radius_progress']}px;
                background: {UI_TOKENS['surface_alt']};
            }}
            QProgressBar::chunk {{
                border-radius: {UI_TOKENS['radius_progress']}px;
                background: {primary};
            }}
        """)

        self._apply_dashboard_accents(theme)
        print(f"已应用主题: {theme_index} - {get_theme_name(theme_index)}")
    
    def _theme_hex_to_rgb(self, hex_color):
        """将十六进制颜色转换为RGB（用于主题）"""
        hex_color = hex_color.lstrip('#')
        return ', '.join(str(int(hex_color[i:i+2], 16)) for i in (0, 2, 4))
    
    def load_user_settings(self):
        """启动时加载用户设置"""
        settings_file = get_settings_path()
        
        try:
            if os.path.exists(settings_file):
                with open(settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                
                # 应用UI设置
                ui = settings.get('ui', {})
                opacity = ui.get('opacity', 95) / 100.0
                self.setWindowOpacity(opacity)
                
                # 应用主题设置
                theme_index = ui.get('theme_color', 0)
                self.apply_theme(theme_index)
                
                # 应用下载设置
                download = settings.get('download', {})
                
                # 设置默认线程数
                default_threads = download.get('default_threads', DEFAULT_CONFIG['max_workers'])
                if hasattr(self, 'threads_spin'):
                    self.threads_spin.setValue(default_threads)
                
                # 设置默认保存路径
                default_path = download.get('default_path', '')
                if default_path and os.path.exists(default_path) and hasattr(self, 'output_input'):
                    self.output_input.setText(default_path)
                
                print(f"已加载用户设置: 线程数={default_threads}, 路径={default_path}, 主题={theme_index}")
                
        except Exception as e:
            print(f"️ 加载用户设置失败: {e}")
            # 继续使用默认设置
    
    def _on_task_finished(self, success):
        """任务完成回调"""
        self.active_downloads -= 1
        print(f"[DEBUG] 任务完成，当前活跃下载数: {self.active_downloads}")
        
        # 处理队列中的下一个任务
        self._process_download_queue()
    
    def _process_download_queue(self):
        """处理下载队列"""
        max_concurrent = self.concurrent_spin.value()
        
        # 找到等待中的任务并开始下载
        for task in self.download_tasks:
            if self.active_downloads >= max_concurrent:
                break
                
            # 检查任务是否在等待状态
            if hasattr(task, 'status_label') and "准备中" in task.status_label.text():
                try:
                    self.active_downloads += 1
                    task.start_download()
                    print(f"[DEBUG] 自动启动任务: {task.task_name}, 当前活跃下载数: {self.active_downloads}")
                except Exception as e:
                    self.active_downloads -= 1
                    print(f"[ERROR] 启动任务失败: {e}")
        
        # 更新状态栏和进度概览
        waiting_count = sum(1 for task in self.download_tasks 
                          if hasattr(task, 'status_label') and "准备中" in task.status_label.text())
        if waiting_count > 0:
            self.statusBar().showMessage(f"活跃下载: {self.active_downloads}/{max_concurrent}, 等待中: {waiting_count}")
        else:
            self.statusBar().showMessage(f"活跃下载: {self.active_downloads}/{max_concurrent}")
        
        # 更新进度概览
        self._update_progress_overview()
    
    def _update_progress_overview(self):
        """更新进度概览"""
        if not self.download_tasks:
            self.progress_overview.setVisible(False)
            if hasattr(self, 'empty_state_card'):
                self.empty_state_card.setVisible(True)
                self._start_empty_state_animation()
            if hasattr(self, 'clear_all_tasks_btn'):
                self.clear_all_tasks_btn.setEnabled(False)
            self._update_active_pulse_state(0)
            self._stat_counts = {
                'total': 0, 'active': 0, 'waiting': 0, 'completed': 0, 'failed': 0,
            }
            return
        
        self.progress_overview.setVisible(True)
        if hasattr(self, 'empty_state_card'):
            self.empty_state_card.setVisible(False)
            self._stop_empty_state_animation()
        
        # 统计各种状态的任务数
        total_tasks = len(self.download_tasks)
        active_count = self.active_downloads
        waiting_count = 0
        completed_count = 0
        failed_count = 0
        
        for task in self.download_tasks:
            if hasattr(task, 'status_label'):
                status_text = task.status_label.text()
                if "准备中" in status_text or "等待中" in status_text:
                    waiting_count += 1
                elif "完成" in status_text:
                    completed_count += 1
                elif "失败" in status_text or "错误" in status_text:
                    failed_count += 1
        
        new_counts = {
            'total': total_tasks,
            'active': active_count,
            'waiting': waiting_count,
            'completed': completed_count,
            'failed': failed_count,
        }
        pill_map = {
            'total': (self.total_tasks_label, UI_TOKENS['primary']),
            'active': (self.active_downloads_label, UI_TOKENS['primary']),
            'waiting': (self.waiting_tasks_label, UI_TOKENS['warning']),
            'completed': (self.completed_tasks_label, UI_TOKENS['success']),
            'failed': (self.failed_tasks_label, UI_TOKENS['danger']),
        }
        for key, (label, _) in pill_map.items():
            if new_counts[key] != self._stat_counts.get(key, -1):
                self._flash_overview_pill(label)
        self._stat_counts = new_counts

        # 更新标签
        self.total_tasks_label.setText(f"总任务 {total_tasks}")
        self.active_downloads_label.setText(f"活跃 {active_count}")
        self.waiting_tasks_label.setText(f"等待 {waiting_count}")
        self.completed_tasks_label.setText(f"完成 {completed_count}")
        self.failed_tasks_label.setText(f"失败 {failed_count}")
        self.progress_summary_label.setText(f"并发上限 {self.concurrent_spin.value()} · 已完成 {completed_count + failed_count}/{total_tasks}")
        self.clear_all_tasks_btn.setEnabled((completed_count + failed_count) > 0)
        self._update_active_pulse_state(active_count)
        
        # 计算整体进度
        if total_tasks > 0:
            progress = (completed_count + failed_count) / total_tasks * 100
            self.overall_progress.setValue(int(progress))
        else:
            self.overall_progress.setValue(0)

    def _update_active_pulse_state(self, active_count):
        """活跃下载 > 0 时脉冲高亮活跃 pill"""
        if active_count > 0:
            if not self._active_pulse_timer.isActive():
                self._active_pulse_bright = False
                self._active_pulse_timer.start()
        else:
            self._active_pulse_timer.stop()
            self._active_pulse_bright = False
            if hasattr(self, 'active_downloads_label'):
                color = getattr(self, '_active_pill_color', UI_TOKENS['primary'])
                self._apply_overview_pill_style(self.active_downloads_label, color, bright=False)

    def _toggle_active_pulse(self):
        """切换活跃下载 pill 的背景亮度"""
        if not hasattr(self, 'active_downloads_label'):
            return
        self._active_pulse_bright = not self._active_pulse_bright
        color = getattr(self, '_active_pill_color', UI_TOKENS['primary'])
        self._apply_overview_pill_style(
            self.active_downloads_label,
            color,
            bright=self._active_pulse_bright,
        )

    def _start_empty_state_animation(self):
        """空状态图标呼吸动画"""
        if self._empty_anim_running or not hasattr(self, 'empty_state_icon'):
            return
        effect = QGraphicsOpacityEffect(self.empty_state_icon)
        effect.setOpacity(1.0)
        self.empty_state_icon.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(1400)
        anim.setStartValue(0.55)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.InOutSine)
        anim.setLoopCount(-1)
        anim.start()
        self._empty_anim = anim
        self._empty_anim_running = True

    def _stop_empty_state_animation(self):
        """停止空状态动画"""
        if not self._empty_anim_running:
            return
        if self._empty_anim is not None:
            self._empty_anim.stop()
            self._empty_anim = None
        if hasattr(self, 'empty_state_icon'):
            self.empty_state_icon.setGraphicsEffect(None)
        self._empty_anim_running = False

    def showEvent(self, event):
        """窗口首次显示时淡入主内容区"""
        super().showEvent(event)
        if not self._entrance_done:
            self._entrance_done = True
            self._play_entrance_animation()

    def _play_entrance_animation(self):
        """主内容区 0→1 淡入（窗口透明度仍由设置控制）"""
        surface = getattr(self, '_main_surface', None) or self.centralWidget()
        if surface is None:
            return
        effect = QGraphicsOpacityEffect(surface)
        effect.setOpacity(0.0)
        surface.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(250)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.finished.connect(lambda: surface.setGraphicsEffect(None))
        anim.start()
        self._entrance_anim = anim


GLOBAL_STYLESHEET = f"""
    QWidget {{
        background-color: {UI_TOKENS['bg']};
        color: {UI_TOKENS['text']};
    }}
    QMenuBar {{
        background: {UI_TOKENS['bg']};
        color: {UI_TOKENS['text']};
        border-bottom: 1px solid {UI_TOKENS['border']};
        padding: 4px 8px;
        font-size: 13px;
    }}
    QMenuBar::item {{
        background: transparent;
        padding: 5px 12px;
        border-radius: 6px;
        margin: 0 2px;
    }}
    QMenuBar::item:selected {{
        background: {UI_TOKENS['surface_alt']};
        color: {UI_TOKENS['primary']};
    }}
    QMenu {{
        background: {UI_TOKENS['surface']};
        color: {UI_TOKENS['text']};
        border: 1px solid {UI_TOKENS['border']};
        border-radius: 8px;
        padding: 6px;
    }}
    QMenu::item {{
        padding: 7px 18px 7px 14px;
        border-radius: 6px;
        min-width: 140px;
    }}
    QMenu::item:selected {{
        background: {UI_TOKENS['surface_alt']};
        color: {UI_TOKENS['primary']};
    }}
    QMenu::separator {{
        height: 1px;
        background: {UI_TOKENS['border']};
        margin: 4px 8px;
    }}
    QStatusBar {{
        background: {UI_TOKENS['surface']};
        color: {UI_TOKENS['text_muted']};
        border-top: 1px solid {UI_TOKENS['border']};
        padding: 4px 12px;
        font-size: 12px;
    }}
    QStatusBar::item {{
        border: none;
    }}
    QToolTip {{
        background: {UI_TOKENS['text']};
        color: #FFFFFF;
        border: none;
        border-radius: 6px;
        padding: 6px 10px;
        font-size: 12px;
    }}
    QScrollBar:vertical {{
        border: none;
        background: transparent;
        width: 10px;
        margin: 4px 2px 4px 0;
    }}
    QScrollBar::handle:vertical {{
        background: {UI_TOKENS['border_strong']};
        border-radius: 4px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {UI_TOKENS['text_subtle']};
    }}
    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical,
    QScrollBar::add-page:vertical,
    QScrollBar::sub-page:vertical {{
        background: none;
        border: none;
        height: 0;
    }}
    QScrollBar:horizontal {{
        border: none;
        background: transparent;
        height: 10px;
        margin: 0 4px 2px 4px;
    }}
    QScrollBar::handle:horizontal {{
        background: {UI_TOKENS['border_strong']};
        border-radius: 4px;
        min-width: 30px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {UI_TOKENS['text_subtle']};
    }}
    QScrollBar::add-line:horizontal,
    QScrollBar::sub-line:horizontal,
    QScrollBar::add-page:horizontal,
    QScrollBar::sub-page:horizontal {{
        background: none;
        border: none;
        width: 0;
    }}
"""


def main():
    """主函数"""
    app = QApplication(sys.argv)
    app.setApplicationName("M3U8 下载器")
    app.setOrganizationName("M3U8Downloader")

    app_font_obj = QFont()
    app_font_obj.setFamilies([
        "PingFang SC",
        "Microsoft YaHei UI",
        "Microsoft YaHei",
        "Noto Sans SC",
        "Source Han Sans SC",
        "Helvetica Neue",
        "Segoe UI",
        "Arial",
    ])
    app_font_obj.setPointSize(10)
    app_font_obj.setHintingPreference(QFont.PreferNoHinting)
    app.setFont(app_font_obj)
    app.setStyleSheet(GLOBAL_STYLESHEET)
    
    # 设置应用图标
    try:
        icon_path = resolve_app_icon()
        if icon_path:
            app.setWindowIcon(QIcon(icon_path))
    except Exception as e:
        print(f"设置应用图标失败: {e}")
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
