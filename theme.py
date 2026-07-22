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
    QStyle,
    QWidget,
)

from config import UI_TOKENS, merge_theme_tokens

# --- 字体层级（像素）---
FONT_TITLE = 17
FONT_BODY = 13
FONT_CAPTION = 12

# 弹窗保持略高于辅助信息的可读性，但整体密度与主窗口一致。
DIALOG_TITLE = 17
DIALOG_GROUP_TITLE = 14
DIALOG_BODY = 13
DIALOG_LABEL = 13
DIALOG_CAPTION = 12

# --- 阴影（克制：靠边框分层，阴影只做轻微抬升）---
SHADOW_BLUR = 14
SHADOW_ALPHA = 28  # 0-255
SHADOW_Y_OFFSET = 4

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


def _hex_to_rgb(hex_color):
    value = str(hex_color).lstrip('#')
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _mix(hex_color, other, ratio):
    """按 ratio 混合两个 hex；ratio=0 偏向 hex_color，1 偏向 other。"""
    r1, g1, b1 = _hex_to_rgb(hex_color)
    r2, g2, b2 = _hex_to_rgb(other)
    return '#{:02X}{:02X}{:02X}'.format(
        int(r1 + (r2 - r1) * ratio),
        int(g1 + (g2 - g1) * ratio),
        int(b1 + (b2 - b1) * ratio),
    )


def _rgba(hex_color, alpha):
    """alpha 传 0-1 浮点，输出 Qt QSS 认可的 0-255 整数。"""
    r, g, b = _hex_to_rgb(hex_color)
    return f'rgba({r}, {g}, {b}, {int(round(alpha * 255))})'


