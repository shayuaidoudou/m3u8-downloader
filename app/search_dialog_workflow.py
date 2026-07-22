"""Search execution and M3U8 extraction workflows."""

import threading
from threading import Thread

from PySide6.QtWidgets import QApplication, QDialog, QInputDialog

from search import IYF_CHANNEL, NNYY_CHANNEL, channel_requires_refresh, search_with_engine
from .message_box import CustomMessageBox
from .route_dialog import RouteSelectionDialog


class SearchDialogWorkflowMixin:
    """Own asynchronous search, route selection and extraction state changes."""

    def start_search(self):
        """开始搜索"""
        keyword = self.keyword_input.text().strip()
        print(f" 开始搜索，关键词: '{keyword}'")

        if not keyword:
            CustomMessageBox.show_error(self, "错误", "请输入搜索关键词!")
            return

        # 获取搜索引擎类型
        engine_type = self.engine_combo.currentText()

        if channel_requires_refresh(engine_type):
            # 爱壹帆：只刷新 Cookie，保留已缓存密钥，避免每次搜索都重建引擎卡顿。
            if (
                engine_type == IYF_CHANNEL
                and self.search_engine is not None
                and hasattr(self.search_engine, "_apply_cookie")
            ):
                self.search_engine._apply_cookie(self.ncat_cookie_input.text().strip())
            else:
                self.init_search_engine()
        elif not self.search_engine:
            print("搜索引擎未初始化，正在初始化...")
            self.init_search_engine()

        if not self.search_engine:
            CustomMessageBox.show_error(self, "错误", "搜索引擎未初始化!")
            return

        # 禁用搜索按钮
        self.search_btn.setEnabled(False)
        self.update_status(f" 正在搜索: {keyword}...")

        # 获取搜索类型（仅爱瓜影视需要）
        choice = self.type_combo.currentIndex()  # 0=电影, 1=电视剧等

        if engine_type == "爱瓜影视":
            print(f"搜索类型: {choice} ({'电影' if choice == 0 else '电视剧/动漫/综艺'})")

        # 在线程中执行搜索
        search_thread = threading.Thread(target=self._do_search, args=(keyword, choice))
        search_thread.daemon = True
        search_thread.start()
        print("搜索线程已启动")

    def _do_search(self, keyword, choice):
        """执行搜索（在线程中）"""
        try:
            engine_type = self.engine_combo.currentText()
            results = search_with_engine(engine_type, self.search_engine, keyword, choice)
            self.signals.search_completed.emit(results, keyword)

        except Exception as e:
            print(f"搜索异常: {e}")
            import traceback
            traceback.print_exc()
            # 使用信号通知UI更新错误
            self.signals.search_error.emit(str(e))

    def _on_search_complete(self, results, keyword):
        """搜索完成回调"""
        print(f"UI更新回调被调用: 结果数量={len(results)}, 关键词={keyword}")
        self.search_results = results
        self.search_btn.setEnabled(True)

        if results:
            engine_type = self.engine_combo.currentText()
            self.update_status(f"找到 {len(results)} 个结果")
            print(f"正在设置结果文本...")

            # 显示结果
            result_text = f" 搜索关键词: {keyword}\n"
            result_text += f" 搜索引擎: {engine_type}\n"
            result_text += f" 共找到 {len(results)} 个结果:\n\n"

            if engine_type == "爱瓜影视":
                # 爱瓜影视返回 [url, url, ...]
                for i, url in enumerate(results):
                    result_text += f"{i}: {url}\n"
            elif engine_type in {"NCat22影视", NNYY_CHANNEL}:
                # HTML 详情页渠道统一返回 [{dict}, {dict}, ...]
                for i, item in enumerate(results):
                    if isinstance(item, dict):
                        result_text += f"{'='*60}\n"
                        result_text += f"[{i}] {item.get('title', '未知')}\n"
                        result_text += f"{'='*60}\n"
                        result_text += f" 分类：{item.get('category', '未知')}"
                        result_text += f"  |   年份：{item.get('year', '未知')}"
                        result_text += f"  |   地区：{item.get('region', '未知')}\n"
                        if item.get('genre'):
                            result_text += f" 类型：{item.get('genre')}\n"
                        if item.get('remarks'):
                            result_text += f" 备注：{item.get('remarks')}\n"
                        if item.get('score'):
                            result_text += f" 评分：{item.get('score')}\n"
                        if item.get('actors'):
                            actors = item.get('actors', '')
                            # 如果演员信息太长，截断显示
                            if len(actors) > 80:
                                result_text += f"演员：{actors[:80]}...\n"
                            else:
                                result_text += f"演员：{actors}\n"
                        if item.get('description'):
                            desc = item.get('description', '')
                            # 简介截断显示
                            if len(desc) > 100:
                                result_text += f"简介：{desc[:100]}...\n"
                            else:
                                result_text += f"简介：{desc}\n"
                        result_text += f"链接：{item.get('detail_url', '')}\n"
                        result_text += f"\n"
                    else:
                        # 兼容性处理
                        result_text += f"{i}: {item}\n"
            elif engine_type == "魔法影视":
                # 魔法影视返回 [{dict}, {dict}, ...]，直接包含播放链接
                for i, item in enumerate(results):
                    if isinstance(item, dict):
                        result_text += f"{'='*60}\n"
                        result_text += f"[{i}] {item.get('title', '未知')}\n"
                        result_text += f"{'='*60}\n"
                        result_text += f" 分类：{item.get('category', '未知')}"
                        result_text += f"  |   年份：{item.get('year', '未知')}"
                        result_text += f"  |   地区：{item.get('region', '未知')}\n"
                        if item.get('genre'):
                            result_text += f" 类型：{item.get('genre')}\n"
                        if item.get('remarks'):
                            result_text += f" 备注：{item.get('remarks')}\n"
                        if item.get('score'):
                            result_text += f"评分：{item.get('score')}\n"
                        if item.get('actors'):
                            actors = item.get('actors', '')
                            if len(actors) > 80:
                                result_text += f" 演员：{actors[:80]}...\n"
                            else:
                                result_text += f" 演员：{actors}\n"
                        if item.get('total'):
                            result_text += f" 总集数：{item.get('total')}集\n"
                        result_text += f" 播放源：{item.get('play_from', '默认')}\n"
                        result_text += f"\n"
                    else:
                        result_text += f"{i}: {item}\n"
            elif engine_type == IYF_CHANNEL:
                for i, item in enumerate(results):
                    if not isinstance(item, dict):
                        result_text += f"{i}: {item}\n"
                        continue
                    result_text += f"{'='*60}\n"
                    result_text += f"[{i}] {item.get('title', '未知')}\n"
                    result_text += f"{'='*60}\n"
                    result_text += f" 分类：{item.get('category', '未知')}"
                    result_text += f"  |   年份：{item.get('year', '未知')}"
                    result_text += f"  |   地区：{item.get('region', '未知')}\n"
                    if item.get('genre'):
                        result_text += f" 类型：{item.get('genre')}\n"
                    if item.get('score'):
                        result_text += f"评分：{item.get('score')}\n"
                    if item.get('actors'):
                        result_text += f" 演员：{item.get('actors')}\n"
                    if item.get('director'):
                        result_text += f" 导演：{item.get('director')}\n"
                    result_text += f" 剧集：{item.get('total', 0)} 集"
                    if item.get('remarks'):
                        result_text += f"  |  更新至：{item.get('remarks')}"
                    result_text += "\n\n"

            print(f"结果文本长度: {len(result_text)}")
            self.results_text.setText(result_text)
            print(f"已设置结果文本到UI")

            # 强制刷新UI
            self.results_text.update()
            QApplication.processEvents()

            # 启用提取按钮和复制按钮
            self.extract_selected_btn.setEnabled(True)
            self.extract_all_btn.setEnabled(True)
            self.copy_btn.setEnabled(True)
            print(f"已启用提取按钮")

        else:
            self.update_status("未找到相关结果")
            self.results_text.setText(f"未找到与 '{keyword}' 相关的结果")
            print("设置了无结果信息")

    def _on_search_error(self, error):
        """搜索错误回调"""
        print(f"搜索错误回调被调用: {error}")
        self.search_btn.setEnabled(True)
        self.update_status(f"搜索失败: {error}")
        CustomMessageBox.show_error(self, "搜索失败", f"搜索过程中发生错误:\n{error}")

    def extract_selected(self):
        """提取选中的m3u8"""
        if not self.search_results:
            CustomMessageBox.show_error(self, "错误", "没有搜索结果!")
            return

        # 创建选择对话框
        from PySide6.QtWidgets import QInputDialog

        # 创建选择项列表
        engine_type = self.engine_combo.currentText()
        items = []

        if engine_type == "爱瓜影视":
            # 爱瓜影视返回 [url, url, ...]
            for i, url in enumerate(self.search_results):
                display_name = url.split('/')[-1] if '/' in url else url
                items.append(f"{i}: {display_name}")
        elif engine_type in {"NCat22影视", NNYY_CHANNEL}:
            # HTML 详情页渠道返回 [{dict}, {dict}, ...]
            for i, item in enumerate(self.search_results):
                if isinstance(item, dict):
                    title = item.get('title', '未知')
                    items.append(f"{i}: {title}")
                else:
                    items.append(f"{i}: {item}")
        elif engine_type == "魔法影视":
            # 魔法影视返回 [{dict}, {dict}, ...]
            for i, item in enumerate(self.search_results):
                if isinstance(item, dict):
                    title = item.get('title', '未知')
                    remarks = item.get('remarks', '')
                    items.append(f"{i}: {title} ({remarks})")
                else:
                    items.append(f"{i}: {item}")
        elif engine_type == IYF_CHANNEL:
            for i, item in enumerate(self.search_results):
                title = item.get('title', '未知') if isinstance(item, dict) else str(item)
                items.append(f"{i}: {title}")

        # 弹出选择对话框
        item, ok = QInputDialog.getItem(
            self,
            "选择要提取的项目",
            "请选择要提取M3U8的项目:",
            items,
            0,
            False
        )

        if ok and item:
            # 解析选择的索引
            try:
                selected_index = int(item.split(':')[0])
                if 0 <= selected_index < len(self.search_results):
                    self.extract_m3u8([self.search_results[selected_index]])
                else:
                    CustomMessageBox.show_error(self, "错误", "选择的索引无效!")
            except (ValueError, IndexError):
                CustomMessageBox.show_error(self, "错误", "解析选择失败!")

    def extract_all(self):
        """提取所有m3u8"""
        if not self.search_results:
            CustomMessageBox.show_error(self, "错误", "没有搜索结果!")
            return

        self.extract_m3u8(self.search_results)

    def extract_m3u8(self, items):
        """提取m3u8链接"""
        if not self.search_engine:
            CustomMessageBox.show_error(self, "错误", "搜索引擎未初始化!")
            return

        engine_type = self.engine_combo.currentText()

        if engine_type == "爱瓜影视":
            # 爱瓜影视：直接提取m3u8
            self._extract_aigua(items)
        elif engine_type == "NCat22影视":
            # NCat22影视：需要先获取详情页，解析线路和剧集
            self._extract_ncat(items)
        elif engine_type == "魔法影视":
            # 魔法影视：直接从搜索结果中提取播放链接
            self._extract_mofa(items)
        elif engine_type == IYF_CHANNEL:
            # 爱壹帆：搜索结果含剧集 key，走播放接口取标清 m3u8
            self._extract_iyf(items)
        elif engine_type == NNYY_CHANNEL:
            # 努努影院：详情页提供剧集，/_gp 接口提供多条播放线路
            self._extract_nnyy(items)

    def _extract_aigua(self, urls):
        """爱瓜影视提取m3u8"""
        # 清空之前的结果
        if hasattr(self.search_engine, 'clear_results'):
            self.search_engine.clear_results()
        self.m3u8_results = {}

        # 禁用按钮
        self.extract_selected_btn.setEnabled(False)
        self.extract_all_btn.setEnabled(False)

        self.update_status(f"开始提取 {len(urls)} 个M3U8链接...")

        # 使用多线程并发提取（按照search.py的逻辑）
        self.search_threads = []
        for url in urls:
            thread = Thread(target=self.search_engine.get_m3u8, args=(url,))
            thread.daemon = True
            self.search_threads.append(thread)
            thread.start()

        # 启动监控线程
        monitor_thread = threading.Thread(target=self._monitor_extraction)
        monitor_thread.daemon = True
        monitor_thread.start()

    def _extract_ncat(self, items):
        """NCat22影视提取m3u8"""
        self.m3u8_results = {}

        # 禁用按钮
        self.extract_selected_btn.setEnabled(False)
        self.extract_all_btn.setEnabled(False)

        self.update_status(f"开始提取 {len(items)} 个详情页...")

        # 在线程中执行提取
        extract_thread = threading.Thread(target=self._do_ncat_extraction, args=(items,))
        extract_thread.daemon = True
        extract_thread.start()

    def _do_ncat_extraction(self, items):
        """执行NCat22影视的提取（在线程中）"""
        try:
            all_results = {}

            for idx, item in enumerate(items, 1):
                # 提取URL和标题
                if isinstance(item, dict):
                    title = item.get('title', f'视频{idx}')
                    url = item.get('detail_url', '')
                else:
                    # 兼容性处理
                    if isinstance(item, tuple) and len(item) == 2:
                        title, url = item
                    else:
                        url = item
                        title = f"视频{idx}"

                if not url:
                    print(f"跳过无效URL: {title}")
                    continue

                self.update_status(f"正在获取线路信息: {title} ({idx}/{len(items)})")
                print(f"\n处理: {title}")
                print(f"URL: {url}")

                # 获取详情页
                detail_html = self.search_engine.fetch_detail_page(url)
                if not detail_html:
                    print(f"获取详情页失败: {title}")
                    continue

                # 解析线路和剧集
                routes = self.search_engine.parse_detail_routes(detail_html, url)
                if not routes:
                    print(f"未找到播放线路，跳过: {title}")
                    continue

                print(f"找到 {len(routes)} 个播放线路")

                # 在主线程中显示线路选择对话框
                selected_route = self._show_route_selection_dialog(routes, title)

                if not selected_route:
                    print(f"用户取消选择线路: {title}")
                    continue

                # 获取选中线路的所有剧集
                route_data = routes[selected_route]
                episodes = route_data['episodes']
                total_episodes = len(episodes)

                print(f"选择线路: {selected_route}")
                print(f"开始提取 {total_episodes} 集...")

                self.update_status(f"正在提取: {title} - {selected_route} (0/{total_episodes})")

                # 使用多线程并发提取所有剧集
                from concurrent.futures import ThreadPoolExecutor, as_completed
                import threading

                # 创建线程锁保护共享数据
                results_lock = threading.Lock()
                completed_count = [0]  # 使用列表以便在闭包中修改

                def extract_single_episode(ep_info):
                    """提取单个剧集的m3u8链接"""
                    ep_idx, ep_name, ep_url = ep_info
                    try:
                        print(f"  [{ep_idx}/{total_episodes}] 提取: {ep_name}")

                        # 获取播放URL
                        _, m3u8_url = self.search_engine.get_episode_play_url(ep_url)

                        with results_lock:
                            completed_count[0] += 1
                            current = completed_count[0]

                        # 更新UI进度
                        self.update_status(f"正在提取: {title} - {selected_route} ({current}/{total_episodes})")

                        if m3u8_url:
                            key = f"{title}_{selected_route}_{ep_name}"
                            print(f"    [{current}/{total_episodes}] 成功: {ep_name}")
                            return (key, m3u8_url)
                        else:
                            print(f"    [{current}/{total_episodes}] 提取失败: {ep_name}")
                            return None

                    except Exception as e:
                        print(f"    提取失败: {ep_name} - {e}")
                        return None

                # 准备任务列表
                tasks = [(idx, ep_name, ep_url) for idx, (ep_name, ep_url) in enumerate(episodes, 1)]

                # 使用线程池并发处理（最多10个并发线程）
                max_workers = min(10, total_episodes)
                print(f"使用 {max_workers} 个线程并发提取...")

                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    # 提交所有任务
                    future_to_episode = {executor.submit(extract_single_episode, task): task for task in tasks}

                    # 收集结果
                    for future in as_completed(future_to_episode):
                        result = future.result()
                        if result:
                            key, m3u8_url = result
                            all_results[key] = m3u8_url

                success_count = len([k for k in all_results.keys() if k.startswith(f"{title}_{selected_route}")])
                print(f"完成提取: {title} - 共成功 {success_count}/{total_episodes} 集")

            # 使用信号通知UI更新
            self.signals.extraction_completed.emit(all_results)

        except Exception as e:
            print(f"NCat22影视提取异常: {e}")
            import traceback
            traceback.print_exc()
            # 发送空结果
            self.signals.extraction_completed.emit({})

    def _extract_mofa(self, items):
        """魔法影视提取m3u8（直接从搜索结果中提取）"""
        self.m3u8_results = {}

        # 禁用按钮
        self.extract_selected_btn.setEnabled(False)
        self.extract_all_btn.setEnabled(False)

        self.update_status("正在提取 M3U8 链接...")

        # 在线程中执行提取
        extract_thread = threading.Thread(target=self._do_mofa_extraction, args=(items,))
        extract_thread.daemon = True
        extract_thread.start()

    def _extract_nnyy(self, items):
        """努努影院：进入详情页并按 src_site 聚合 M3U8 线路。"""
        self.m3u8_results = {}
        self.extract_selected_btn.setEnabled(False)
        self.extract_all_btn.setEnabled(False)
        self.update_status(f"开始解析 {len(items)} 个努努影院详情页...")

        extract_thread = threading.Thread(target=self._do_nnyy_extraction, args=(items,))
        extract_thread.daemon = True
        extract_thread.start()

    def _do_nnyy_extraction(self, items):
        """在线程中读取详情、聚合线路并收集用户选中的整条线路。"""
        all_results = {}
        try:
            for index, item in enumerate(items, 1):
                if not isinstance(item, dict):
                    print(f"跳过无效努努影院结果: {item}")
                    continue

                fallback_title = item.get("title", f"视频{index}")
                self.update_status(
                    f"正在解析努努影院线路: {fallback_title} ({index}/{len(items)})"
                )
                try:
                    title, routes = self.search_engine.fetch_item_routes(item)
                except Exception as exc:
                    print(f"努努影院详情解析失败: {fallback_title} - {exc}")
                    continue

                title = title or fallback_title
                if not routes:
                    print(f"努努影院未找到可用线路: {title}")
                    continue

                selected_route = (
                    next(iter(routes))
                    if len(routes) == 1
                    else self._show_route_selection_dialog(routes, title)
                )
                if not selected_route:
                    print(f"用户取消选择努努影院线路: {title}")
                    continue

                route_info = routes[selected_route]
                episodes = route_info["episodes"]
                for episode_name, m3u8_url in episodes:
                    key = f"{title}_{selected_route}_{episode_name}"
                    all_results[key] = m3u8_url
                extracted_summary = RouteSelectionDialog._content_summary(route_info)
                print(
                    f"完成提取: {title} - {selected_route} "
                    f"成功提取 {extracted_summary}"
                )
        except Exception as exc:
            print(f"努努影院提取异常: {exc}")
            import traceback
            traceback.print_exc()
        self.signals.extraction_completed.emit(all_results)

    def _extract_iyf(self, items):
        """爱壹帆影视提取标清 m3u8"""
        self.m3u8_results = {}
        if hasattr(self.search_engine, "clear_results"):
            self.search_engine.clear_results()

        self.extract_selected_btn.setEnabled(False)
        self.extract_all_btn.setEnabled(False)
        self.update_status(f"开始提取爱壹帆标清 M3U8（{len(items)} 部）...")

        extract_thread = threading.Thread(target=self._do_iyf_extraction, args=(items,))
        extract_thread.daemon = True
        extract_thread.start()

    def _do_iyf_extraction(self, items):
        """执行爱壹帆提取（在线程中）"""
        try:
            all_results = {}
            for idx, item in enumerate(items, 1):
                if not isinstance(item, dict):
                    print(f"跳过无效爱壹帆结果: {item}")
                    continue

                title = item.get("title", f"视频{idx}")
                brief_count = len(item.get("episodes") or [])
                self.update_status(
                    f"正在提取: {title} ({idx}/{len(items)}, {brief_count} 集)"
                )
                print(f"\n处理爱壹帆: {title} | 搜索结果约 {brief_count} 集")

                try:
                    extracted = self.search_engine.extract_item(item)
                except Exception as exc:
                    print(f"爱壹帆提取失败: {title} - {exc}")
                    continue

                all_results.update(extracted)
                total_episodes = (
                    item.get("total")
                    or len(item.get("episodes") or [])
                    or brief_count
                )
                print(f"完成提取: {title} - 成功 {len(extracted)}/{total_episodes} 集")

            self.signals.extraction_completed.emit(all_results)
        except Exception as e:
            print(f"爱壹帆提取异常: {e}")
            import traceback
            traceback.print_exc()
            self.signals.extraction_completed.emit({})

    def _do_mofa_extraction(self, items):
        """执行魔法影视的提取（在线程中）"""
        try:
            all_results = {}

            for item in items:
                if isinstance(item, dict):
                    title = item.get('title', '未知')
                    play_url = item.get('play_url', '')
                    play_from = item.get('play_from', 'default')

                    if not play_url:
                        print(f"{title} 没有播放链接")
                        continue

                    print(f"\n正在处理: {title}")

                    # 解析播放链接
                    routes = self.search_engine.parse_detail_routes(item)

                    if not routes:
                        print(f"{title} 没有可用的播放线路")
                        continue

                    # 显示线路信息
                    for route_name, route_info in routes.items():
                        print(f"   线路: {route_name} | 共 {route_info['total']} 集")

                    # 如果只有一个线路，直接使用
                    if len(routes) == 1:
                        selected_route = list(routes.keys())[0]
                    else:
                        # 多个线路时，让用户选择
                        selected_route = self._show_route_selection_dialog(routes, title)
                        if not selected_route:
                            print("用户取消了线路选择")
                            continue

                    # 获取选中线路的剧集
                    route_info = routes[selected_route]
                    episodes = route_info['episodes']
                    total_episodes = route_info['total']

                    print(f"选择线路: {selected_route} | 共 {total_episodes} 集")

                    # 魔法影视的播放链接已经是m3u8格式，直接添加到结果
                    for ep_name, ep_url in episodes:
                        key = f"{title}_{selected_route}_{ep_name}"
                        all_results[key] = ep_url
                        print(f"    {ep_name}: {ep_url[:60]}...")

                    print(f"完成提取: {title} - 共 {len(episodes)} 集")

            # 使用信号通知UI更新
            self.signals.extraction_completed.emit(all_results)

        except Exception as e:
            print(f"魔法影视提取异常: {e}")
            import traceback
            traceback.print_exc()
            # 发送空结果
            self.signals.extraction_completed.emit({})

    def _show_route_selection_dialog(self, routes, title):
        """
        显示线路选择对话框（线程安全）
        :param routes: 线路数据
        :param title: 视频标题
        :return: 选中的线路名称，如果取消则返回None
        """
        import threading

        # 创建事件对象
        self.route_selection_event = threading.Event()
        self.route_selection_result = None

        print("[工作线程] 准备发送信号显示对话框...")

        # 发送信号到主线程显示对话框
        self.signals.show_route_dialog.emit(routes, title, None)

        # 等待对话框完成
        print("[工作线程] 等待对话框完成...")
        self.route_selection_event.wait()

        result = self.route_selection_result
        print(f"[工作线程] 对话框完成，返回结果: {result}")

        return result

    def _on_show_route_dialog(self, routes, title, _):
        """在主线程中显示线路选择对话框"""
        try:
            print(f"[主线程] 准备显示线路选择对话框: {title}")
            print(f"   可用线路数: {len(routes)}")

            dialog = RouteSelectionDialog(routes, title, self)
            dialog_result = dialog.exec()

            print(f"   对话框返回值: {dialog_result} ({'Accepted' if dialog_result == QDialog.Accepted else 'Rejected'})")

            if dialog_result == QDialog.Accepted:
                selected = dialog.get_selected_route()
                self.route_selection_result = selected
                print(f"[主线程] 用户选择了线路: {selected}")
                print(f"   存储到 self.route_selection_result: {self.route_selection_result}")
            else:
                print("[主线程] 用户取消了选择")
                self.route_selection_result = None

        except Exception as e:
            print(f"显示线路选择对话框失败: {e}")
            import traceback
            traceback.print_exc()
            self.route_selection_result = None
        finally:
            # 无论成功失败都要设置事件，避免死锁
            print("[主线程] 设置事件，通知工作线程继续...")
            if self.route_selection_event:
                self.route_selection_event.set()

    def _monitor_extraction(self):
        """监控提取进程"""
        try:
            # 等待所有线程完成
            for thread in self.search_threads:
                thread.join()

            # 获取结果
            results = self.search_engine.get_result()

            # 使用信号通知UI更新
            self.signals.extraction_completed.emit(results)
        except Exception as e:
            print(f"监控提取进程异常: {e}")
            # 发送空结果
            self.signals.extraction_completed.emit({})

    def _on_extraction_complete(self, results):
        """提取完成回调"""
        self.m3u8_results = results

        # 重新启用按钮
        self.extract_selected_btn.setEnabled(True)
        self.extract_all_btn.setEnabled(True)

        if results:
            self.update_status(f"提取完成: 获得 {len(results)} 个M3U8链接")

            # 显示结果
            result_text = self.results_text.toPlainText() + "\n\n"
            result_text += "=" * 50 + "\n"
            result_text += f" M3U8提取结果 ({len(results)}个):\n"
            result_text += "=" * 50 + "\n\n"

            for i, (chapter_id, m3u8_url) in enumerate(results.items(), 1):
                result_text += f"{i}. Chapter ID: {chapter_id}\n"
                result_text += f"   M3U8: {m3u8_url}\n\n"

            self.results_text.setText(result_text)

            # 启用复制按钮
            self.copy_btn.setEnabled(True)

        else:
            self.update_status("提取失败，未获得有效 M3U8 链接")

    def copy_results(self):
        """复制结果到剪贴板"""
        if not self.m3u8_results:
            CustomMessageBox.show_error(self, "错误", "没有可复制的结果!")
            return

        # 只复制M3U8链接
        m3u8_urls = list(self.m3u8_results.values())
        clipboard_text = "\n".join(m3u8_urls)

        clipboard = QApplication.clipboard()
        clipboard.setText(clipboard_text)

        self.update_status(f" 已复制 {len(m3u8_urls)} 个M3U8链接到剪贴板")

    def clear_results(self):
        """清空结果"""
        self.results_text.clear()
        self.search_results = []
        self.m3u8_results = {}

        if self.search_engine:
            self.search_engine.clear_results()

        # 禁用按钮
        self.extract_selected_btn.setEnabled(False)
        self.extract_all_btn.setEnabled(False)
        self.copy_btn.setEnabled(False)

        self.update_status("已清空所有结果")
