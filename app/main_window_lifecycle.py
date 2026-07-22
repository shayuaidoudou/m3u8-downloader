"""Lifecycle, logging, tray and menu integration for the main window."""

import logging
import os
import sys
import threading

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QAction, QDesktopServices, QFont, QIcon
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMenu, QPushButton, QSystemTrayIcon

from config import UI_TOKENS
from theme import app_font
from .headers_dialog import HeadersDialog
from .message_box import CustomMessageBox
from .search_dialog import M3u8SearchDialog
from .ui_support import append_spring_boot_log, resolve_app_icon


class MainWindowLifecycleMixin:
    """Own operating-system integration and application shutdown behavior."""

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
        """退出前停掉下载线程，并清理未完成任务的专属工作区。"""
        for task in list(getattr(self, "download_tasks", []) or []):
            try:
                if hasattr(task, "shutdown_worker"):
                    task.shutdown_worker(wait_ms=5000)
                if hasattr(task, "cleanup_incomplete_artifacts"):
                    task.cleanup_incomplete_artifacts()
            except Exception as exc:
                print(f"停止并清理下载任务失败: {exc}")

    def closeEvent(self, event):
        """窗口关闭事件"""
        if self.is_closing:
            # 如果是真正退出，接受关闭事件
            self._shutdown_all_download_workers()
            self._uninstall_main_log_capture()
            event.accept()
            return

        # 队列为空时无需询问是否留在托盘，直接执行完整退出清理。
        if not getattr(self, "download_tasks", None):
            self.quit_application()
            event.accept()
            return

        # 弹出对话框让用户选择
        dialog = CustomMessageBox(
            self,
            "关闭窗口",
            "你想如何处理当前窗口？\n\n最小化到托盘：程序继续在后台运行\n直接退出：停止未完成任务并清理临时文件",
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
