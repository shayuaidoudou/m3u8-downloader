"""Shared, dependency-light helpers used by the GUI modules.

Keeping path, font and log helpers here prevents each window/dialog module from
reimplementing the same bootstrap concerns and gives the rest of the UI a
small, stable import surface.
"""

import os
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit, QPushButton

from theme import app_font
from utils import LOG_LEVEL_COLORS, build_spring_log_segments


def get_settings_path() -> str:
    """Return the settings path for both source and frozen applications."""
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), "settings.json")
    return str(Path(__file__).resolve().parent.parent / "settings.json")


def app_base_dir() -> Path:
    """Return the source directory or PyInstaller's extracted resource dir."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def asset_path(*parts: str) -> Path:
    """Build an absolute path inside the application asset directory."""
    return app_base_dir().joinpath("assets", *parts)


def resolve_app_icon() -> Optional[str]:
    """Find the first usable application icon in the packaged asset set."""
    for name in ("app_icon.png", "app.icns", "shayu.jpg", "favicon.ico"):
        path = asset_path(name)
        if path.exists():
            return str(path)
    return None


def append_spring_boot_log(widget: Optional[QPlainTextEdit], message: str, thread_name: str = "main") -> None:
    """Append a colourised log line to a plain-text Qt log widget."""
    if widget is None:
        return

    role_colors = {
        "time": "#8B949E",
        "meta": "#8B949E",
        "message": "#E6EDF3",
    }
    cursor = widget.textCursor()
    cursor.movePosition(QTextCursor.End)
    level = "INFO"
    for text, role in build_spring_log_segments(message, thread_name=thread_name):
        fmt = QTextCharFormat()
        if role == "level":
            level = text.strip() or level
            fmt.setForeground(QColor(LOG_LEVEL_COLORS.get(level, "#98C379")))
            fmt.setFontWeight(QFont.DemiBold)
        else:
            fmt.setForeground(QColor(role_colors.get(role, "#E6EDF3")))
        cursor.insertText(text, fmt)

    widget.setTextCursor(cursor)
    widget.verticalScrollBar().setValue(widget.verticalScrollBar().maximum())


def make_close_button(on_click):
    """Create the shared text close button used by custom dialogs."""
    button = QPushButton("×")
    button.setObjectName("title_close_btn")
    button.setFixedSize(34, 34)
    button.setFont(app_font(18, QFont.Normal))
    button.setCursor(Qt.PointingHandCursor)
    button.setFlat(True)
    button.clicked.connect(on_click)
    return button


# Backwards-compatible private alias for code migrated from the original entrypoint.
_make_close_button = make_close_button
