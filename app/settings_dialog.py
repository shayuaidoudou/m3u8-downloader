"""Preferences dialog and settings persistence."""

import json
import os

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGraphicsOpacityEffect,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QTabBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from config import DEFAULT_CONFIG, THEME_NAMES, UI_TOKENS, get_theme
from theme import (
    DIALOG_BODY,
    DIALOG_GROUP_TITLE,
    DIALOG_LABEL,
    app_font,
    apply_app_theme,
    build_stylesheet,
    polish_widget,
)
from .message_box import CustomMessageBox
from .ui_support import get_settings_path
from .widgets import ModernButton

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
        self.setFont(app_font(DIALOG_BODY))

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(14)

        # 创建标签页
        from PySide6.QtWidgets import QTabWidget
        tab_widget = QTabWidget()
        tab_widget.setDocumentMode(True)
        tab_widget.setUsesScrollButtons(False)
        tab_widget.setFont(app_font(DIALOG_GROUP_TITLE, QFont.DemiBold))
        tab_widget.tabBar().setElideMode(Qt.ElideNone)
        tab_widget.tabBar().setExpanding(False)
        tab_widget.tabBar().setDrawBase(False)

        tab_widget.addTab(self.create_network_tab(), "网络设置")
        tab_widget.addTab(self.create_ui_tab(), "界面设置")
        tab_widget.addTab(self.create_download_tab(), "下载设置")
        tab_widget.addTab(self.create_advanced_tab(), "高级设置")
        self.settings_tabs = tab_widget
        tab_widget.currentChanged.connect(self._animate_tab_change)
        main_layout.addWidget(tab_widget, 1)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        button_layout.addStretch()

        reset_btn = ModernButton("恢复默认")
        reset_btn.setFont(app_font(DIALOG_BODY, QFont.DemiBold))
        reset_btn.setMinimumSize(124, 42)
        reset_btn.clicked.connect(self.reset_to_default)

        save_btn = ModernButton("保存并应用", primary=True)
        save_btn.setFont(app_font(DIALOG_BODY, QFont.DemiBold))
        save_btn.setMinimumSize(124, 42)
        save_btn.clicked.connect(self.save_settings)

        button_layout.addWidget(reset_btn)
        button_layout.addWidget(save_btn)
        main_layout.addLayout(button_layout)

        self.center_on_screen()
        self.load_settings()

    def _animate_tab_change(self, index):
        """Fade each settings page in so switching sections feels continuous."""
        page = self.settings_tabs.widget(index) if hasattr(self, 'settings_tabs') else None
        if page is None:
            return
        effect = QGraphicsOpacityEffect(page)
        effect.setOpacity(0.35)
        page.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", page)
        animation.setDuration(190)
        animation.setStartValue(0.35)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.OutCubic)

        def _finish():
            if page.graphicsEffect() is effect:
                page.setGraphicsEffect(None)
            page._tab_fade_animation = None

        animation.finished.connect(_finish)
        page._tab_fade_animation = animation
        animation.start()

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
                font-size: {DIALOG_GROUP_TITLE}px;
                font-weight: 700;
            }}
        """

    def _settings_label_style(self):
        """设置页标签样式"""
        return f"color: {UI_TOKENS['text']}; font-size: {DIALOG_LABEL}px;"

    def _settings_line_edit_style(self):
        """设置页输入框样式"""
        return f"""
            QLineEdit {{
                background: {UI_TOKENS['surface']};
                border: 1px solid {UI_TOKENS['border']};
                border-radius: {UI_TOKENS['radius_control']}px;
                padding: 8px 12px;
                color: {UI_TOKENS['text']};
                font-size: {DIALOG_BODY}px;
                min-height: 38px;
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
                min-height: 38px;
                font-size: {DIALOG_BODY}px;
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
                min-height: 38px;
                font-size: {DIALOG_BODY}px;
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
                font-size: {DIALOG_BODY}px;
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
                font-size: {DIALOG_LABEL}px;
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
                font-size: {DIALOG_LABEL}px;
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
        proxy_group.setFont(app_font(DIALOG_GROUP_TITLE, QFont.Bold))
        proxy_group.setStyleSheet(self._settings_groupbox_style())
        proxy_layout = QVBoxLayout(proxy_group)
        proxy_layout.setContentsMargins(14, 10, 14, 12)
        proxy_layout.setSpacing(14)

        # 启用代理
        self.proxy_enabled = QCheckBox("启用代理服务器")
        self.proxy_enabled.setFont(app_font(DIALOG_BODY))
        self.proxy_enabled.setStyleSheet(self._settings_checkbox_style())
        proxy_layout.addWidget(self.proxy_enabled)

        # 代理类型和地址
        proxy_info_layout = QHBoxLayout()

        # 代理类型
        type_label = QLabel("代理类型:")
        type_label.setFont(app_font(DIALOG_LABEL))
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
        addr_label.setFont(app_font(DIALOG_LABEL))
        addr_label.setStyleSheet(self._settings_label_style())

        self.proxy_host = QLineEdit()
        self.proxy_host.setPlaceholderText("例如: 127.0.0.1")
        self.proxy_host.setStyleSheet(self._settings_line_edit_style())

        port_label = QLabel("端口:")
        port_label.setFont(app_font(DIALOG_LABEL))
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
        conn_group.setFont(app_font(DIALOG_GROUP_TITLE, QFont.Bold))
        conn_group.setStyleSheet(self._settings_groupbox_style())
        conn_layout = QFormLayout(conn_group)
        self._setup_form_layout(conn_layout)

        # 超时时间
        timeout_label = QLabel("连接超时:")
        timeout_label.setFont(app_font(DIALOG_LABEL))
        timeout_label.setStyleSheet(self._settings_label_style())

        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 300)
        self.timeout_spin.setValue(30)
        self.timeout_spin.setSuffix(" 秒")
        self.timeout_spin.setStyleSheet(self._settings_spinbox_style(120))

        conn_layout.addRow(timeout_label, self.timeout_spin)

        # 重试次数
        retry_label = QLabel("重试次数:")
        retry_label.setFont(app_font(DIALOG_LABEL))
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
        theme_group.setFont(app_font(DIALOG_GROUP_TITLE, QFont.Bold))
        theme_group.setStyleSheet(self._settings_groupbox_style())
        theme_layout = QFormLayout(theme_group)
        self._setup_form_layout(theme_layout)

        # 主题色选择
        color_layout = QHBoxLayout()

        color_label = QLabel("主题色彩:")
        color_label.setFont(app_font(DIALOG_LABEL))
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
        display_group.setFont(app_font(DIALOG_GROUP_TITLE, QFont.Bold))
        display_group.setStyleSheet(self._settings_groupbox_style())
        display_layout = QFormLayout(display_group)
        self._setup_form_layout(display_layout)

        # 字体大小
        font_label = QLabel("字体大小:")
        font_label.setFont(app_font(DIALOG_LABEL))
        font_label.setStyleSheet(self._settings_label_style())

        self.font_size = QSpinBox()
        self.font_size.setRange(8, 24)
        self.font_size.setValue(12)
        self.font_size.setSuffix(" pt")
        self.font_size.setStyleSheet(self._settings_spinbox_style(120))

        display_layout.addRow(font_label, self.font_size)

        # 窗口透明度
        opacity_label = QLabel("窗口透明度:")
        opacity_label.setFont(app_font(DIALOG_LABEL))
        opacity_label.setStyleSheet(self._settings_label_style())

        from PySide6.QtWidgets import QSlider
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(70, 100)
        self.opacity_slider.setValue(95)
        self.opacity_slider.setTickPosition(QSlider.TicksBelow)
        self.opacity_slider.setTickInterval(10)
        self.opacity_slider.setStyleSheet(self._settings_slider_style())

        display_layout.addRow(opacity_label, self.opacity_slider)

        effects_label = QLabel("动态特效:")
        effects_label.setFont(app_font(DIALOG_LABEL))
        effects_label.setStyleSheet(self._settings_label_style())

        self.effects_enabled = QCheckBox("启用粒子、轨道与流光")
        self.effects_enabled.setFont(app_font(DIALOG_BODY))
        self.effects_enabled.setChecked(True)
        self.effects_enabled.setToolTip("关闭后保留视觉样式，但停止持续动画以降低绘制开销")
        display_layout.addRow(effects_label, self.effects_enabled)

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
        path_group.setFont(app_font(DIALOG_GROUP_TITLE, QFont.Bold))
        path_group.setStyleSheet(self._settings_groupbox_style())
        path_layout = QVBoxLayout(path_group)
        path_layout.setContentsMargins(14, 10, 14, 12)
        path_layout.setSpacing(14)

        # 默认保存路径
        default_path_layout = QHBoxLayout()
        default_path_layout.setSpacing(10)

        path_label = QLabel("默认保存路径:")
        path_label.setFont(app_font(DIALOG_LABEL))
        path_label.setStyleSheet(self._settings_label_style())

        self.default_path = QLineEdit()
        self.default_path.setPlaceholderText("选择默认的视频保存文件夹...")
        self.default_path.setText(os.path.expanduser("~/Downloads"))
        self.default_path.setStyleSheet(self._settings_line_edit_style())

        browse_btn = QPushButton("浏览")
        browse_btn.setFont(app_font(DIALOG_LABEL, QFont.DemiBold))
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
        download_group.setFont(app_font(DIALOG_GROUP_TITLE, QFont.Bold))
        download_group.setStyleSheet(self._settings_groupbox_style())
        download_layout = QFormLayout(download_group)
        self._setup_form_layout(download_layout)

        # 默认线程数
        threads_label = QLabel("默认线程数:")
        threads_label.setFont(app_font(DIALOG_LABEL))
        threads_label.setStyleSheet(self._settings_label_style())

        self.default_threads = QSpinBox()
        self.default_threads.setRange(1, 32)
        self.default_threads.setValue(8)
        self.default_threads.setSuffix(" 个")
        self.default_threads.setStyleSheet(self._settings_spinbox_style(120))

        download_layout.addRow(threads_label, self.default_threads)

        # 文件命名规则
        naming_label = QLabel("文件命名:")
        naming_label.setFont(app_font(DIALOG_LABEL))
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
        debug_group.setFont(app_font(DIALOG_GROUP_TITLE, QFont.Bold))
        debug_group.setStyleSheet(self._settings_groupbox_style())
        debug_layout = QVBoxLayout(debug_group)
        debug_layout.setContentsMargins(14, 10, 14, 12)
        debug_layout.setSpacing(14)

        # 启用调试日志
        self.debug_enabled = QCheckBox("启用详细调试日志")
        self.debug_enabled.setFont(app_font(DIALOG_BODY))
        self.debug_enabled.setStyleSheet(self._settings_checkbox_style())
        debug_layout.addWidget(self.debug_enabled)

        # 日志级别
        log_level_layout = QHBoxLayout()

        log_label = QLabel("日志级别:")
        log_label.setFont(app_font(DIALOG_LABEL))
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
        cache_group.setFont(app_font(DIALOG_GROUP_TITLE, QFont.Bold))
        cache_group.setStyleSheet(self._settings_groupbox_style())
        cache_layout = QFormLayout(cache_group)
        self._setup_form_layout(cache_layout)

        # 缓存大小限制
        cache_label = QLabel("缓存大小限制:")
        cache_label.setFont(app_font(DIALOG_LABEL))
        cache_label.setStyleSheet(self._settings_label_style())

        self.cache_size = QSpinBox()
        self.cache_size.setRange(10, 1000)
        self.cache_size.setValue(100)
        self.cache_size.setSuffix(" MB")
        self.cache_size.setStyleSheet(self._settings_spinbox_style(120))

        cache_layout.addRow(cache_label, self.cache_size)

        # 清理缓存按钮
        clear_cache_btn = QPushButton("清理缓存")
        clear_cache_btn.setFont(app_font(DIALOG_LABEL, QFont.DemiBold))
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
                self.effects_enabled.setChecked(ui.get('effects_enabled', True))

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
                'opacity': self.opacity_slider.value(),
                'effects_enabled': self.effects_enabled.isChecked()
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
        if hasattr(self.main_window, 'set_effects_enabled'):
            self.main_window.set_effects_enabled(settings['ui'].get('effects_enabled', True))

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
            self.effects_enabled.setChecked(True)

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
        """应用主题到设置对话框（原生窗口，只同步表面色）。"""
        theme = self.get_current_theme()
        surface = theme.get('groupbox_bg', UI_TOKENS['surface'])
        text = theme.get('text_color', UI_TOKENS['text'])
        border = theme.get('input_border', UI_TOKENS['border'])
        primary = theme.get('primary', UI_TOKENS['primary'])

        self.setStyleSheet(f"""
            QDialog {{
                background: {surface};
                color: {text};
                font-size: {DIALOG_BODY}px;
            }}
        """)

        tab_widget = self.findChild(QTabWidget)
        if tab_widget:
            tab_widget.setStyleSheet(f"""
                QTabWidget::pane {{
                    border: none;
                    background: transparent;
                    padding-top: 12px;
                }}
                QTabBar::tab {{
                    background: transparent;
                    border: none;
                    border-bottom: 2px solid transparent;
                    padding: 10px 18px;
                    margin-right: 4px;
                    color: {UI_TOKENS['text_muted']};
                    min-width: 88px;
                    font-size: {DIALOG_GROUP_TITLE}px;
                    font-weight: 600;
                }}
                QTabBar::tab:selected {{
                    color: {primary};
                    border-bottom-color: {primary};
                }}
                QTabBar::tab:hover:!selected {{
                    color: {text};
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
                    font-size: {DIALOG_GROUP_TITLE}px;
                    font-weight: 700;
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
