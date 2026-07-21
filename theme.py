#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一主题与窗口铬层：stylesheet、字体、阴影、标题栏。

可调参数（改这里即可换肤）：
  FONT_TITLE / FONT_BODY / FONT_CAPTION  — 字号层级（px）
  SHADOW_BLUR / SHADOW_ALPHA             — 卡片阴影
  UI_TOKENS / merge_theme_tokens         — 色板与圆角（见 config.py）
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QWidget,
)

from config import UI_TOKENS, merge_theme_tokens

# --- 字体层级（像素）---
FONT_TITLE = 18
FONT_BODY = 14
FONT_CAPTION = 12

# --- 阴影 ---
SHADOW_BLUR = 20
SHADOW_ALPHA = 42  # 0-255
SHADOW_Y_OFFSET = 6

FONT_FAMILIES = [
    "PingFang SC",
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "Noto Sans SC",
    "Source Han Sans SC",
    "Segoe UI",
    "Inter",
    "Helvetica Neue",
    "Arial",
]


def resolve_app_font(size=FONT_BODY, weight=QFont.Normal):
    """统一字族 + 像素字号。"""
    font = QFont()
    font.setFamilies(FONT_FAMILIES)
    font.setPixelSize(size)
    font.setWeight(weight)
    font.setHintingPreference(QFont.PreferNoHinting)
    return font


def app_font(size, weight=QFont.Normal):
    """兼容旧调用：传入的 size 按像素处理。"""
    return resolve_app_font(size, weight)


def _t(tokens, key, default=None):
    if tokens and key in tokens:
        return tokens[key]
    return UI_TOKENS.get(key, default)


