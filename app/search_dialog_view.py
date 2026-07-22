"""View construction, engine selection and log capture for search dialog."""

import json
import logging
import os
import sys
import threading

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config import UI_TOKENS
from search import (
    CHANNEL_INPUT_COOKIE,
    CHANNEL_INPUT_TYPE,
    IYF_CHANNEL,
    SEARCH_CHANNELS,
    create_search_engine,
    get_channel_input_mode,
)
from theme import DIALOG_BODY, DIALOG_GROUP_TITLE, DIALOG_LABEL, app_font
from utils import log_console_stylesheet
from .ui_support import append_spring_boot_log, get_settings_path
from .widgets import ModernButton


class SearchDialogViewMixin:
    """Own search-dialog widgets, engine switching and log presentation."""

    def setup_ui(self):
        """设置UI界面"""
        self.setWindowTitle("M3U8 搜索器")
        self.setMinimumSize(1100, 700)
        self.setModal(False)
        self.setFont(app_font(DIALOG_BODY))

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 16, 20, 16)
        main_layout.setSpacing(14)

        # 搜索区域
        search_group = QGroupBox("搜索设置")
        search_group.setFont(app_font(DIALOG_GROUP_TITLE, QFont.Bold))
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
        keyword_label.setFont(app_font(DIALOG_LABEL, QFont.DemiBold))
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
        self.type_label.setFont(app_font(DIALOG_LABEL, QFont.DemiBold))
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
        self.ncat_cookie_label.setFont(app_font(DIALOG_LABEL, QFont.DemiBold))
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
        engine_label.setFont(app_font(DIALOG_LABEL, QFont.DemiBold))
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
        results_group.setFont(app_font(DIALOG_GROUP_TITLE, QFont.Bold))
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
                font-size: {DIALOG_LABEL}px;
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
