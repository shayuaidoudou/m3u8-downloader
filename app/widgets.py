"""Reusable Qt widgets and the per-download task worker."""

from PySide6.QtCore import QSize, Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from config import DEFAULT_CONFIG, UI_TOKENS
from m3u8_downloader import M3U8Downloader
from theme import FONT_BODY, FONT_CAPTION, app_font, polish_widget, qta_icon

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
    """统一按钮：primary / default / danger，样式由全局 QSS 的 variant 属性驱动。"""

    def __init__(self, text, primary=False, icon_text="", variant=None, icon_name=None):
        super().__init__(text)
        self.primary = primary
        self.icon_text = icon_text
        self._variant = variant or ('primary' if primary else 'default')
        self.setMinimumHeight(36)
        self.setFont(app_font(FONT_BODY, QFont.DemiBold))
        self.setCursor(Qt.PointingHandCursor)
        self.setProperty("variant", self._variant)
        if icon_name:
            self.setProperty("icon_name", icon_name)
            if self._variant == 'primary':
                color = '#0A0E1A'
            elif self._variant == 'danger':
                color = UI_TOKENS['danger']
            else:
                color = UI_TOKENS['text_muted']
            self.setIcon(qta_icon(icon_name, color=color))
            self.setIconSize(QSize(16, 16))
        elif icon_text:
            self.setText(f"{icon_text} {text}")
        polish_widget(self)

    def _apply_variant(self):
        self.setProperty("variant", self._variant)
        polish_widget(self)


class ModernLineEdit(QLineEdit):
    """现代极简输入框（样式走全局 QSS）"""

    def __init__(self, placeholder="", icon_text=""):
        super().__init__()
        self.setPlaceholderText(placeholder)
        self.setMinimumHeight(40)
        self.setFont(app_font(FONT_BODY))
        self.setClearButtonEnabled(True)
        if icon_text:
            self.setPlaceholderText(f"{icon_text} {placeholder}")


class ModernProgressBar(QProgressBar):
    """现代极简进度条（样式走全局 QSS）"""

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(6)
        self.setMaximumHeight(8)
        self.setTextVisible(False)


