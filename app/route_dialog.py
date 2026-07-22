"""Signals and route-selection dialog shared by search workflows."""

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QDialog, QHBoxLayout, QHeaderView, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout

from config import UI_TOKENS
from theme import DIALOG_BODY, DIALOG_LABEL, DIALOG_TITLE, app_font
from .widgets import ModernButton

class SearchSignals(QObject):
    """搜索信号类"""
    search_completed = Signal(list, str)
    search_error = Signal(str)
    extraction_completed = Signal(dict)
    show_route_dialog = Signal(dict, str, list)  # (routes, title, result_container)
    log_message = Signal(str, str)  # message, thread_name


class RouteSelectionDialog(QDialog):
    """线路选择对话框"""

    def __init__(self, routes_data, video_title, parent=None):
        """
        初始化线路选择对话框
        :param routes_data: 线路数据 {线路名: {"total": 页面条目数, "episodes": [(集名, URL), ...]}}
        :param video_title: 视频标题
        :param parent: 父窗口
        """
        super().__init__(parent)
        self.routes_data = routes_data
        self.video_title = video_title
        self.selected_route = None
        self.setup_ui()

    def setup_ui(self):
        """设置UI"""
        self.setWindowTitle(f"选择播放线路 - {self.video_title}")
        self.setMinimumSize(720, 480)
        self.setModal(True)
        self.setFont(app_font(DIALOG_BODY))

        self.setStyleSheet(f"""
            QDialog {{
                background: {UI_TOKENS['bg']};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        title_label = QLabel(self.video_title)
        title_label.setFont(app_font(DIALOG_TITLE, QFont.DemiBold))
        title_label.setStyleSheet(f"color: {UI_TOKENS['text']}; padding: 4px 0; background: transparent; border: none;")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        info_label = QLabel(self._dialog_description())
        info_label.setFont(app_font(DIALOG_LABEL))
        info_label.setStyleSheet(f"color: {UI_TOKENS['text_muted']}; padding: 2px 0; background: transparent; border: none;")
        layout.addWidget(info_label)

        self.route_list = QTableWidget()
        self.route_list.setColumnCount(3)
        self.route_list.setHorizontalHeaderLabels(["线路名称", "可用内容", "覆盖情况"])
        self.route_list.horizontalHeader().setStretchLastSection(True)
        self.route_list.setSelectionBehavior(QTableWidget.SelectRows)
        self.route_list.setSelectionMode(QTableWidget.SingleSelection)
        self.route_list.setEditTriggers(QTableWidget.NoEditTriggers)
        self.route_list.setAlternatingRowColors(True)
        self.route_list.setFont(app_font(DIALOG_BODY))
        self.route_list.setStyleSheet(f"""
            QTableWidget {{
                border: 1px solid {UI_TOKENS['border']};
                border-radius: {UI_TOKENS['radius_control']}px;
                background: {UI_TOKENS['surface']};
                gridline-color: {UI_TOKENS['border']};
            }}
            QTableWidget::item {{
                padding: 8px;
                color: {UI_TOKENS['text']};
            }}
            QTableWidget::item:selected {{
                background: {UI_TOKENS['primary']};
                color: #FFFFFF;
            }}
            QHeaderView::section {{
                background: {UI_TOKENS['surface_alt']};
                padding: 8px;
                border: none;
                border-bottom: 1px solid {UI_TOKENS['border']};
                color: {UI_TOKENS['text']};
            }}
        """)

        self.route_list.setRowCount(len(self.routes_data))
        for idx, (route_name, route_info) in enumerate(self.routes_data.items()):
            name_item = QTableWidgetItem(route_name)
            name_item.setFont(app_font(DIALOG_BODY, QFont.DemiBold))
            self.route_list.setItem(idx, 0, name_item)

            content_item = QTableWidgetItem(self._content_summary(route_info))
            content_item.setTextAlignment(Qt.AlignCenter)
            self.route_list.setItem(idx, 1, content_item)

            status, status_color = self._coverage_summary(route_info)

            status_item = QTableWidgetItem(status)
            status_item.setTextAlignment(Qt.AlignCenter)
            status_item.setForeground(QColor(status_color))
            self.route_list.setItem(idx, 2, status_item)

        self.route_list.setColumnWidth(0, 250)
        self.route_list.setColumnWidth(1, 100)

        self.route_list.itemDoubleClicked.connect(self.accept)
        layout.addWidget(self.route_list)

        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = ModernButton("取消")
        cancel_btn.setFont(app_font(DIALOG_BODY, QFont.DemiBold))
        cancel_btn.setMinimumSize(108, 42)
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        ok_btn = ModernButton("确定提取", primary=True)
        ok_btn.setFont(app_font(DIALOG_BODY, QFont.DemiBold))
        ok_btn.setMinimumSize(124, 42)
        ok_btn.clicked.connect(self.accept)
        button_layout.addWidget(ok_btn)

        layout.addLayout(button_layout)

        if self.route_list.rowCount() > 0:
            self.route_list.selectRow(0)

    def _dialog_description(self):
        """在线路数据含分类信息时，明确区分正片和特别内容。"""
        first_route = next(iter(self.routes_data.values()), {})
        if "regular_total" not in first_route:
            return "请选择一个播放线路，将提取该线路的所有剧集："

        regular_total = first_route.get("regular_total", 0)
        special_total = first_route.get("special_total", 0)
        summary = f"页面共 {regular_total} 集正片"
        if special_total:
            summary += f" + {special_total} 个特别内容"
        return f"{summary}；请选择要提取的播放线路："

    @staticmethod
    def _content_summary(route_info):
        if "regular_count" not in route_info:
            return f"{len(route_info.get('episodes') or [])} 集"

        parts = []
        regular_count = route_info.get("regular_count", 0)
        special_count = route_info.get("special_count", 0)
        if regular_count:
            parts.append(f"{regular_count} 集")
        if special_count:
            parts.append(f"{special_count} 个特别内容")
        return " + ".join(parts) or "无内容"

    @staticmethod
    def _coverage_summary(route_info):
        episodes_count = len(route_info.get("episodes") or [])
        total = route_info.get("total", episodes_count)
        if "regular_count" not in route_info:
            if episodes_count == total:
                return "完整", UI_TOKENS['success']
            if episodes_count:
                return f"覆盖 {episodes_count}/{total}", UI_TOKENS['warning']
            return "无剧集", UI_TOKENS['danger']

        regular_count = route_info.get("regular_count", 0)
        regular_total = route_info.get("regular_total", 0)
        special_count = route_info.get("special_count", 0)
        special_total = route_info.get("special_total", 0)
        if regular_count == regular_total:
            if special_count == special_total:
                return "全部内容完整", UI_TOKENS['success']
            return "正片完整", UI_TOKENS['success']
        if regular_count:
            return f"正片 {regular_count}/{regular_total}", UI_TOKENS['warning']
        if special_count:
            return "仅特别内容", UI_TOKENS['warning']
        return "无可用内容", UI_TOKENS['danger']

    def accept(self):
        """确认选择"""
        selected_row = self.route_list.currentRow()
        print(f"线路选择对话框 - 当前选中行: {selected_row}")

        if selected_row >= 0:
            route_keys = list(self.routes_data.keys())
            print(f"   可用线路: {route_keys}")
            self.selected_route = route_keys[selected_row]
            print(f"确认选择线路: {self.selected_route}")
        else:
            print("未选择任何线路")
            self.selected_route = None

        super().accept()

    def get_selected_route(self):
        """获取选中的线路"""
        print(f"返回选中的线路: {self.selected_route}")
        return self.selected_route
