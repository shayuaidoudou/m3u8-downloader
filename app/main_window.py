"""Main-window composition root.

The concrete window intentionally contains only state initialisation.  View
construction, OS lifecycle integration and queue behavior live in focused
mixins with explicit dependencies.
"""

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QMainWindow

from .main_window_lifecycle import MainWindowLifecycleMixin
from .main_window_queue import MainWindowQueueMixin
from .main_window_ui import MainWindowUiMixin


class MainWindow(
    MainWindowUiMixin,
    MainWindowLifecycleMixin,
    MainWindowQueueMixin,
    QMainWindow,
):
    """Compose the application's view, lifecycle and task-queue concerns."""

    log_message = Signal(str, str)

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
        self._queue_filter = 'all'
        self._filter_chips = {}
        self._tool_buttons = []
        self.effects_enabled = True
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