class DownloadTaskWidget(QFrame):
    """下载任务组件（紧凑行卡；操作按钮悬停显示）"""

    # 定义信号
    download_finished = Signal(bool)

    def __init__(self, task_name, url, output_path, custom_headers=None):
        super().__init__()
        self.task_name = task_name
        self.url = url
        self.output_path = output_path
        self.custom_headers = custom_headers or {}
        self.worker = None
        self.downloader = None
        self._actions_pinned = False

        self.setFrameStyle(QFrame.NoFrame)
        self.setAttribute(Qt.WA_Hover, True)
        self._apply_card_style()
        self.setup_ui()

    def _apply_card_style(self, accent_color=None, border_color=None, hover_color=None):
        """卡片：渐变表面 + 左侧状态色竖条，hover 时边框提亮。"""
        accent = accent_color or getattr(self, '_accent_color', None) or UI_TOKENS['primary']
        border = border_color or UI_TOKENS['border']
        hover_border = hover_color or UI_TOKENS['border_strong']
        radius = UI_TOKENS['radius_card']
        self._accent_color = accent
        self.setStyleSheet(f"""
            QFrame#task_card {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {UI_TOKENS['surface_alt']}, stop:0.2 {UI_TOKENS['surface']},
                    stop:1 {UI_TOKENS['surface']});
                border-radius: {radius}px;
                border: 1px solid {border};
                border-left: 3px solid {accent};
            }}
            QFrame#task_card:hover {{
                border-color: {hover_border};
                border-left: 3px solid {accent};
                background: {UI_TOKENS['surface_alt']};
            }}
        """)
        if hasattr(self, 'status_dot'):
            self.status_dot.setStyleSheet(
                f"background: {accent}; border-radius: 4px; border: none;"
            )

    def _set_status_accent(self, color):
        """状态竖条、圆点与状态文字同步"""
        self._apply_card_style(accent_color=color)
        if hasattr(self, 'status_label'):
            self.status_label.setStyleSheet(
                f"color: {color}; background: transparent; border: none;"
            )

    def _make_action_btn(self, icon_name, tooltip, variant='default'):
        btn = QPushButton()
        btn.setObjectName("task_action_btn")
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedSize(30, 30)
        if variant == 'danger':
            btn.setProperty("variant", "danger")
            color = UI_TOKENS['danger']
        else:
            color = UI_TOKENS['text_muted']
        btn.setIcon(qta_icon(icon_name, color=color))
        btn.setIconSize(QSize(16, 16))
        polish_widget(btn)
        return btn

    def setup_ui(self):
        """设置UI — 紧凑行卡"""
        self.setObjectName("task_card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # 标题行：圆点 + 任务名 + 状态 + 操作（悬停）
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        self.status_dot = QLabel()
        self.status_dot.setFixedSize(8, 8)
        self.status_dot.setStyleSheet(
            f"background: {UI_TOKENS['primary']}; border-radius: 4px; border: none;"
        )
        header_layout.addWidget(self.status_dot, 0, Qt.AlignVCenter)

        title_label = QLabel(self.task_name)
        title_label.setFont(app_font(FONT_BODY, QFont.DemiBold))
        title_label.setStyleSheet(f"color: {UI_TOKENS['text']}; background: transparent; border: none;")
        title_label.setMinimumWidth(0)
        header_layout.addWidget(title_label, 1)

        self.status_label = QLabel("准备中")
        self.status_label.setFont(app_font(FONT_CAPTION, QFont.DemiBold))
        self.status_label.setStyleSheet(
            f"color: {UI_TOKENS['primary']}; background: transparent; border: none;"
        )
        header_layout.addWidget(self.status_label, 0, Qt.AlignVCenter)

        self.actions_wrap = QWidget()
        self.actions_wrap.setObjectName("task_actions")
        actions_layout = QHBoxLayout(self.actions_wrap)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(4)

        self.start_btn = self._make_action_btn("fa5s.play", "开始")
        self.start_btn.clicked.connect(self.start_download)
        actions_layout.addWidget(self.start_btn)

        self.stop_btn = self._make_action_btn("fa5s.pause", "暂停")
        self.stop_btn.clicked.connect(self.stop_download)
        self.stop_btn.setEnabled(False)
        actions_layout.addWidget(self.stop_btn)

        self.delete_btn = self._make_action_btn("fa5s.trash", "删除", variant='danger')
        self.delete_btn.clicked.connect(self.delete_task)
        actions_layout.addWidget(self.delete_btn)

        self.actions_wrap.setVisible(False)
        header_layout.addWidget(self.actions_wrap, 0, Qt.AlignVCenter)

        layout.addLayout(header_layout)

        # 单行元数据
        url_display = self.url if len(self.url) <= 56 else f"{self.url[:53]}..."
        out_display = self.output_path if len(self.output_path) <= 40 else f"...{self.output_path[-37:]}"
        meta_label = QLabel(f"{url_display}  ·  {out_display}")
        meta_label.setFont(app_font(FONT_CAPTION))
        meta_label.setStyleSheet(
            f"color: {UI_TOKENS['text_subtle']}; background: transparent; border: none;"
        )
        meta_label.setWordWrap(False)
        layout.addWidget(meta_label)

        self.progress_bar = ModernProgressBar()
        self.progress_bar.setMaximumHeight(5)
        self.progress_bar.setMinimumHeight(5)
        layout.addWidget(self.progress_bar)
        self._apply_card_style()

    def enterEvent(self, event):
        self.actions_wrap.setVisible(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self._actions_pinned:
            self.actions_wrap.setVisible(False)
        super().leaveEvent(event)

    def start_download(self):
        """开始下载"""
        # 若已有线程，先安全停掉，避免旧 QThread 被覆盖后崩溃
        self.shutdown_worker(wait_ms=3000)
        self.cleanup_incomplete_artifacts()

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.delete_btn.setEnabled(False)  # 下载时禁用删除
        self._actions_pinned = True
        self.actions_wrap.setVisible(True)
        self._set_status_accent(UI_TOKENS['primary'])

        # 获取主窗口的线程数设置
        main_window = self._find_main_window()

        max_workers = DEFAULT_CONFIG['max_workers']
        if main_window and hasattr(main_window, 'threads_spin'):
            max_workers = main_window.threads_spin.value()

        # 创建下载器和工作线程（父对象绑定到任务卡片，随卡片生命周期管理）
        self.downloader = M3U8Downloader(custom_headers=self.custom_headers)
        self.worker = DownloadWorker(
            self.downloader,
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

    def cleanup_incomplete_artifacts(self):
        """清理该任务尚未发布的分片和合并暂存文件。"""
        downloader = self.downloader
        if downloader is None or not hasattr(downloader, 'cleanup_incomplete_artifacts'):
            return True
        return downloader.cleanup_incomplete_artifacts()

    def stop_download(self):
        """停止下载"""
        self.shutdown_worker(wait_ms=8000)
        self.cleanup_incomplete_artifacts()

        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.delete_btn.setEnabled(True)
        self._actions_pinned = False
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
        self._actions_pinned = False

        self.download_finished.emit(success)

        if success:
            self.progress_bar.setValue(100)
            self.status_label.setText("下载完成")
            self._set_status_accent(UI_TOKENS['success'])
            self._apply_card_style(
                accent_color=UI_TOKENS['success'],
                border_color=UI_TOKENS.get('border', UI_TOKENS['success']),
            )
            if main_window:
                main_window.statusBar().showMessage(
                    f"已完成：{self.task_name} → {self.output_path}", 6000
                )
        else:
            self.status_label.setText("下载失败")
            self._set_status_accent(UI_TOKENS['danger'])
            self._apply_card_style(
                accent_color=UI_TOKENS['danger'],
                border_color=UI_TOKENS['danger'],
            )

            if main_window:
                from .dialogs import CustomMessageBox

                CustomMessageBox.show_error(
                    main_window,
                    "下载失败",
                    f"任务“{self.task_name}”下载失败。\n\n可能的原因：\n• 网络连接问题\n• M3U8 链接失效\n• 视频源访问受限\n\n请检查链接或稍后重试。"
                )

    def _find_main_window(self):
        """查找主窗口"""
        # Lazy import keeps the widget module independent from MainWindow and
        # avoids a module-level circular dependency.
        from .main_window import MainWindow

        parent = self.parent()
        while parent and not isinstance(parent, MainWindow):
            parent = parent.parent()
        return parent

    def delete_task(self):
        """删除任务"""
        # 先停线程，再确认删除，避免确认期间线程结束回调碰已删对象
        self.shutdown_worker(wait_ms=8000)
        self.cleanup_incomplete_artifacts()

        # 确认删除
        main_window = self._find_main_window()
        from .dialogs import CustomMessageBox

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
                main_window = self._find_main_window()

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
