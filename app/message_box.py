"""Reusable application message dialog."""

from PySide6.QtCore import QEasingCurve, QParallelAnimationGroup, QPoint, QPropertyAnimation, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from config import UI_TOKENS
from theme import (
    DIALOG_BODY,
    DIALOG_CAPTION,
    DIALOG_TITLE,
    app_font,
    apply_drop_shadow,
)
from .ui_support import _make_close_button
from .widgets import ModernButton

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
        self._entrance_animation = None
        self._entrance_played = False
        self.setup_ui(title, message, buttons)

    def setup_ui(self, title, message, buttons):
        """设置UI"""
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )

        self.setWindowTitle("")
        self.setMinimumSize(540, 300)
        self.resize(560, 320)
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
        main_container.setObjectName("dialog_card")
        main_container.setStyleSheet(f"""
            QWidget#dialog_card {{
                background: {UI_TOKENS['surface']};
                border: 1px solid {UI_TOKENS['border']};
                border-radius: {radius_card}px;
            }}
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.addWidget(main_container)
        apply_drop_shadow(main_container)

        container_layout = QVBoxLayout(main_container)
        container_layout.setContentsMargins(24, 22, 24, 22)
        container_layout.setSpacing(18)

        # 标题栏
        title_layout = QHBoxLayout()
        title_layout.setSpacing(10)

        badge_label = QLabel(type_labels.get(self.msg_type, "提示"))
        badge_label.setFont(app_font(DIALOG_CAPTION, QFont.DemiBold))
        badge_label.setStyleSheet(f"""
            QLabel {{
                color: {accent};
                background: {UI_TOKENS['surface_alt']};
                border: 1px solid {UI_TOKENS['border']};
                border-radius: {radius_tag}px;
                padding: 5px 10px;
            }}
        """)

        title_label = QLabel(title if title else "提示")
        title_label.setFont(app_font(DIALOG_TITLE, QFont.DemiBold))
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
            self.INFO: "i",
            self.WARNING: "!",
            self.QUESTION: "?",
            self.SUCCESS: "✓",
            self.ERROR: "×",
        }

        icon_label = QLabel(icons.get(self.msg_type, "i"))
        icon_label.setFont(app_font(28, QFont.DemiBold))
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setFixedSize(58, 58)
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
        message_label.setFont(app_font(DIALOG_BODY, QFont.Medium))
        message_label.setWordWrap(True)
        message_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        message_label.setStyleSheet(f"""
            QLabel {{
                color: {UI_TOKENS['text']};
                padding: 8px 2px;
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
            is_primary = i == len(buttons) - 1
            btn = ModernButton(button_text, primary=is_primary)
            btn.setFont(app_font(DIALOG_BODY, QFont.DemiBold))
            btn.setMinimumSize(112, 42)
            btn.clicked.connect(lambda checked=False, idx=i: self.button_clicked(idx))
            button_layout.addWidget(btn)

        container_layout.addLayout(button_layout)

    def showEvent(self, event):
        """Reveal modal dialogs with a short lift-and-fade entrance."""
        super().showEvent(event)
        if self._entrance_played:
            return
        self._entrance_played = True
        final_position = self.pos()
        self.move(final_position + QPoint(0, 12))
        self.setWindowOpacity(0.0)

        group = QParallelAnimationGroup(self)
        opacity = QPropertyAnimation(self, b"windowOpacity", group)
        opacity.setDuration(220)
        opacity.setStartValue(0.0)
        opacity.setEndValue(1.0)
        opacity.setEasingCurve(QEasingCurve.OutCubic)
        position = QPropertyAnimation(self, b"pos", group)
        position.setDuration(220)
        position.setStartValue(self.pos())
        position.setEndValue(final_position)
        position.setEasingCurve(QEasingCurve.OutCubic)
        group.start()
        self._entrance_animation = group

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
