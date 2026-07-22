"""Presentation and view-construction mixin for the main window."""

import platform

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QTimer, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizeGrip,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config import DEFAULT_CONFIG, UI_TOKENS, get_theme, merge_theme_tokens
from theme import (
    FONT_BODY,
    FONT_CAPTION,
    FONT_TITLE,
    TitleBar,
    app_font,
    apply_drop_shadow,
    apply_glow,
    polish_widget,
    qta_icon,
)
from utils import log_console_stylesheet
from .effects import (
    AmbientWorkspace,
    ComposeEnergyCard,
    EmptyStateVisual,
    EnergyBorderCard,
    enable_button_shine,
)
from .ui_support import resolve_app_icon
from .widgets import ModernButton, ModernLineEdit, ModernProgressBar


class MainWindowUiMixin:
    """Build and restyle the main window without owning application state."""

    COMPOSE_PANEL_MIN_WIDTH = 360
    COMPOSE_PANEL_MAX_WIDTH = 420

    def setup_ui(self):
        """设置UI"""
        self.setWindowTitle("M3U8 下载器 v1.0")
        self.setMinimumSize(1000, 720)
        self.resize(1100, 800)
        # macOS 无边框会丢系统红绿灯且工具区易被样式吞掉；主窗用原生标题栏更稳
        self._use_custom_chrome = platform.system() != "Darwin"
        if self._use_custom_chrome:
            self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)

        try:
            icon_path = resolve_app_icon()
            if icon_path:
                self.setWindowIcon(QIcon(icon_path))
        except Exception as e:
            print(f"设置窗口图标失败: {e}")

        shell = QWidget()
        shell.setObjectName("main_shell")
        self.setCentralWidget(shell)
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        self.title_bar = None
        if self._use_custom_chrome:
            self.title_bar = TitleBar(self, title="M3U8 下载器")
            self.title_bar.minimize_requested.connect(self.showMinimized)
            self.title_bar.maximize_requested.connect(self._toggle_maximize)
            self.title_bar.close_requested.connect(self.close)
            self.title_bar.set_menu_actions([
                ("打开下载目录", self.open_download_folder),
                ("偏好设置", self.show_settings),
                None,
                ("请求头配置", self.show_headers_dialog),
                ("片源搜索", self.show_m3u8_search_dialog),
                None,
                ("关于", self.show_about),
                ("打开 GitHub 仓库", self.open_github_repo),
                None,
                ("退出", self.close),
            ])
            shell_layout.addWidget(self.title_bar)

        central_widget = QWidget()
        central_widget.setObjectName("main_surface")
        self._main_surface = central_widget
        shell_layout.addWidget(central_widget, 1)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.top_bar = QFrame()
        self.top_bar.setObjectName("top_bar")
        top_bar_layout = QHBoxLayout(self.top_bar)
        top_bar_layout.setContentsMargins(18, 10, 14, 10)
        top_bar_layout.setSpacing(10)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(10)

        self.brand_icon = QLabel()
        self.brand_icon.setFixedSize(32, 32)
        self.brand_icon.setAlignment(Qt.AlignCenter)
        icon_path = resolve_app_icon()
        if icon_path:
            pix = QPixmap(icon_path).scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.brand_icon.setPixmap(pix)
        else:
            self.brand_icon.setPixmap(qta_icon("fa5s.play-circle", color=UI_TOKENS['primary']).pixmap(28, 28))
        brand_row.addWidget(self.brand_icon, 0, Qt.AlignVCenter)

        brand_text_layout = QVBoxLayout()
        brand_text_layout.setContentsMargins(0, 0, 0, 0)
        brand_text_layout.setSpacing(0)

        self.app_title = QLabel("M3U8 下载器")
        self.app_title.setProperty("role", "title")
        self.app_title.setFont(app_font(FONT_TITLE, QFont.DemiBold))
        brand_text_layout.addWidget(self.app_title)

        self.app_subtitle = QLabel("轻量抓取 · 稳定合并")
        self.app_subtitle.setProperty("role", "subtitle")
        self.app_subtitle.setStyleSheet(f"color: {UI_TOKENS['text_muted']};")
        self.app_subtitle.setFont(app_font(FONT_CAPTION))
        brand_text_layout.addWidget(self.app_subtitle)
        brand_row.addLayout(brand_text_layout)
        top_bar_layout.addLayout(brand_row)
        top_bar_layout.addStretch()

        # 右上角：金底主按钮 + 描边次按钮，始终保留文字以确保操作可识别。
        self.search_tool_btn = self._create_header_action(
            "搜索", "fa5s.search", self.show_m3u8_search_dialog, primary=True
        )
        self.headers_tool_btn = self._create_header_action(
            "请求头", "fa5s.code", self.show_headers_dialog
        )
        self.folder_tool_btn = self._create_header_action(
            "下载目录", "fa5s.folder-open", self.open_download_folder
        )
        self.settings_tool_btn = self._create_header_action(
            "设置", "fa5s.cog", self.show_settings
        )
        for btn in (
            self.search_tool_btn,
            self.headers_tool_btn,
            self.folder_tool_btn,
            self.settings_tool_btn,
        ):
            top_bar_layout.addWidget(btn)
        apply_glow(self.search_tool_btn, color=UI_TOKENS['primary'], blur=18, alpha=90)
        enable_button_shine(self.search_tool_btn, interval_ms=3900)

        main_layout.addWidget(self.top_bar, 0)

        workspace = AmbientWorkspace()
        workspace.setObjectName("workspace")
        self.workspace = workspace
        workspace_layout = QHBoxLayout(workspace)
        workspace_layout.setContentsMargins(14, 12, 14, 12)
        workspace_layout.setSpacing(14)

        self.compose_card = ComposeEnergyCard()
        self.compose_card.setObjectName("compose_card")
        self.compose_card.setMinimumWidth(self.COMPOSE_PANEL_MIN_WIDTH)
        self.compose_card.setMaximumWidth(self.COMPOSE_PANEL_MAX_WIDTH)
        compose_outer = QVBoxLayout(self.compose_card)
        compose_outer.setContentsMargins(0, 0, 0, 0)
        compose_outer.setSpacing(0)

        compose_scroll = QScrollArea()
        compose_scroll.setObjectName("compose_scroll")
        compose_scroll.setWidgetResizable(True)
        compose_scroll.setFrameShape(QFrame.NoFrame)
        compose_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        compose_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        compose_scroll.setStyleSheet("""
            QScrollArea#compose_scroll {
                background: transparent;
                border: none;
            }
            QScrollArea#compose_scroll > QWidget > QWidget {
                background: transparent;
            }
        """)

        compose_form = QWidget()
        compose_form.setObjectName("compose_form")
        compose_layout = QVBoxLayout(compose_form)
        compose_layout.setContentsMargins(14, 14, 14, 10)
        compose_layout.setSpacing(10)

        self.compose_title = QLabel("新建下载")
        self.compose_title.setProperty("role", "title")
        self.compose_title.setFont(app_font(FONT_TITLE, QFont.DemiBold))
        compose_layout.addWidget(self.compose_title)

        self.compose_desc = QLabel("粘贴链接，加入后自动排队。")
        self.compose_desc.setProperty("role", "subtitle")
        self.compose_desc.setFont(app_font(FONT_CAPTION))
        self.compose_desc.setWordWrap(True)
        compose_layout.addWidget(self.compose_desc)

        mode_label = self._create_form_label("输入方式")
        compose_layout.addWidget(mode_label)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["单个链接", "批量链接"])
        self.mode_combo.setMinimumHeight(36)
        self.mode_combo.currentTextChanged.connect(self.on_mode_changed)
        compose_layout.addWidget(self.mode_combo)

        url_label = self._create_form_label("视频链接")
        compose_layout.addWidget(url_label)

        self.url_input = ModernLineEdit("请输入 M3U8 视频链接")
        self.url_input.setMinimumHeight(36)
        self.url_input.returnPressed.connect(self.add_download_task)
        compose_layout.addWidget(self.url_input)

        self.batch_url_input = QTextEdit()
        self.batch_url_input.setPlaceholderText("每行一个 M3U8 链接")
        self.batch_url_input.setMinimumHeight(100)
        self.batch_url_input.setMaximumHeight(140)
        self.batch_url_input.setVisible(False)
        compose_layout.addWidget(self.batch_url_input)

        output_label = self._create_form_label("保存位置")
        compose_layout.addWidget(output_label)

        output_row = QHBoxLayout()
        output_row.setSpacing(6)

        self.output_input = ModernLineEdit("选择保存路径")
        self.output_input.setMinimumHeight(36)
        output_row.addWidget(self.output_input, 1)

        self.browse_btn = ModernButton("浏览")
        self.browse_btn.setMinimumHeight(36)
        self.browse_btn.clicked.connect(self.browse_output_path)
        output_row.addWidget(self.browse_btn)
        compose_layout.addLayout(output_row)

        task_name_label = self._create_form_label("任务名称 · 可选")
        compose_layout.addWidget(task_name_label)

        self.task_name_input = ModernLineEdit("留空将自动从链接推断")
        self.task_name_input.setMinimumHeight(36)
        self.task_name_input.returnPressed.connect(self.add_download_task)
        compose_layout.addWidget(self.task_name_input)

        # 高级：线程 / 并发 / 请求头模板（默认折叠）
        self.advanced_toggle = QPushButton("高级  ▸")
        self.advanced_toggle.setObjectName("advanced_toggle")
        self.advanced_toggle.setCursor(Qt.PointingHandCursor)
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setChecked(False)
        self.advanced_toggle.toggled.connect(self._toggle_advanced_panel)
        compose_layout.addWidget(self.advanced_toggle)

        self.advanced_panel = QWidget()
        self.advanced_panel.setObjectName("advanced_panel")
        advanced_layout = QVBoxLayout(self.advanced_panel)
        advanced_layout.setContentsMargins(0, 0, 0, 0)
        advanced_layout.setSpacing(10)

        self.threads_label = self._create_form_label("单视频线程")
        advanced_layout.addWidget(self.threads_label)
        self.threads_spin = self._create_number_input(
            1,
            32,
            DEFAULT_CONFIG['max_workers'],
            "一个视频同时下载的分片数。",
        )
        self.threads_spin.setAccessibleName("单任务线程")
        advanced_layout.addWidget(self.threads_spin)

        self.concurrent_label = self._create_form_label("同时下载")
        advanced_layout.addWidget(self.concurrent_label)
        self.concurrent_spin = self._create_number_input(
            1,
            20,
            10,
            "队列中同时运行的下载任务数。",
        )
        self.concurrent_spin.setAccessibleName("同时任务")
        advanced_layout.addWidget(self.concurrent_spin)

        self.performance_panel = None

        template_label = self._create_form_label("请求头模板")
        advanced_layout.addWidget(template_label)
        self.template_combo = self._create_template_combo()
        advanced_layout.addWidget(self.template_combo)

        self.advanced_panel.setVisible(False)
        compose_layout.addWidget(self.advanced_panel)

        compose_layout.addStretch(1)

        compose_scroll.setWidget(compose_form)
        compose_outer.addWidget(compose_scroll, 1)

        footer = QWidget()
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(14, 8, 14, 14)
        footer_layout.setSpacing(0)
        self.add_task_btn = ModernButton("加入下载队列", primary=True)
        self.add_task_btn.setMinimumHeight(42)
        self.add_task_btn.clicked.connect(self.add_download_task)
        apply_glow(self.add_task_btn, color=UI_TOKENS['primary'], blur=26, alpha=120)
        enable_button_shine(self.add_task_btn, interval_ms=2400)
        footer_layout.addWidget(self.add_task_btn)
        compose_outer.addWidget(footer, 0)

        workspace_layout.addWidget(self.compose_card, 3)

        self.queue_section = QFrame()
        self.queue_section.setObjectName("queue_section")
        queue_layout = QVBoxLayout(self.queue_section)
        queue_layout.setContentsMargins(4, 0, 0, 0)
        queue_layout.setSpacing(0)

        self.right_tabs = QTabWidget()
        self.right_tabs.setObjectName("right_tabs")
        self.right_tabs.setDocumentMode(True)
        # macOS 会额外绘制一条被选中标签截断的 base line；只保留下划线指示态。
        self.right_tabs.tabBar().setDrawBase(False)

        # ---- Tab 1: 下载队列 ----
        queue_tab = QWidget()
        queue_tab_layout = QVBoxLayout(queue_tab)
        queue_tab_layout.setContentsMargins(2, 10, 2, 2)
        queue_tab_layout.setSpacing(10)

        # 筛选条 + 清理（去掉与 Tab 重复的「下载队列」标题）
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(4)
        self._filter_chips = {}
        for key, label in (
            ('all', '全部'),
            ('active', '下载中'),
            ('waiting', '等待'),
            ('completed', '完成'),
            ('failed', '失败'),
        ):
            chip = self._create_filter_chip(key, f"{label} 0")
            self._filter_chips[key] = chip
            stats_layout.addWidget(chip)
        self.total_tasks_label = self._filter_chips['all']
        self.active_downloads_label = self._filter_chips['active']
        self.waiting_tasks_label = self._filter_chips['waiting']
        self.completed_tasks_label = self._filter_chips['completed']
        self.failed_tasks_label = self._filter_chips['failed']
        stats_layout.addStretch()

        self.clear_all_tasks_btn = ModernButton("清理已完成", variant='ghost')
        self.clear_all_tasks_btn.setMinimumHeight(28)
        self.clear_all_tasks_btn.clicked.connect(self.clear_all_tasks)
        self.clear_all_tasks_btn.setEnabled(False)
        stats_layout.addWidget(self.clear_all_tasks_btn)
        queue_tab_layout.addLayout(stats_layout)
        self._set_queue_filter('all', refresh=False)

        self.progress_overview = self._create_progress_overview()
        queue_tab_layout.addWidget(self.progress_overview)

        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("task_scroll")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self.task_container = QWidget()
        self.task_container.setObjectName("task_container")
        self.task_container_layout = QVBoxLayout(self.task_container)
        self.task_container_layout.setContentsMargins(0, 2, 0, 2)
        self.task_container_layout.setSpacing(6)
        self.empty_state_card = self._create_empty_state_card()
        self.task_container_layout.addWidget(self.empty_state_card)
        self.task_container_layout.addStretch()

        self.scroll_area.setWidget(self.task_container)
        queue_tab_layout.addWidget(self.scroll_area, 1)

        # ---- Tab 2: 实时日志 ----
        log_tab = QWidget()
        log_tab_layout = QVBoxLayout(log_tab)
        log_tab_layout.setContentsMargins(4, 8, 4, 4)
        log_tab_layout.setSpacing(8)

        log_header = QHBoxLayout()
        self.log_panel_title = QLabel("实时日志")
        self.log_panel_title.setProperty("role", "title")
        self.log_panel_title.setFont(app_font(FONT_TITLE - 1, QFont.DemiBold))
        log_header.addWidget(self.log_panel_title)
        log_header.addStretch()
        self.clear_main_log_btn = ModernButton("清空日志")
        self.clear_main_log_btn.setMinimumHeight(30)
        self.clear_main_log_btn.clicked.connect(self.clear_main_logs)
        log_header.addWidget(self.clear_main_log_btn)
        log_tab_layout.addLayout(log_header)

        self.main_log_text = QPlainTextEdit()
        self.main_log_text.setReadOnly(True)
        self.main_log_text.setPlaceholderText("下载、搜索、过盾等过程日志会显示在这里...")
        self.main_log_text.setStyleSheet(
            log_console_stylesheet(border=UI_TOKENS['border'], radius=UI_TOKENS['radius'])
        )
        log_tab_layout.addWidget(self.main_log_text, 1)

        self.right_tabs.addTab(queue_tab, "下载队列")
        self.right_tabs.addTab(log_tab, "实时日志")
        queue_layout.addWidget(self.right_tabs)

        workspace_layout.addWidget(self.queue_section, 7)
        main_layout.addWidget(workspace, 1)

        if self._use_custom_chrome:
            grip_row = QHBoxLayout()
            grip_row.setContentsMargins(0, 0, 0, 0)
            grip_row.addStretch(1)
            self._size_grip = QSizeGrip(central_widget)
            grip_row.addWidget(self._size_grip, 0, Qt.AlignBottom | Qt.AlignRight)
            main_layout.addLayout(grip_row)

        # 右侧不铺阴影，避免「盒子套盒子」；左侧轨轻微抬升即可
        apply_drop_shadow(self.compose_card, blur=18, alpha=40, y_offset=4)

        self.statusBar().showMessage("准备就绪")
        if self._use_custom_chrome:
            self.menuBar().setVisible(False)
        else:
            self.setup_menu()
        self._apply_dashboard_accents(get_theme(0))
        if not self.download_tasks:
            QTimer.singleShot(0, self._start_empty_state_animation)

    def _toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
            if self.title_bar:
                self.title_bar.set_maximized_state(False)
        else:
            self.showMaximized()
            if self.title_bar:
                self.title_bar.set_maximized_state(True)

    def _create_header_action(self, text, icon_name, slot, primary=False):
        """顶栏可见操作：金底主按钮 / 描边次按钮（带文字，避免隐形图标）。"""
        variant = 'primary' if primary else 'outline'
        btn = ModernButton(text, primary=primary, variant=variant, icon_name=icon_name)
        btn.setToolTip(text)
        btn.setMinimumHeight(34)
        btn.setMinimumWidth(88 if not primary else 76)
        btn.clicked.connect(slot)
        btn.setProperty("icon_name", icon_name)
        btn.setProperty("header_variant", variant)
        self._tool_buttons.append(btn)
        return btn

    def _create_icon_tool_button(self, icon_name, tooltip, slot):
        """兼容旧调用：转成带文字的描边按钮。"""
        return self._create_header_action(tooltip, icon_name, slot, primary=False)

    def _create_filter_chip(self, filter_key, text):
        """队列状态筛选芯片"""
        chip = QPushButton(text)
        chip.setObjectName("filter_chip")
        chip.setCursor(Qt.PointingHandCursor)
        chip.setProperty("filter_key", filter_key)
        chip.setProperty("active", "false")
        chip.clicked.connect(lambda checked=False, k=filter_key: self._set_queue_filter(k))
        polish_widget(chip)
        return chip

    def _toggle_advanced_panel(self, checked):
        self.advanced_panel.setVisible(checked)
        self.advanced_toggle.setText("高级  ▾" if checked else "高级  ▸")

    def _set_queue_filter(self, filter_key, refresh=True):
        self._queue_filter = filter_key
        for key, chip in self._filter_chips.items():
            active = key == filter_key
            chip.setProperty("active", "true" if active else "false")
            polish_widget(chip)
        if refresh:
            self._apply_queue_filter()

    def _task_filter_bucket(self, task):
        """将任务归入筛选桶：active / waiting / completed / failed / other"""
        if not hasattr(task, 'status_label'):
            return 'waiting'
        status = task.status_label.text()
        if "完成" in status:
            return 'completed'
        if "失败" in status or "错误" in status:
            return 'failed'
        if "准备中" in status or "等待" in status or "已暂停" in status:
            return 'waiting'
        # 下载中 / 百分比 / 合并中 等
        return 'active'

    def _apply_queue_filter(self):
        for task in self.download_tasks:
            if self._queue_filter == 'all':
                task.setVisible(True)
            else:
                task.setVisible(self._task_filter_bucket(task) == self._queue_filter)

    def _create_form_label(self, text):
        """创建左侧任务表单的小标签。"""
        label = QLabel(text)
        label.setProperty("role", "form_label")
        label.setFont(app_font(FONT_CAPTION, QFont.DemiBold))
        return label

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
        """主题切换后刷新依赖当前强调色的少量动态控件。"""
        tokens = getattr(self, "current_tokens", None) or merge_theme_tokens(0)
        primary = tokens.get("primary", UI_TOKENS["primary"])
        border = tokens.get("border", UI_TOKENS["border"])
        radius = tokens.get("radius", UI_TOKENS["radius"])
        muted = tokens.get("text_muted", UI_TOKENS["text_muted"])

        if hasattr(self, "app_subtitle"):
            self.app_subtitle.setStyleSheet(f"color: {muted};")

        if hasattr(self, "main_log_text"):
            self.main_log_text.setStyleSheet(
                log_console_stylesheet(border=border, radius=radius)
            )
        if hasattr(self, "workspace") and hasattr(self.workspace, "set_tokens"):
            self.workspace.set_tokens(tokens)
        if hasattr(self, "compose_card") and hasattr(self.compose_card, "set_tokens"):
            self.compose_card.set_tokens(tokens)
        if hasattr(self, "empty_state_card") and hasattr(self.empty_state_card, "set_tokens"):
            self.empty_state_card.set_tokens(tokens)
        if hasattr(self, "empty_state_visual"):
            if hasattr(self.empty_state_visual, "set_tokens"):
                self.empty_state_visual.set_tokens(tokens)
            self.empty_state_visual.update()
        elif hasattr(self, "empty_state_icon"):
            self.empty_state_icon.clear()
            self.empty_state_icon.setStyleSheet(
                f"background: {tokens.get('primary_soft', UI_TOKENS['primary_soft'])};"
                " border-radius: 32px; border: none;"
            )
            self.empty_state_icon.setPixmap(
                qta_icon("fa5s.inbox", color=tokens.get('primary', UI_TOKENS['primary'])).pixmap(28, 28)
            )
        if getattr(self, "title_bar", None):
            self.title_bar.refresh_icons(tokens)
            self.title_bar.set_maximized_state(self.isMaximized())

        for btn in getattr(self, "_tool_buttons", []):
            icon_name = btn.property("icon_name")
            if not icon_name:
                continue
            variant = btn.property("header_variant") or btn.property("variant") or "outline"
            if variant == "primary":
                color = "#0A0E1A"
            elif variant == "danger":
                color = tokens.get("danger", UI_TOKENS["danger"])
            else:
                color = muted
            btn.setIcon(qta_icon(icon_name, color=color))

        # 左侧轨轻微抬升；右侧保持平坦；CTA 与主按钮跟随主题色发光
        if hasattr(self, "compose_card"):
            apply_drop_shadow(self.compose_card, blur=18, alpha=40, y_offset=4)
        if hasattr(self, "add_task_btn"):
            effect = apply_glow(self.add_task_btn, color=primary, blur=24, alpha=126)
            self._start_primary_glow_pulse(effect)
        if hasattr(self, "search_tool_btn"):
            apply_glow(self.search_tool_btn, color=primary, blur=18, alpha=90)

        self._active_pill_color = primary
        # 刷新筛选芯片选中态（样式由全局 QSS 驱动）
        if getattr(self, "_filter_chips", None):
            self._set_queue_filter(self._queue_filter, refresh=True)

    def set_effects_enabled(self, enabled):
        """Enable or freeze decorative motion without changing the visual theme."""
        self.effects_enabled = bool(enabled)

        for name in ("workspace", "compose_card", "empty_state_card", "empty_state_visual"):
            widget = getattr(self, name, None)
            if widget is not None and hasattr(widget, "set_motion_enabled"):
                widget.set_motion_enabled(self.effects_enabled)

        shine_buttons = [
            *getattr(self, "_tool_buttons", []),
            getattr(self, "add_task_btn", None),
            getattr(self, "empty_start_button", None),
        ]
        for button in shine_buttons:
            overlay = getattr(button, "_shine_overlay", None) if button is not None else None
            if overlay is not None:
                overlay.set_enabled(self.effects_enabled)

        pulse = getattr(self, "_primary_glow_animation", None)
        if not self.effects_enabled:
            if pulse is not None:
                pulse.stop()
            self._stop_empty_state_animation()
            return

        add_button = getattr(self, "add_task_btn", None)
        glow = add_button.graphicsEffect() if add_button is not None else None
        if glow is not None and hasattr(glow, "setBlurRadius"):
            self._start_primary_glow_pulse(glow)
        card = getattr(self, "empty_state_card", None)
        if card is not None and card.isVisible():
            self._start_empty_state_animation()

    def _start_primary_glow_pulse(self, effect):
        """Give the primary queue action a slow, visible breathing halo."""
        previous = getattr(self, "_primary_glow_animation", None)
        if previous is not None:
            previous.stop()
        if not getattr(self, "effects_enabled", True):
            effect.setBlurRadius(24.0)
            return
        animation = QPropertyAnimation(effect, b"blurRadius", self)
        animation.setDuration(2200)
        animation.setStartValue(20.0)
        animation.setKeyValueAt(0.5, 38.0)
        animation.setEndValue(20.0)
        animation.setEasingCurve(QEasingCurve.InOutSine)
        animation.setLoopCount(-1)
        animation.start()
        self._primary_glow_animation = animation

    def _create_field_label(self, text):
        """创建表单字段标签"""
        label = QLabel(text)
        label.setFont(app_font(FONT_CAPTION, QFont.DemiBold))
        label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        label.setMinimumWidth(82)
        label.setProperty("role", "form_label")
        return label

    def _create_number_input(self, minimum, maximum, value, tooltip):
        """创建统一样式的数字输入框"""
        spin_box = QSpinBox()
        spin_box.setRange(minimum, maximum)
        spin_box.setValue(value)
        spin_box.setMinimumHeight(36)
        spin_box.setMaximumHeight(36)
        spin_box.setButtonSymbols(QSpinBox.UpDownArrows)
        spin_box.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        spin_box.setToolTip(tooltip)
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
        """兼容旧 pill；筛选条改用 filter_chip，此样式仅作闪动高亮备用。"""
        color = QColor(text_color)
        background = f"rgba({color.red()}, {color.green()}, {color.blue()}, {int(round(alpha * 255))})"
        return f"""
            QPushButton#filter_chip {{
                color: {text_color};
                background: {background};
                border: 1px solid transparent;
                border-radius: 14px;
                padding: 4px 12px;
            }}
        """

    def _apply_overview_pill_style(self, label, text_color, bright=False):
        """筛选芯片短暂高亮（统计变化时）"""
        alpha = 0.28 if bright else 0.10
        if isinstance(label, QPushButton) and label.objectName() == "filter_chip":
            # 非选中芯片才闪；选中态交给 QSS active
            if label.property("active") == "true":
                polish_widget(label)
                return
            label.setStyleSheet(self._pill_stylesheet(text_color, alpha))
            return
        label.setStyleSheet(self._pill_stylesheet(text_color, alpha))

    def _flash_overview_pill(self, label):
        """统计数字变化时短暂高亮"""
        text_color = label.property('pill_color') or UI_TOKENS['primary']
        self._apply_overview_pill_style(label, text_color, bright=True)

        def _restore():
            if label is None:
                return
            label.setStyleSheet("")
            polish_widget(label)

        QTimer.singleShot(180, _restore)

    def _create_empty_state_card(self):
        """空状态：能量核心与流光边框形成队列的主视觉焦点。"""
        card = EnergyBorderCard()
        card.setObjectName("empty_state_card")

        wrapper = QVBoxLayout(card)
        wrapper.setContentsMargins(32, 56, 32, 56)
        wrapper.setSpacing(8)
        wrapper.addStretch(1)

        self.empty_state_visual = EmptyStateVisual()
        self.empty_state_visual.clicked.connect(self._focus_download_input)
        self.empty_state_icon_wrap = self.empty_state_visual
        wrapper.addWidget(self.empty_state_visual, 0, Qt.AlignHCenter)

        wrapper.addSpacing(6)

        self.empty_state_title = QLabel("还没有下载任务")
        self.empty_state_title.setAlignment(Qt.AlignCenter)
        self.empty_state_title.setFont(app_font(FONT_BODY + 2, QFont.DemiBold))
        wrapper.addWidget(self.empty_state_title)

        self.empty_state_desc = QLabel("在左侧粘贴 M3U8 链接，加入后自动排队。")
        self.empty_state_desc.setAlignment(Qt.AlignCenter)
        self.empty_state_desc.setWordWrap(True)
        self.empty_state_desc.setProperty("role", "muted")
        wrapper.addWidget(self.empty_state_desc)

        self.empty_state_hint = QLabel("线程与请求头可在「高级」中调整")
        self.empty_state_hint.setAlignment(Qt.AlignCenter)
        self.empty_state_hint.setFont(app_font(FONT_CAPTION))
        self.empty_state_hint.setProperty("role", "muted")
        wrapper.addWidget(self.empty_state_hint)

        wrapper.addSpacing(10)

        start_button = ModernButton("开始添加", variant='outline')
        start_button.setMaximumWidth(136)
        start_button.setMinimumHeight(34)
        start_button.clicked.connect(self._focus_download_input)
        enable_button_shine(start_button, interval_ms=3300)
        self.empty_start_button = start_button
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
        combo.setMinimumHeight(36)

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
                "user-agent": (
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
                    "Mobile/15E148 Safari/604.1"
                ),
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