def build_stylesheet(tokens=None):
    """根据 token 生成全局 QSS（含 hover / pressed / disabled / focus）。"""
    t = tokens or UI_TOKENS
    primary = _t(t, 'primary')
    primary_hover = _t(t, 'primary_hover')
    primary_active = _t(t, 'primary_active')
    bg = _t(t, 'bg')
    surface = _t(t, 'surface')
    surface_alt = _t(t, 'surface_alt')
    surface_hover = _t(t, 'surface_hover')
    text = _t(t, 'text')
    text_muted = _t(t, 'text_muted')
    text_subtle = _t(t, 'text_subtle')
    border = _t(t, 'border')
    border_strong = _t(t, 'border_strong')
    border_focus = _t(t, 'border_focus')
    danger = _t(t, 'danger')
    radius = _t(t, 'radius', 10)

    return f"""
    /* ===== Base（不要给所有 QWidget 强制背景，否则会吞掉标题栏/图标） ===== */
    QMainWindow {{
        background-color: {bg};
        color: {text};
        font-size: {FONT_BODY}px;
    }}
    QDialog {{
        background-color: {bg};
        color: {text};
        font-size: {FONT_BODY}px;
    }}
    QWidget#main_shell,
    QWidget#main_surface,
    QWidget#workspace {{
        background-color: {bg};
        color: {text};
    }}
    QLabel {{
        background: transparent;
        color: {text};
        border: none;
    }}
    QLabel[role="form_label"] {{
        color: {text_muted};
        font-size: {FONT_CAPTION}px;
        font-weight: 600;
    }}
    QLabel[role="muted"] {{
        color: {text_muted};
        font-size: {FONT_CAPTION}px;
    }}
    QLabel[role="title"] {{
        color: {text};
        font-size: {FONT_TITLE}px;
        font-weight: 600;
    }}
    QLabel[role="subtitle"] {{
        color: {text_muted};
        font-size: {FONT_CAPTION}px;
    }}

    /* ===== Title bar ===== */
    QFrame#title_bar {{
        background: {surface};
        border: none;
        border-bottom: 1px solid {border};
    }}
    QLabel#title_bar_brand {{
        color: {text};
        font-size: {FONT_BODY}px;
        font-weight: 600;
        background: transparent;
    }}
    QPushButton#title_tool_btn,
    QPushButton#title_win_btn {{
        background: transparent;
        border: none;
        border-radius: {radius}px;
        color: {text_muted};
        padding: 6px;
        min-width: 32px;
        min-height: 32px;
    }}
    QPushButton#title_tool_btn:hover,
    QPushButton#title_win_btn:hover {{
        background: {surface_alt};
        color: {text};
    }}
    QPushButton#title_tool_btn:pressed,
    QPushButton#title_win_btn:pressed {{
        background: {surface_hover};
    }}
    QPushButton#title_close_btn {{
        background: transparent;
        border: none;
        border-radius: {radius}px;
        color: {text_muted};
        padding: 0;
        min-width: 34px;
        min-height: 34px;
        font-size: 18px;
        font-weight: 400;
    }}
    QPushButton#title_close_btn:hover {{
        background: {danger};
        color: #FFFFFF;
    }}
    QPushButton#title_close_btn:pressed {{
        background: #B91C1C;
        color: #FFFFFF;
    }}

    /* ===== Cards / sections ===== */
    QWidget#main_surface {{
        background: {bg};
    }}
    QFrame#compose_card,
    QFrame#queue_section,
    QFrame#dialog_card {{
        background: {surface};
        border: 1px solid {border};
        border-radius: {radius}px;
    }}
    QFrame#top_bar {{
        background: transparent;
        border: none;
    }}
    QFrame#performance_panel {{
        background: {surface_alt};
        border: 1px solid {border};
        border-radius: {radius}px;
    }}

    /* ===== Buttons（variant 属性） ===== */
    QPushButton {{
        background: {surface};
        color: {text};
        border: 1px solid {border};
        border-radius: {radius}px;
        padding: 8px 14px;
        min-height: 36px;
        font-size: {FONT_BODY}px;
        font-weight: 600;
    }}
    QPushButton:hover {{
        background: {surface_alt};
        border-color: {border_strong};
        color: {primary};
    }}
    QPushButton:pressed {{
        background: {surface_hover};
        border-color: {primary};
    }}
    QPushButton:disabled {{
        background: {surface_alt};
        color: {text_muted};
        border-color: {border};
    }}
    QPushButton[variant="primary"] {{
        background: {primary};
        color: #FFFFFF;
        border: 1px solid {primary};
    }}
    QPushButton[variant="primary"]:hover {{
        background: {primary_hover};
        border-color: {primary_hover};
        color: #FFFFFF;
    }}
    QPushButton[variant="primary"]:pressed {{
        background: {primary_active};
        border-color: {primary_active};
        color: #FFFFFF;
    }}
    QPushButton[variant="primary"]:disabled {{
        background: {surface_alt};
        color: {text_muted};
        border-color: {border};
    }}
    QPushButton[variant="danger"] {{
        background: {surface};
        color: {danger};
        border: 1px solid {border};
    }}
    QPushButton[variant="danger"]:hover {{
        background: {surface_alt};
        border-color: {danger};
        color: {danger};
    }}
    QPushButton[variant="danger"]:pressed {{
        background: {surface_hover};
    }}
    QPushButton[variant="danger"]:disabled {{
        background: {surface_alt};
        color: {text_muted};
        border-color: {border};
    }}
    QPushButton[variant="ghost"] {{
        background: transparent;
        border: none;
        color: {text_muted};
        padding: 6px 10px;
    }}
    QPushButton[variant="ghost"]:hover {{
        background: {surface_alt};
        color: {text};
    }}

    /* ===== Inputs ===== */
    QLineEdit, QTextEdit, QPlainTextEdit, QComboBox {{
        background: {surface};
        border: 1px solid {border};
        border-radius: {radius}px;
        padding: 8px 12px;
        color: {text};
        selection-background-color: {primary};
        selection-color: #FFFFFF;
        min-height: 36px;
        font-size: {FONT_BODY}px;
    }}
    QSpinBox {{
        background: {surface};
        border: 1px solid {border};
        border-radius: {radius}px;
        padding: 6px 10px 6px 12px;
        color: {text};
        selection-background-color: {primary};
        selection-color: #FFFFFF;
        min-height: 40px;
        max-height: 40px;
        font-size: {FONT_BODY}px;
    }}
    QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover,
    QComboBox:hover, QSpinBox:hover {{
        border-color: {border_focus};
    }}
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
    QComboBox:focus, QSpinBox:focus {{
        border-color: {primary};
    }}
    QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled,
    QComboBox:disabled, QSpinBox:disabled {{
        background: {surface_alt};
        color: {text_muted};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 28px;
    }}
    QComboBox::down-arrow {{
        image: none;
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-top: 5px solid {primary};
        width: 0;
        height: 0;
        margin-right: 10px;
    }}
    QComboBox QAbstractItemView {{
        background: {surface};
        border: 1px solid {border};
        border-radius: {radius}px;
        selection-background-color: {surface_alt};
        selection-color: {primary};
        padding: 4px;
        outline: none;
    }}
    QSpinBox::up-button, QSpinBox::down-button {{
        subcontrol-origin: border;
        width: 22px;
        border: none;
        background: {surface_alt};
    }}
    QSpinBox::up-button {{
        subcontrol-position: top right;
        margin: 1px 1px 0 0;
        border-top-right-radius: {radius}px;
    }}
    QSpinBox::down-button {{
        subcontrol-position: bottom right;
        margin: 0 1px 1px 0;
        border-bottom-right-radius: {radius}px;
    }}
    QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
        background: {surface_hover};
    }}
    QSpinBox::up-arrow {{
        image: none;
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-bottom: 5px solid {text_muted};
        width: 0;
        height: 0;
    }}
    QSpinBox::down-arrow {{
        image: none;
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-top: 5px solid {text_muted};
        width: 0;
        height: 0;
    }}

    /* ===== Progress ===== */
    QProgressBar {{
        border: none;
        border-radius: {radius}px;
        background: {surface_alt};
        text-align: center;
        color: transparent;
        min-height: 6px;
        max-height: 8px;
    }}
    QProgressBar::chunk {{
        border-radius: {radius}px;
        background: {primary};
    }}

    /* ===== Tabs ===== */
    QTabWidget::pane {{
        border: none;
        background: transparent;
        top: -1px;
    }}
    QTabBar::tab {{
        background: transparent;
        color: {text_muted};
        border: none;
        border-bottom: 2px solid transparent;
        padding: 8px 16px;
        margin-right: 4px;
        font-size: {FONT_BODY}px;
    }}
    QTabBar::tab:selected {{
        color: {primary};
        border-bottom: 2px solid {primary};
        font-weight: 600;
    }}
    QTabBar::tab:hover:!selected {{
        color: {text};
        background: {surface_alt};
        border-radius: {radius}px {radius}px 0 0;
    }}

    /* ===== Menu / Status ===== */
    QMenuBar {{
        background: {surface};
        color: {text};
        border-bottom: 1px solid {border};
        padding: 4px 8px;
        font-size: {FONT_BODY}px;
    }}
    QMenuBar::item {{
        background: transparent;
        padding: 6px 12px;
        border-radius: {radius}px;
        margin: 0 2px;
    }}
    QMenuBar::item:selected {{
        background: {surface_alt};
        color: {primary};
    }}
    QMenu {{
        background: {surface};
        color: {text};
        border: 1px solid {border};
        border-radius: {radius}px;
        padding: 6px;
    }}
    QMenu::item {{
        padding: 8px 16px;
        border-radius: {radius}px;
        min-width: 140px;
    }}
    QMenu::item:selected {{
        background: {surface_alt};
        color: {primary};
    }}
    QMenu::separator {{
        height: 1px;
        background: {border};
        margin: 4px 8px;
    }}
    QStatusBar {{
        background: {surface};
        color: {text_muted};
        border-top: 1px solid {border};
        padding: 6px 12px;
        font-size: {FONT_CAPTION}px;
    }}
    QStatusBar::item {{
        border: none;
    }}
    QToolTip {{
        background: {text};
        color: #FFFFFF;
        border: none;
        border-radius: {radius}px;
        padding: 6px 10px;
        font-size: {FONT_CAPTION}px;
    }}

    /* ===== Scrollbar ===== */
    QScrollBar:vertical {{
        border: none;
        background: transparent;
        width: 10px;
        margin: 4px 2px 4px 0;
    }}
    QScrollBar::handle:vertical {{
        background: {border_strong};
        border-radius: 5px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {text_subtle};
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
        background: {border_strong};
        border-radius: 5px;
        min-width: 30px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {text_subtle};
    }}
    QScrollBar::add-line:horizontal,
    QScrollBar::sub-line:horizontal,
    QScrollBar::add-page:horizontal,
    QScrollBar::sub-page:horizontal {{
        background: none;
        border: none;
        width: 0;
    }}

    /* ===== GroupBox / CheckBox ===== */
    QGroupBox {{
        background: {surface};
        border: 1px solid {border};
        border-radius: {radius}px;
        margin-top: 14px;
        padding-top: 16px;
        font-weight: 600;
        color: {text};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 6px;
        color: {text};
    }}
    QCheckBox {{
        color: {text};
        spacing: 8px;
    }}
    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border-radius: 4px;
        border: 1px solid {border_strong};
        background: {surface};
    }}
    QCheckBox::indicator:hover {{
        border-color: {primary};
    }}
    QCheckBox::indicator:checked {{
        background: {primary};
        border-color: {primary};
    }}

    /* ===== Task scroll ===== */
    QScrollArea#task_scroll {{
        border: 1px solid {border};
        border-radius: {radius}px;
        background: {surface_alt};
    }}
    QWidget#task_container {{
        background: transparent;
    }}
    """


