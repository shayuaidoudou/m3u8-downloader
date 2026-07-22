"""Download queue, task actions and progress state for the main window."""

import json
import os

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QGraphicsOpacityEffect

from config import DEFAULT_CONFIG, UI_TOKENS, get_theme, get_theme_name
from theme import apply_app_theme, polish_widget
from utils import (
    ensure_extension,
    extract_title_from_url,
    get_available_filename,
    is_valid_m3u8_url,
    sanitize_filename,
    validate_output_path,
)
from .message_box import CustomMessageBox
from .settings_dialog import SettingsDialog
from .ui_support import get_settings_path
from .widgets import DownloadTaskWidget


class MainWindowQueueMixin:
    """Own task creation, scheduling, progress aggregation and animations."""

    def add_download_task(self):
        """添加下载任务"""
        is_batch_mode = "批量" in self.mode_combo.currentText()

        if is_batch_mode:
            self._add_batch_tasks()
        else:
            self._add_single_task()

    def _add_single_task(self):
        """添加单个下载任务"""
        url = self.url_input.text().strip()
        output_path = self.output_input.text().strip()
        task_name = self.task_name_input.text().strip()

        # 验证URL
        if not url:
            CustomMessageBox.show_warning(self, "提示", "请输入 M3U8 链接。")
            return

        if not is_valid_m3u8_url(url):
            CustomMessageBox.show_warning(self, "提示", "请输入有效的 M3U8 链接。")
            return

        # 验证输出路径
        if not output_path:
            CustomMessageBox.show_warning(self, "提示", "请选择保存路径。")
            return

        # 确保文件扩展名
        output_path = ensure_extension(output_path)

        # 验证输出路径
        is_valid, error_msg = validate_output_path(output_path)
        if not is_valid:
            CustomMessageBox.show_warning(self, "提示", f"输出路径不可用：{error_msg}")
            return

        # 避免文件名冲突
        output_path = get_available_filename(output_path)

        # 生成任务名称
        if not task_name:
            task_name = extract_title_from_url(url)
            if not task_name or task_name == "未知视频":
                task_name = f"下载任务_{len(self.download_tasks) + 1}"

        # 创建并添加任务
        self._create_task_widget(task_name, url, output_path)

        # 清空输入框
        self.url_input.clear()
        self.task_name_input.clear()

        # 显示任务信息
        headers_info = f" (包含 {len(self.custom_headers)} 个自定义请求头)" if self.custom_headers else ""
        self.statusBar().showMessage(f"已添加任务: {task_name}{headers_info}")

    def _add_batch_tasks(self):
        """添加批量下载任务"""
        urls_text = self.batch_url_input.toPlainText().strip()
        output_folder = self.output_input.text().strip()
        base_task_name = self.task_name_input.text().strip()

        # 验证输入
        if not urls_text:
            CustomMessageBox.show_warning(self, "提示", "请输入 M3U8 链接。")
            return

        if not output_folder:
            CustomMessageBox.show_warning(self, "提示", "请选择保存文件夹。")
            return

        if not os.path.exists(output_folder):
            CustomMessageBox.show_warning(self, "提示", "保存文件夹不存在。")
            return

        # 解析URL列表
        urls = []
        for line in urls_text.split('\n'):
            url = line.strip()
            if url and is_valid_m3u8_url(url):
                urls.append(url)

        if not urls:
            CustomMessageBox.show_warning(self, "提示", "没有找到有效的 M3U8 链接。")
            return

        # 确认批量添加
        reply = CustomMessageBox.show_question(
            self,
            "批量添加",
            f"检测到 {len(urls)} 个有效链接，是否加入下载队列？\n\n任务会按照当前并发设置自动启动。"
        )

        if reply != QDialog.Accepted:
            return

        # 批量创建任务
        added_count = 0
        for i, url in enumerate(urls):
            try:
                # 生成任务名称
                if base_task_name:
                    task_name = f"{base_task_name}_{i+1:03d}"
                else:
                    extracted_name = extract_title_from_url(url)
                    if extracted_name and extracted_name != "未知视频":
                        task_name = f"{extracted_name}_{i+1:03d}"
                    else:
                        task_name = f"批量任务_{len(self.download_tasks) + i + 1:03d}"

                # 生成输出文件路径
                safe_name = "".join(c for c in task_name if c.isalnum() or c in (' ', '-', '_', '.')).rstrip()
                output_path = os.path.join(output_folder, f"{safe_name}.mp4")
                output_path = get_available_filename(output_path)

                # 创建任务
                self._create_task_widget(task_name, url, output_path)
                added_count += 1

            except Exception as e:
                print(f"创建任务失败 {i+1}: {e}")
                continue

        # 清空输入框
        self.batch_url_input.clear()
        self.task_name_input.clear()

        # 显示结果
        headers_info = f" (包含 {len(self.custom_headers)} 个自定义请求头)" if self.custom_headers else ""
        self.statusBar().showMessage(f"批量添加完成: {added_count}/{len(urls)} 个任务{headers_info}")

        # 自动开始下载队列中的任务
        self._process_download_queue()

    def _create_task_widget(self, task_name, url, output_path):
        """创建任务组件"""
        # 创建任务组件（包含自定义请求头）
        task_widget = DownloadTaskWidget(task_name, url, output_path, self.custom_headers.copy())

        # 连接任务完成信号
        task_widget.download_finished.connect(self._on_task_finished)

        # 插入到任务容器的最后一个位置（stretch之前）
        self.task_container_layout.insertWidget(
            self.task_container_layout.count() - 1,
            task_widget
        )

        self.download_tasks.append(task_widget)

        self._play_task_entry_animation(task_widget)

        # 更新进度概览
        self._update_progress_overview()

        return task_widget

    def _play_task_entry_animation(self, task_widget):
        """Fade a new task into the queue without moving the surrounding layout."""
        effect = QGraphicsOpacityEffect(task_widget)
        effect.setOpacity(0.0)
        task_widget.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", task_widget)
        animation.setDuration(220)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.OutCubic)

        def _finish():
            if task_widget.graphicsEffect() is effect:
                task_widget.setGraphicsEffect(None)
            task_widget._entry_animation = None

        animation.finished.connect(_finish)
        task_widget._entry_animation = animation
        QTimer.singleShot(0, animation.start)

    def clear_all_tasks(self):
        """清理已完成的下载任务"""
        if not self.download_tasks:
            CustomMessageBox.show_info(
                self,
                "提示",
                "当前还没有下载任务。"
            )
            return

        # 筛选出已完成的任务
        completed_tasks = []
        for task in self.download_tasks:
            # 通过状态文本判断任务是否完成
            if hasattr(task, 'status_label'):
                status_text = task.status_label.text()
                # 判断是否包含完成、失败或错误的关键词
                if any(keyword in status_text for keyword in ["完成", "失败", "错误", "成功"]):
                    # 如果有worker，确保它不在运行中
                    if hasattr(task, 'worker') and task.worker:
                        if not task.worker.isRunning():
                            completed_tasks.append(task)
                    else:
                        # 没有worker或worker为None，直接添加
                        completed_tasks.append(task)

        if not completed_tasks:
            CustomMessageBox.show_info(
                self,
                "提示",
                "当前没有可清理的任务。\n\n只有下载完成或失败的任务才会被清理。"
            )
            return

        # 确认删除
        reply = CustomMessageBox.show_question(
            self,
            "确认清理",
            f"发现 {len(completed_tasks)} 个已完成任务。\n\n确认清理这些任务吗？\n进行中的任务不会被删除。"
        )

        if reply == QDialog.Accepted:
            # 删除已完成的任务
            for task in completed_tasks:
                # 从任务列表中移除
                if task in self.download_tasks:
                    self.download_tasks.remove(task)

                # 从布局中移除
                task.setParent(None)
                task.deleteLater()

            # 更新进度概览
            self._update_progress_overview()

            # 更新状态栏
            self.statusBar().showMessage(f"已清理 {len(completed_tasks)} 个已完成任务")

            # 显示成功提示
            CustomMessageBox.show_success(
                self,
                "清理完成",
                f"已清理 {len(completed_tasks)} 个已完成任务。\n进行中的任务会继续保留。"
            )

    def open_download_folder(self):
        """打开下载文件夹"""
        if self.download_tasks:
            last_output = self.download_tasks[-1].output_path
            folder_path = os.path.dirname(last_output)
            if os.path.exists(folder_path):
                QDesktopServices.openUrl(QUrl.fromLocalFile(folder_path))
            else:
                CustomMessageBox.show_info(self, "提示", "下载文件夹不存在。")
        else:
            CustomMessageBox.show_info(self, "提示", "还没有下载任务，请先添加一个任务。")

    def show_settings(self):
        """显示设置对话框"""
        settings_dialog = SettingsDialog(self)
        settings_dialog.exec()

    def show_about(self):
        """显示关于对话框"""
        about_message = """M3U8 下载器 v1.0

基于 PySide6 的桌面端 HLS / M3U8 下载工具，界面采用简约工作台风格，将下载、任务队列、请求头配置与片源搜索放在同一处。

主要能力：
• 多线程下载与任务队列
• AES 加密流解密与 FFmpeg 合并
• 自定义请求头与模板
• 实时日志与进度概览
• 可选片源搜索与提取

开源地址：
github.com/shayuaidoudou/m3u8-downloader"""

        CustomMessageBox.show_info(
            self,
            "关于 M3U8 下载器",
            about_message
        )

    def apply_theme(self, theme_index):
        """一次性重建全局 stylesheet，并刷新工作台动态强调色。"""
        theme = get_theme(theme_index)
        self.current_theme_data = theme.copy()
        tokens = apply_app_theme(theme_index)
        self.current_tokens = tokens
        # 同步模块级 UI_TOKENS 引用的可变字段，供任务卡片等即时读取
        for key, value in tokens.items():
            if key in UI_TOKENS or key in ("is_dark",):
                UI_TOKENS[key] = value
        self._apply_dashboard_accents(theme)
        print(f"已应用主题: {theme_index} - {get_theme_name(theme_index)}")

    def _theme_hex_to_rgb(self, hex_color):

        """将十六进制颜色转换为RGB（用于主题）"""
        hex_color = hex_color.lstrip('#')
        return ', '.join(str(int(hex_color[i:i+2], 16)) for i in (0, 2, 4))

    def load_user_settings(self):
        """启动时加载用户设置"""
        settings_file = get_settings_path()

        try:
            if os.path.exists(settings_file):
                with open(settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)

                # 应用UI设置
                ui = settings.get('ui', {})
                opacity = ui.get('opacity', 95) / 100.0
                self.setWindowOpacity(opacity)

                # 应用主题设置
                theme_index = ui.get('theme_color', 0)
                self.apply_theme(theme_index)
                self.set_effects_enabled(ui.get('effects_enabled', True))

                # 应用下载设置
                download = settings.get('download', {})

                # 设置默认线程数
                default_threads = download.get('default_threads', DEFAULT_CONFIG['max_workers'])
                if hasattr(self, 'threads_spin'):
                    self.threads_spin.setValue(default_threads)

                # 设置默认保存路径
                default_path = download.get('default_path', '')
                if default_path and os.path.exists(default_path) and hasattr(self, 'output_input'):
                    self.output_input.setText(default_path)

                print(f"已加载用户设置: 线程数={default_threads}, 路径={default_path}, 主题={theme_index}")

        except Exception as e:
            print(f"️ 加载用户设置失败: {e}")
            # 继续使用默认设置

    def _on_task_finished(self, success):
        """任务完成回调"""
        self.active_downloads -= 1
        print(f"[DEBUG] 任务完成，当前活跃下载数: {self.active_downloads}")

        # 处理队列中的下一个任务
        self._process_download_queue()

    def _process_download_queue(self):
        """处理下载队列"""
        max_concurrent = self.concurrent_spin.value()

        # 找到等待中的任务并开始下载
        for task in self.download_tasks:
            if self.active_downloads >= max_concurrent:
                break

            # 检查任务是否在等待状态
            if hasattr(task, 'status_label') and "准备中" in task.status_label.text():
                try:
                    self.active_downloads += 1
                    task.start_download()
                    print(f"[DEBUG] 自动启动任务: {task.task_name}, 当前活跃下载数: {self.active_downloads}")
                except Exception as e:
                    self.active_downloads -= 1
                    print(f"[ERROR] 启动任务失败: {e}")

        # 更新状态栏和进度概览
        waiting_count = sum(1 for task in self.download_tasks
                          if hasattr(task, 'status_label') and "准备中" in task.status_label.text())
        if waiting_count > 0:
            self.statusBar().showMessage(f"活跃下载: {self.active_downloads}/{max_concurrent}, 等待中: {waiting_count}")
        else:
            self.statusBar().showMessage(f"活跃下载: {self.active_downloads}/{max_concurrent}")

        # 更新进度概览
        self._update_progress_overview()

    def _update_progress_overview(self):
        """更新进度概览"""
        if not self.download_tasks:
            self.progress_overview.setVisible(False)
            if hasattr(self, 'empty_state_card'):
                self.empty_state_card.setVisible(True)
                self._start_empty_state_animation()
            if hasattr(self, 'clear_all_tasks_btn'):
                self.clear_all_tasks_btn.setEnabled(False)
            self._update_active_pulse_state(0)
            self._stat_counts = {
                'total': 0, 'active': 0, 'waiting': 0, 'completed': 0, 'failed': 0,
            }
            return

        self.progress_overview.setVisible(True)
        if hasattr(self, 'empty_state_card'):
            self.empty_state_card.setVisible(False)
            self._stop_empty_state_animation()

        # 统计各种状态的任务数
        total_tasks = len(self.download_tasks)
        active_count = self.active_downloads
        waiting_count = 0
        completed_count = 0
        failed_count = 0

        for task in self.download_tasks:
            if hasattr(task, 'status_label'):
                status_text = task.status_label.text()
                if "准备中" in status_text or "等待中" in status_text:
                    waiting_count += 1
                elif "完成" in status_text:
                    completed_count += 1
                elif "失败" in status_text or "错误" in status_text:
                    failed_count += 1

        new_counts = {
            'total': total_tasks,
            'active': active_count,
            'waiting': waiting_count,
            'completed': completed_count,
            'failed': failed_count,
        }
        chip_labels = {
            'all': ('全部', self.total_tasks_label),
            'active': ('下载中', self.active_downloads_label),
            'waiting': ('等待', self.waiting_tasks_label),
            'completed': ('完成', self.completed_tasks_label),
            'failed': ('失败', self.failed_tasks_label),
        }
        count_map = {
            'all': total_tasks,
            'active': active_count,
            'waiting': waiting_count,
            'completed': completed_count,
            'failed': failed_count,
        }
        for key, (prefix, chip) in chip_labels.items():
            value = count_map[key]
            if value != self._stat_counts.get(
                {'all': 'total'}.get(key, key), -1
            ) and key != 'all':
                self._flash_overview_pill(chip)
            elif key == 'all' and value != self._stat_counts.get('total', -1):
                self._flash_overview_pill(chip)
            chip.setText(f"{prefix} {value}")
            chip.setProperty('pill_color', UI_TOKENS['primary'])
        self._stat_counts = new_counts

        # 更新标签
        self.progress_summary_label.setText(
            f"并发上限 {self.concurrent_spin.value()} · 已完成 {completed_count + failed_count}/{total_tasks}"
        )
        self.clear_all_tasks_btn.setEnabled((completed_count + failed_count) > 0)
        self._update_active_pulse_state(active_count)
        self._apply_queue_filter()

        # 计算整体进度
        if total_tasks > 0:
            progress = (completed_count + failed_count) / total_tasks * 100
            self.overall_progress.setValue(int(progress))
        else:
            self.overall_progress.setValue(0)

    def _update_active_pulse_state(self, active_count):
        """活跃下载 > 0 时脉冲高亮「下载中」筛选芯片"""
        if active_count > 0:
            if not self._active_pulse_timer.isActive():
                self._active_pulse_bright = False
                self._active_pulse_timer.start()
        else:
            self._active_pulse_timer.stop()
            self._active_pulse_bright = False
            if hasattr(self, 'active_downloads_label'):
                polish_widget(self.active_downloads_label)

    def _toggle_active_pulse(self):
        """切换活跃下载芯片的背景亮度"""
        if not hasattr(self, 'active_downloads_label'):
            return
        if self.active_downloads_label.property("active") == "true":
            return
        self._active_pulse_bright = not self._active_pulse_bright
        color = getattr(self, '_active_pill_color', UI_TOKENS['primary'])
        self._apply_overview_pill_style(
            self.active_downloads_label,
            color,
            bright=self._active_pulse_bright,
        )

    def _start_empty_state_animation(self):
        """启动空状态能量核心与卡片边框动画。"""
        target = getattr(self, 'empty_state_icon_wrap', None) or getattr(self, 'empty_state_icon', None)
        if self._empty_anim_running or target is None:
            return
        animated = False
        for widget in (target, getattr(self, 'empty_state_card', None)):
            if widget is not None and hasattr(widget, 'start_animation'):
                widget.start_animation()
                animated = True
        if animated:
            self._empty_anim_running = True
            return
        effect = QGraphicsOpacityEffect(target)
        effect.setOpacity(1.0)
        target.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(1400)
        anim.setStartValue(0.55)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.InOutSine)
        anim.setLoopCount(-1)
        anim.start()
        self._empty_anim = anim
        self._empty_anim_running = True

    def _stop_empty_state_animation(self):
        """停止空状态的全部持续动画，避免隐藏后继续重绘。"""
        if not self._empty_anim_running:
            return
        if self._empty_anim is not None:
            self._empty_anim.stop()
            self._empty_anim = None
        target = getattr(self, 'empty_state_icon_wrap', None) or getattr(self, 'empty_state_icon', None)
        for widget in (target, getattr(self, 'empty_state_card', None)):
            if widget is None:
                continue
            if hasattr(widget, 'stop_animation'):
                widget.stop_animation()
            elif widget is target:
                widget.setGraphicsEffect(None)
        self._empty_anim_running = False

    def showEvent(self, event):
        """窗口首次显示时淡入主内容区"""
        super().showEvent(event)
        if not self._entrance_done:
            self._entrance_done = True
            self._play_entrance_animation()

    def _play_entrance_animation(self):
        """主内容区 0→1 淡入（窗口透明度仍由设置控制）"""
        surface = getattr(self, '_main_surface', None) or self.centralWidget()
        if surface is None:
            return
        effect = QGraphicsOpacityEffect(surface)
        effect.setOpacity(0.0)
        surface.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(250)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.finished.connect(lambda: surface.setGraphicsEffect(None))
        anim.start()
        self._entrance_anim = anim
