"""Request-header editing dialog."""

import json

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QPlainTextEdit, QVBoxLayout

from config import UI_TOKENS
from theme import DIALOG_BODY, DIALOG_CAPTION, app_font, polish_widget

class HeadersDialog(QDialog):
    """请求头配置对话框"""

    def __init__(self, parent=None, current_headers=None):
        super().__init__(parent)
        self.current_headers = current_headers or {}
        self.setup_ui()

    def setup_ui(self):
        self.setWindowTitle("请求头配置")
        self.setMinimumSize(680, 500)
        self.setFont(app_font(DIALOG_BODY))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        info_label = QLabel("请输入自定义请求头（JSON 格式或每行一个键值对）")
        info_label.setFont(app_font(DIALOG_BODY, QFont.DemiBold))
        info_label.setProperty("role", "form_label")
        layout.addWidget(info_label)

        example_text = '''示例格式：
{
    "referer": "https://example.com/",
    "origin": "https://example.com",
    "sec-ch-ua": "\\"Not;A=Brand\\";v=\\"99\\", \\"Google Chrome\\";v=\\"139\\"",
    "sec-fetch-site": "cross-site"
}

        或者每行一个：
referer: https://example.com/
origin: https://example.com'''

        example_label = QLabel(example_text)
        example_font = QFont("Menlo")
        example_font.setPixelSize(DIALOG_CAPTION)
        example_label.setFont(example_font)
        example_label.setStyleSheet(f"""
            background: {UI_TOKENS['surface_alt']};
            padding: 12px;
            border-radius: {UI_TOKENS['radius_control']}px;
            color: {UI_TOKENS['text_muted']};
            border: 1px solid {UI_TOKENS['border']};
        """)
        layout.addWidget(example_label)

        self.text_edit = QPlainTextEdit()
        editor_font = QFont("Menlo")
        editor_font.setPixelSize(DIALOG_BODY)
        self.text_edit.setFont(editor_font)
        self.text_edit.setPlainText(self._headers_to_text())
        self.text_edit.setStyleSheet(f"""
            QPlainTextEdit {{
                border: 1px solid {UI_TOKENS['border']};
                border-radius: {UI_TOKENS['radius_control']}px;
                padding: 12px;
                background: {UI_TOKENS['surface']};
                color: {UI_TOKENS['text']};
                selection-background-color: {UI_TOKENS['primary']};
                selection-color: #FFFFFF;
                font-family: "Consolas";
            }}
            QPlainTextEdit:focus {{
                border-color: {UI_TOKENS['primary']};
            }}
        """)
        layout.addWidget(self.text_edit)

        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            parent=self
        )
        button_box.setFont(app_font(DIALOG_BODY, QFont.DemiBold))
        ok_btn = button_box.button(QDialogButtonBox.Ok)
        cancel_btn = button_box.button(QDialogButtonBox.Cancel)
        if ok_btn:
            ok_btn.setText("确定")
            ok_btn.setMinimumSize(108, 42)
            ok_btn.setProperty("variant", "primary")
            polish_widget(ok_btn)
        if cancel_btn:
            cancel_btn.setText("取消")
            cancel_btn.setMinimumSize(108, 42)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _headers_to_text(self):
        """将请求头字典转换为文本"""
        if not self.current_headers:
            return ""

        import json
        return json.dumps(self.current_headers, indent=2, ensure_ascii=False)

    def get_headers(self):
        """获取用户输入的请求头"""
        text = self.text_edit.toPlainText().strip()
        if not text:
            return {}

        try:
            # 尝试解析为JSON
            import json
            return json.loads(text)
        except json.JSONDecodeError:
            # 尝试按行解析
            headers = {}
            for line in text.split('\n'):
                line = line.strip()
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip().strip('"').strip("'")
                    value = value.strip().rstrip(',').strip().strip('"').strip("'")
                    if key:
                        headers[key] = value
            return headers