def apply_app_theme(theme_index=0):
    """合并 token 并应用到 QApplication。返回合并后的 tokens。"""
    tokens = merge_theme_tokens(theme_index)
    app = QApplication.instance()
    if app is not None:
        app.setStyleSheet(build_stylesheet(tokens))
    return tokens


def apply_drop_shadow(widget, blur=SHADOW_BLUR, alpha=SHADOW_ALPHA, y_offset=SHADOW_Y_OFFSET):
    """给卡片加轻微阴影。"""
    if widget is None:
        return None
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, y_offset)
    effect.setColor(QColor(0, 0, 0, alpha))
    widget.setGraphicsEffect(effect)
    return effect


def qta_icon(name, color=None, scale_factor=0.9):
    """安全加载 qtawesome 图标；失败时返回空 QIcon。"""
    from PySide6.QtGui import QIcon
    try:
        import qtawesome as qta
        color = color or UI_TOKENS['text_muted']
        return qta.icon(name, color=color, scale_factor=scale_factor)
    except Exception:
        return QIcon()


def polish_widget(widget):
    """属性变更后刷新样式。"""
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


class TitleBar(QFrame):
    """无边框窗口自定义标题栏：拖动 + 工具按钮 + 窗口控制。"""

    minimize_requested = Signal()
    maximize_requested = Signal()
    close_requested = Signal()

    def __init__(self, parent=None, title="M3U8 下载器"):
        super().__init__(parent)
        self.setObjectName("title_bar")
        self.setFixedHeight(48)
        self._drag_pos = None
        self._host = parent

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 8, 0)
        layout.setSpacing(4)

        self.brand = QLabel(title)
        self.brand.setObjectName("title_bar_brand")
        self.brand.setFont(resolve_app_font(FONT_BODY, QFont.DemiBold))
        layout.addWidget(self.brand)
        layout.addSpacing(8)

        self.tools_host = QWidget()
        self.tools_layout = QHBoxLayout(self.tools_host)
        self.tools_layout.setContentsMargins(0, 0, 0, 0)
        self.tools_layout.setSpacing(2)
        layout.addWidget(self.tools_host)
        layout.addStretch(1)

        self.more_btn = self._make_icon_btn("fa5s.ellipsis-v", "更多", "title_tool_btn")
        layout.addWidget(self.more_btn)

        self.min_btn = self._make_icon_btn("fa5s.window-minimize", "最小化", "title_win_btn")
        self.min_btn.clicked.connect(self.minimize_requested.emit)
        layout.addWidget(self.min_btn)

        self.max_btn = self._make_icon_btn("fa5s.window-maximize", "最大化", "title_win_btn")
        self.max_btn.clicked.connect(self.maximize_requested.emit)
        layout.addWidget(self.max_btn)

        self.close_btn = self._make_icon_btn("fa5s.times", "关闭", "title_close_btn")
        self.close_btn.clicked.connect(self.close_requested.emit)
        layout.addWidget(self.close_btn)

        self._more_menu = QMenu(self)
        self.more_btn.setMenu(self._more_menu)

    def _make_icon_btn(self, icon_name, tooltip, object_name):
        btn = QPushButton()
        btn.setObjectName(object_name)
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedSize(34, 34)
        btn.setIcon(qta_icon(icon_name, color=_t(UI_TOKENS, 'text_muted')))
        btn.setIconSize(btn.size() * 0.45)
        return btn

    def add_tool_button(self, icon_name, tooltip, slot):
        btn = self._make_icon_btn(icon_name, tooltip, "title_tool_btn")
        btn.clicked.connect(slot)
        self.tools_layout.addWidget(btn)
        return btn

    def set_menu_actions(self, actions):
        """actions: list of (text, callable) or None for separator."""
        self._more_menu.clear()
        for item in actions:
            if item is None:
                self._more_menu.addSeparator()
                continue
            text, callback = item
            act = self._more_menu.addAction(text)
            act.triggered.connect(callback)

    def refresh_icons(self, tokens):
        muted = _t(tokens, 'text_muted')
        mapping = [
            (self.more_btn, "fa5s.ellipsis-v"),
            (self.min_btn, "fa5s.window-minimize"),
            (self.max_btn, "fa5s.window-maximize"),
            (self.close_btn, "fa5s.times"),
        ]
        for btn, name in mapping:
            btn.setIcon(qta_icon(name, color=muted))
        for i in range(self.tools_layout.count()):
            w = self.tools_layout.itemAt(i).widget()
            if isinstance(w, QPushButton) and w.toolTip():
                # keep existing icon name via property if set
                icon_name = w.property("icon_name")
                if icon_name:
                    w.setIcon(qta_icon(icon_name, color=muted))

    def set_maximized_state(self, maximized):
        icon = "fa5s.window-restore" if maximized else "fa5s.window-maximize"
        self.max_btn.setIcon(qta_icon(icon, color=_t(UI_TOKENS, 'text_muted')))
        self.max_btn.setToolTip("还原" if maximized else "最大化")

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        host = self.window()
        if (
            self._drag_pos is not None
            and event.buttons() & Qt.LeftButton
            and host is not None
            and not host.isMaximized()
        ):
            delta = event.globalPosition().toPoint() - self._drag_pos
            self._drag_pos = event.globalPosition().toPoint()
            host.move(host.pos() + delta)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.maximize_requested.emit()
        super().mouseDoubleClickEvent(event)


class DialogChrome(QFrame):
    """弹窗顶部拖动条 + 标题 + 关闭。"""

    def __init__(self, title, on_close, parent=None):
        super().__init__(parent)
        self.setObjectName("title_bar")
        self.setFixedHeight(48)
        self._drag_pos = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 8, 0)
        layout.setSpacing(8)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("title_bar_brand")
        self.title_label.setFont(resolve_app_font(FONT_TITLE - 2, QFont.DemiBold))
        layout.addWidget(self.title_label)
        layout.addStretch(1)

        close_btn = QPushButton("×")
        close_btn.setObjectName("title_close_btn")
        close_btn.setFixedSize(34, 34)
        close_btn.setFont(resolve_app_font(18))
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setFlat(True)
        close_btn.clicked.connect(on_close)
        layout.addWidget(close_btn)
        self.close_btn = close_btn

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        host = self.window()
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton and host:
            delta = event.globalPosition().toPoint() - self._drag_pos
            self._drag_pos = event.globalPosition().toPoint()
            host.move(host.pos() + delta)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_pos = None
        super().mouseReleaseEvent(event)
