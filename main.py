#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M3U8 downloader GUI entrypoint.

The implementation is split by responsibility under :mod:`app`; this module
keeps the historical import path (``from main import MainWindow``) and owns
only application bootstrap code.
"""

import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

from app.dialogs import CustomMessageBox, HeadersDialog, SettingsDialog
from app.main_window import MainWindow
from app.route_dialog import RouteSelectionDialog, SearchSignals
from app.search_dialog import M3u8SearchDialog
from app.ui_support import (
    _make_close_button,
    app_base_dir,
    append_spring_boot_log,
    asset_path,
    get_settings_path,
    resolve_app_icon,
)
from app.widgets import (
    DownloadTaskWidget,
    DownloadWorker,
    ModernButton,
    ModernLineEdit,
    ModernProgressBar,
)
from theme import FONT_BODY, apply_app_theme, resolve_app_font


def main() -> int:
    """Create the Qt application and start the main window."""
    app = QApplication(sys.argv)
    app.setApplicationName("M3U8 下载器")
    app.setOrganizationName("M3U8Downloader")
    app.setStyle("Fusion")
    app.setFont(resolve_app_font(FONT_BODY))
    apply_app_theme(0)

    icon_path = resolve_app_icon()
    if icon_path:
        app.setWindowIcon(QIcon(icon_path))

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "CustomMessageBox",
    "DownloadTaskWidget",
    "DownloadWorker",
    "HeadersDialog",
    "MainWindow",
    "ModernButton",
    "ModernLineEdit",
    "ModernProgressBar",
    "M3u8SearchDialog",
    "RouteSelectionDialog",
    "SearchSignals",
    "SettingsDialog",
    "app_base_dir",
    "append_spring_boot_log",
    "asset_path",
    "get_settings_path",
    "main",
    "resolve_app_icon",
]