def build_stylesheet(tokens=None):
    """根据 token 生成全局 QSS（含 hover / pressed / disabled / focus）。"""
    t = tokens or UI_TOKENS
    primary = _t(t, 'primary')
    primary_hover = _t(t, 'primary_hover')
    primary_active = _t(t, 'primary_active')
    primary_soft = _t(t, 'primary_soft')
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
    radius = _t(t, 'radius', 8)
    is_dark = bool(_t(t, 'is_dark', True))

    # 主按钮文字颜色按主色亮度自适应（金色→墨色，靛蓝→白色）
    pr, pg, pb = _hex_to_rgb(primary)
    on_primary = '#14100A' if (0.299 * pr + 0.587 * pg + 0.114 * pb) > 150 else '#FFFFFF'

    # 渐变分层：背景上浅下深，卡片表面自带一层微光
    if is_dark:
        bg_top = _mix(bg, '#FFFFFF', 0.04)
        bg_bottom = _mix(bg, '#000000', 0.45)
        surface_hi = _mix(surface, '#FFFFFF', 0.05)
        surface_lo = _mix(surface, '#000000', 0.22)
        input_bg = _mix(bg, '#000000', 0.25)
        input_focus_bg = _mix(input_bg, primary, 0.05)
    else:
        bg_top = _mix(bg, '#FFFFFF', 0.4)
        bg_bottom = _mix(bg, '#000000', 0.03)
        surface_hi = surface
        surface_lo = _mix(surface, '#000000', 0.04)
        input_bg = surface
        input_focus_bg = _mix(surface, primary, 0.04)

    primary_top = _mix(primary, '#FFFFFF', 0.22)
    primary_hover_top = _mix(primary_hover, '#FFFFFF', 0.25)
    chunk_from = _mix(primary, primary_active, 0.6)
    chunk_to = primary_hover
    accent_dim = _rgba(primary, 0.45)
    accent_faint = _rgba(primary, 0.16)

    return f"""
    /* ===== Base（不要给所有 QWidget 强制背景，否则会吞掉标题栏/图标） ===== */
    QMainWindow {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {bg_top}, stop:0.35 {bg}, stop:1 {bg_bottom});
        color: {text};
        font-size: {FONT_BODY}px;
    }}
    QDialog {{
        background-color: {bg};
        color: {text};
        font-size: {DIALOG_BODY}px;
    }}
    QDialog QPushButton {{
        font-size: {DIALOG_BODY}px;
        min-height: 38px;
    }}
    QDialog QLineEdit,
    QDialog QTextEdit,
    QDialog QPlainTextEdit,
    QDialog QComboBox,
    QDialog QSpinBox {{
        font-size: {DIALOG_BODY}px;
    }}
    QWidget#main_shell,
    QWidget#main_surface,
    QWidget#workspace {{
        background: transparent;
        color: {text};
    }}
    QWidget#main_shell {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {bg_top}, stop:0.35 {bg}, stop:1 {bg_bottom});
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
        font-weight: 700;
    }}
    QLabel[role="subtitle"] {{
        color: {text_muted};
        font-size: {FONT_CAPTION}px;
    }}

    /* ===== Title bar ===== */
    QFrame#title_bar {{
        background: {surface_lo};
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

    /* ===== Cards / sections — 卡片自带渐变微光，顶栏透明 ===== */
    QFrame#compose_card {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {surface_hi}, stop:0.12 {surface}, stop:1 {surface_lo});
        border: 1px solid {border};
        border-radius: {radius}px;
    }}
    QFrame#queue_section {{
        background: transparent;
        border: none;
        border-radius: 0;
    }}
    QFrame#dialog_card {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {surface_hi}, stop:1 {surface_lo});
        border: 1px solid {border_strong};
        border-radius: {radius}px;
    }}
    QFrame#top_bar {{
        background: transparent;
        border: none;
        border-bottom: 1px solid {border};
        border-radius: 0;
    }}
    QFrame#performance_panel {{
        background: {surface_alt};
        border: 1px solid {border};
        border-radius: {_t(t, 'radius_control', 8)}px;
    }}

    /* ===== Buttons（variant 属性） ===== */
    QPushButton {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {_mix(surface_alt, '#FFFFFF', 0.05) if is_dark else surface_alt},
            stop:1 {surface_alt});
        color: {text};
        border: 1px solid {border};
        border-radius: {_t(t, 'radius_control', 8)}px;
        padding: 7px 12px;
        min-height: 34px;
        font-size: {FONT_BODY}px;
        font-weight: 600;
    }}
    QPushButton:hover {{
        background: {surface_hover};
        border-color: {border_strong};
        color: {text};
    }}
    QPushButton:pressed {{
        background: {surface};
        border-color: {primary};
    }}
    QPushButton:disabled {{
        background: {surface};
        color: {text_subtle};
        border-color: {border};
    }}
    QPushButton[variant="primary"] {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {primary_top}, stop:1 {primary});
        color: {on_primary};
        border: 1px solid {_mix(primary, '#FFFFFF', 0.3)};
        font-weight: 700;
    }}
    QPushButton[variant="primary"]:hover {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {primary_hover_top}, stop:1 {primary_hover});
        border-color: {primary_hover_top};
        color: {on_primary};
    }}
    QPushButton[variant="primary"]:pressed {{
        background: {primary_active};
        border-color: {primary_active};
        color: {on_primary};
    }}
    QPushButton[variant="primary"]:disabled {{
        background: {surface_alt};
        color: {text_subtle};
        border-color: {border};
    }}
    QPushButton[variant="outline"] {{
        background: transparent;
        color: {text};
        border: 1px solid {border_strong};
    }}
    QPushButton[variant="outline"]:hover {{
        background: {accent_faint};
        border-color: {accent_dim};
        color: {primary};
    }}
    QPushButton[variant="outline"]:pressed {{
        background: {surface_hover};
        border-color: {primary};
    }}
    QPushButton[variant="outline"]:disabled {{
        color: {text_subtle};
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

    /* ===== Icon toolbar / filter chips ===== */
    QPushButton#icon_tool_btn {{
        background: transparent;
        border: 1px solid transparent;
        border-radius: {radius}px;
        color: {text_muted};
        padding: 0;
        min-width: 36px;
        max-width: 36px;
        min-height: 36px;
        max-height: 36px;
    }}
    QPushButton#icon_tool_btn:hover {{
        background: {surface_alt};
        border-color: {border};
        color: {primary};
    }}
    QPushButton#icon_tool_btn:pressed {{
        background: {surface_hover};
        border-color: {primary};
    }}
    QPushButton#filter_chip {{
        background: transparent;
        border: 1px solid transparent;
        border-radius: 14px;
        color: {text_muted};
        padding: 4px 12px;
        min-height: 28px;
        max-height: 28px;
        font-size: {FONT_CAPTION}px;
        font-weight: 500;
    }}
    QPushButton#filter_chip:hover {{
        border-color: {border_strong};
        color: {text};
        background: {surface_alt};
    }}
    QPushButton#filter_chip[active="true"] {{
        background: {accent_faint};
        border-color: {accent_dim};
        color: {primary};
        font-weight: 700;
    }}
    QPushButton#advanced_toggle {{
        background: transparent;
        border: none;
        color: {text_muted};
        text-align: left;
        padding: 4px 0;
        min-height: 28px;
        font-size: {FONT_CAPTION}px;
        font-weight: 600;
    }}
    QPushButton#advanced_toggle:hover {{
        color: {primary};
        background: transparent;
        border: none;
    }}
    QPushButton#task_action_btn {{
        background: transparent;
        border: 1px solid {border};
        border-radius: {radius}px;
        color: {text_muted};
        padding: 0;
        min-width: 30px;
        max-width: 30px;
        min-height: 30px;
        max-height: 30px;
    }}
    QPushButton#task_action_btn:hover {{
        background: {surface_alt};
        border-color: {primary};
        color: {primary};
    }}
    QPushButton#task_action_btn[variant="danger"]:hover {{
        border-color: {danger};
        color: {danger};
    }}
    QPushButton#task_action_btn:disabled {{
        background: transparent;
        color: {text_subtle};
        border-color: {border};
    }}
    QWidget#advanced_panel {{
        background: transparent;
    }}

    /* ===== Inputs ===== */
    QLineEdit, QTextEdit, QPlainTextEdit, QComboBox {{
        background: {input_bg};
        border: 1px solid {border};
        border-radius: {_t(t, 'radius_control', 8)}px;
        padding: 8px 12px;
        color: {text};
        selection-background-color: {primary};
        selection-color: {on_primary};
        min-height: 34px;
        font-size: {FONT_BODY}px;
    }}
    QSpinBox {{
        background: {input_bg};
        border: 1px solid {border};
        border-radius: {_t(t, 'radius_control', 8)}px;
        padding: 6px 10px 6px 12px;
        color: {text};
        selection-background-color: {primary};
        selection-color: {on_primary};
        min-height: 34px;
        max-height: 36px;
        font-size: {FONT_BODY}px;
    }}
    QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover,
    QComboBox:hover, QSpinBox:hover {{
        border-color: {border_strong};
    }}
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
    QComboBox:focus, QSpinBox:focus {{
        border-color: {primary};
        background: {input_focus_bg};
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
        border-radius: {_t(t, 'radius_progress', 3)}px;
        background: {_mix(surface_alt, '#000000', 0.25) if is_dark else surface_alt};
        text-align: center;
        color: transparent;
        min-height: 5px;
        max-height: 6px;
    }}
    QProgressBar::chunk {{
        border-radius: {_t(t, 'radius_progress', 3)}px;
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {chunk_from}, stop:1 {chunk_to});
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
        padding: 9px 18px;
        margin-right: 6px;
        font-size: {FONT_BODY}px;
        font-weight: 600;
    }}
    QTabBar::tab:selected {{
        color: {primary};
        border-bottom: 2px solid {primary};
        font-weight: 700;
    }}
    QTabBar::tab:hover:!selected {{
        color: {text};
        border-bottom: 2px solid {border_strong};
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
        background: transparent;
        color: {text_subtle};
        border-top: 1px solid {border};
        padding: 6px 12px;
        font-size: {FONT_CAPTION}px;
    }}
    QStatusBar::item {{
        border: none;
    }}
    QToolTip {{
        background: {surface_alt};
        color: {text};
        border: 1px solid {accent_dim};
        border-radius: 6px;
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
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {primary_top}, stop:1 {primary});
        border-color: {primary};
    }}

    /* ===== Task scroll — 去掉外框，让任务卡自己呼吸 ===== */
    QScrollArea#task_scroll {{
        border: none;
        border-radius: 0;
        background: transparent;
    }}
    QWidget#task_container {{
        background: transparent;
    }}

    /* ===== Empty state ===== */
    QFrame#empty_state_card {{
        background: qradialgradient(
            cx:0.5, cy:0.38, radius:0.78, fx:0.5, fy:0.38,
            stop:0 {primary_soft}, stop:0.34 {surface}, stop:1 {surface}
        );
        border: 1px solid {border};
        border-radius: {radius}px;
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


def apply_glow(widget, color=None, blur=22, alpha=110):
    """给主 CTA / 强调元素加同色辉光（区别于普通投影）。"""
    if widget is None:
        return None
    base = QColor(color or UI_TOKENS['primary'])
    base.setAlpha(alpha)
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, 2)
    effect.setColor(base)
    widget.setGraphicsEffect(effect)
    return effect


_STANDARD_ICON_FALLBACKS = {
    "fa5s.play": QStyle.SP_MediaPlay,
    "fa5s.play-circle": QStyle.SP_MediaPlay,
    "fa5s.pause": QStyle.SP_MediaPause,
    "fa5s.trash": QStyle.SP_TrashIcon,
    "fa5s.folder-open": QStyle.SP_DirOpenIcon,
    "fa5s.search": QStyle.SP_FileDialogContentsView,
    "fa5s.code": QStyle.SP_FileDialogDetailedView,
    "fa5s.cog": QStyle.SP_FileDialogInfoView,
    "fa5s.inbox": QStyle.SP_DriveHDIcon,
    "fa5s.ellipsis-v": QStyle.SP_TitleBarMenuButton,
    "fa5s.times": QStyle.SP_TitleBarCloseButton,
    "fa5s.window-minimize": QStyle.SP_TitleBarMinButton,
    "fa5s.window-maximize": QStyle.SP_TitleBarMaxButton,
    "fa5s.window-restore": QStyle.SP_TitleBarNormalButton,
}


def _standard_icon(name):
    """Return a Qt-native icon when the optional icon font is unavailable."""
    app = QApplication.instance()
    standard_pixmap = _STANDARD_ICON_FALLBACKS.get(name)
    if app is None or standard_pixmap is None:
        from PySide6.QtGui import QIcon
        return QIcon()
    return app.style().standardIcon(standard_pixmap)


def _painted_fallback_icon(name, color):
    """Draw core application icons in one consistent stroke style."""
    from PySide6.QtCore import QPointF, QRectF
    from PySide6.QtGui import QBrush, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

    if name not in {
        "fa5s.play", "fa5s.play-circle", "fa5s.pause", "fa5s.trash",
        "fa5s.search", "fa5s.code", "fa5s.folder-open", "fa5s.cog", "fa5s.inbox",
    }:
        return QIcon()

    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    paint_color = QColor(color or UI_TOKENS['text_muted'])
    pen = QPen(paint_color, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)

    if name in ("fa5s.play", "fa5s.play-circle"):
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(paint_color))
        painter.drawPolygon(QPolygonF([
            QPointF(8, 5), QPointF(19, 12), QPointF(8, 19),
        ]))
    elif name == "fa5s.pause":
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(paint_color))
        painter.drawRoundedRect(QRectF(6, 5, 4, 14), 1, 1)
        painter.drawRoundedRect(QRectF(14, 5, 4, 14), 1, 1)
    elif name == "fa5s.trash":
        painter.drawRoundedRect(QRectF(7, 7, 10, 12), 1, 1)
        painter.drawLine(QPointF(5, 6), QPointF(19, 6))
        painter.drawLine(QPointF(9, 4), QPointF(15, 4))
        painter.drawLine(QPointF(10, 10), QPointF(10, 16))
        painter.drawLine(QPointF(14, 10), QPointF(14, 16))
    elif name == "fa5s.search":
        painter.drawEllipse(QRectF(4.5, 4.5, 11, 11))
        painter.drawLine(QPointF(14.5, 14.5), QPointF(20, 20))
    elif name == "fa5s.code":
        painter.drawPolyline(QPolygonF([
            QPointF(9, 6), QPointF(4, 12), QPointF(9, 18),
        ]))
        painter.drawPolyline(QPolygonF([
            QPointF(15, 6), QPointF(20, 12), QPointF(15, 18),
        ]))
    elif name == "fa5s.folder-open":
        path = QPainterPath(QPointF(3, 8))
        path.lineTo(3, 18)
        path.lineTo(18, 18)
        path.lineTo(21, 10)
        path.lineTo(10, 10)
        path.lineTo(8, 7)
        path.lineTo(3, 7)
        path.closeSubpath()
        painter.drawPath(path)
    elif name == "fa5s.cog":
        painter.drawEllipse(QRectF(6.5, 6.5, 11, 11))
        painter.drawEllipse(QRectF(9.5, 9.5, 5, 5))
        for start, end in (
            ((12, 3), (12, 6)), ((12, 18), (12, 21)),
            ((3, 12), (6, 12)), ((18, 12), (21, 12)),
            ((5.5, 5.5), (7.6, 7.6)), ((16.4, 16.4), (18.5, 18.5)),
            ((18.5, 5.5), (16.4, 7.6)), ((7.6, 16.4), (5.5, 18.5)),
        ):
            painter.drawLine(QPointF(*start), QPointF(*end))
    elif name == "fa5s.inbox":
        painter.drawRoundedRect(QRectF(4, 5, 16, 14), 2, 2)
        painter.drawPolyline(QPolygonF([
            QPointF(4, 14), QPointF(8.5, 14), QPointF(10, 16),
            QPointF(14, 16), QPointF(15.5, 14), QPointF(20, 14),
        ]))

    painter.end()
    return QIcon(pixmap)


def _icon_has_visible_pixels(icon):
    """Reject non-null icon objects whose font glyph rendered transparent."""
    if icon.isNull():
        return False
    image = icon.pixmap(16, 16).toImage()
    return any(
        image.pixelColor(x, y).alpha() > 0
        for y in range(image.height())
        for x in range(image.width())
    )


def qta_icon(name, color=None, scale_factor=0.9):
    """Load a QtAwesome icon, falling back to Qt's bundled icon set."""
    from PySide6.QtGui import QIcon
    color = color or UI_TOKENS['text_muted']
    try:
        import qtawesome as qta
        icon = qta.icon(name, color=color, scale_factor=scale_factor)
        if _icon_has_visible_pixels(icon):
            return icon
    except Exception:
        pass
    fallback = _painted_fallback_icon(name, color)
    if not fallback.isNull():
        return fallback
    fallback = _standard_icon(name)
    return fallback if not fallback.isNull() else QIcon()


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
