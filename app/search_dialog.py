"""Search-dialog composition root."""

from PySide6.QtWidgets import QDialog

from .route_dialog import SearchSignals
from .search_dialog_view import SearchDialogViewMixin
from .search_dialog_workflow import SearchDialogWorkflowMixin


class M3u8SearchDialog(SearchDialogViewMixin, SearchDialogWorkflowMixin, QDialog):
    """Compose the search view and asynchronous extraction workflow."""

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
