"""爱壹帆影视搜索与播放适配器。"""

import hashlib
import json
import logging
import threading
import time
from urllib.parse import quote

import requests


logger = logging.getLogger(__name__)


class IYFSearcher:
    """Session 内：DrissionPage 过盾取 Cookie → 搜索 / 播放签名 → 提取标清 M3U8。"""

    HOME_URL = "https://www.iyf.tv/"
    SEARCH_URL = "https://rankv21.iyf.tv/v3/list/briefsearch"
    PLAY_URL = "https://m10.iyf.tv/v3/video/play"
    PLAYLIST_URL = "https://m10.iyf.tv/v3/video/languagesplaylist"
    SEARCH_SIGN_CONTEXT = "cinema=1&cid=0,1"
    PLAY_REGION = "JP"
    REQUEST_TIMEOUT = 15
    CF_BYPASS_TIMEOUT = 90
    PLAY_INTERVAL = 1.2
    RATE_LIMIT_RETRIES = 5
    RATE_LIMIT_BASE_WAIT = 3.0
    NETWORK_RETRIES = 3
    NETWORK_RETRY_WAIT = 2.0
    RATE_LIMIT_MARKERS = ("访问过量", "请求过于频繁", "too many", "rate limit")
    NETWORK_ERROR_MARKERS = (
        "timed out",
        "timeout",
        "connection aborted",
        "connection reset",
        "temporarily unavailable",
        "max retries exceeded",
        "failed to establish a new connection",
        "remote end closed connection",
        "read timed out",
        "connect timeout",
    )

    HEADERS = {
        "accept-language": "zh-CN,zh;q=0.9",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/150.0.0.0 Safari/537.36"
        ),
    }

    def __init__(self, proxy_config=None, cookie="", session=None):
        self.session = session or requests.Session()
        self.session.headers.update(self.HEADERS)
        self.public_key = ""
        self.private_key = ""
        self._m3u8_urls = {}
        self._result_lock = threading.Lock()
        self._browser_lock = threading.Lock()
        self._proxy_config = proxy_config or {}
        self._configure_proxy(proxy_config)
        self._apply_cookie(cookie)

    def _configure_proxy(self, proxy_config):
        if not proxy_config or not proxy_config.get("enabled", False):
            return

        host = str(proxy_config.get("host", "")).strip()
        if not host:
            return

        proxy_type = str(proxy_config.get("type", "HTTP")).lower()
        if proxy_type not in {"http", "socks5"}:
            raise ValueError(f"不支持的代理类型: {proxy_type}")

        proxy_url = f"{proxy_type}://{host}:{proxy_config.get('port', 8080)}"
        self.session.proxies.update({"http": proxy_url, "https": proxy_url})

    def _apply_cookie(self, cookie):
        """把 Cookie 写入 Session.cookies，首页与接口共用同一 jar。"""
        if isinstance(cookie, dict):
            cookie_items = {
                str(key).strip(): str(value).strip()
                for key, value in cookie.items()
                if str(key).strip()
            }
            self.cookie = "; ".join(f"{key}={value}" for key, value in cookie_items.items())
        else:
            cookie = (cookie or "").strip()
            self.cookie = cookie
            cookie_items = {}
            for part in cookie.split(";"):
                part = part.strip()
                if not part or "=" not in part:
                    continue
                name, value = part.split("=", 1)
                name = name.strip()
                if name:
                    cookie_items[name] = value.strip()

        self.session.headers.pop("Cookie", None)
        if cookie_items:
            self.session.cookies.update(cookie_items)

    @staticmethod
    def parse_home_keys(html):
        """从首页内嵌配置的 pConfig 对象读取本次请求密钥。"""
        marker_index = html.find('"pConfig"')
        if marker_index < 0:
            raise ValueError("首页中未找到 pConfig 配置")

        object_start = html.find("{", marker_index)
        if object_start < 0:
            raise ValueError("首页中的 pConfig 格式无效")

        try:
            config, _ = json.JSONDecoder().raw_decode(html[object_start:])
        except json.JSONDecodeError as exc:
            raise ValueError("无法解析首页 pConfig 配置") from exc

        public_key = config.get("publicKey", "")
        private_keys = config.get("privateKey", [])
        private_key = private_keys[0] if isinstance(private_keys, list) and private_keys else ""
        if not isinstance(public_key, str) or not public_key:
            raise ValueError("首页 pConfig 缺少 publicKey")
        if not isinstance(private_key, str) or not private_key:
            raise ValueError("首页 pConfig 缺少 privateKey")
        return public_key, private_key

    @staticmethod
    def build_signature(public_key, private_key, sign_context):
        source = f"{public_key}&{sign_context}&{private_key}"
        return hashlib.md5(source.encode("utf-8")).hexdigest()

    @classmethod
    def build_search_signature(cls, public_key, private_key):
        return cls.build_signature(public_key, private_key, cls.SEARCH_SIGN_CONTEXT)

    @classmethod
    def build_play_sign_context(cls, episode_key):
        """播放签名上下文：id 与各参数值需全小写。"""
        return (
            f"cinema=1&id={str(episode_key).lower()}"
            f"&a=0&lang=none&usersign=1&region={cls.PLAY_REGION.lower()}"
            f"&device=1&ismastersupport=0"
        )

    @classmethod
    def build_play_signature(cls, public_key, private_key, episode_key):
        return cls.build_signature(
            public_key,
            private_key,
            cls.build_play_sign_context(episode_key),
        )

    @classmethod
    def build_playlist_sign_context(cls, content_key, video_class_id, taxis=1):
        """完整剧集列表签名：参数顺序与站点 urlBuilder 一致。"""
        return (
            f"cinema=1&vid={content_key}&lsk=1&taxis={taxis}"
            f"&cid={video_class_id}"
        ).lower()

    @classmethod
    def build_playlist_signature(cls, public_key, private_key, content_key, video_class_id, taxis=1):
        return cls.build_signature(
            public_key,
            private_key,
            cls.build_playlist_sign_context(content_key, video_class_id, taxis=taxis),
        )

    @staticmethod
    def _is_cf_challenge(html):
        text = html or ""
        markers = (
            "Just a moment",
            "请稍候",
            "cf-challenge",
            "cf-browser-verification",
            "challenge-platform",
            "cdn-cgi/challenge",
            "Attention Required",
            "Enable JavaScript and cookies to continue",
        )
        return any(marker in text for marker in markers)

    @classmethod
    def _response_is_cf_challenge(cls, response):
        """判断接口/页面响应是否为 Cloudflare 挑战页。"""
        if response is None:
            return False
        text = getattr(response, "text", "") or ""
        status = getattr(response, "status_code", 0) or 0
        if cls._is_cf_challenge(text):
            return True
        if status in (403, 503) and (
            "cloudflare" in text.lower()
            or "cf-ray" in text.lower()
            or not text.strip()
        ):
            return True
        return False

    @staticmethod
    def _html_has_pconfig(html):
        return '"pConfig"' in (html or "")

    @classmethod
    def build_play_page_url(cls, content_key, episode_key=""):
        """构造播放页 URL，例如 https://www.iyf.tv/play/8G3krGD2FL5?id=g7lTuzcBvGC"""
        content_key = (content_key or "").strip()
        episode_key = (episode_key or "").strip()
        if not content_key:
            return cls.HOME_URL
        url = f"{cls.HOME_URL.rstrip('/')}/play/{content_key}"
        if episode_key:
            return f"{url}?id={episode_key}"
        return url

    @classmethod
    def build_challenge_url(cls, content_key, episode_key="", trigger="访问过量"):
        """构造访问过量触发的 CF 挑战页 URL。"""
        content_key = (content_key or "").strip()
        episode_key = (episode_key or "").strip()
        play_path = f"/play/{content_key}"
        if episode_key:
            play_path = f"{play_path}?id={episode_key}"
        return (
            f"{cls.HOME_URL.rstrip('/')}/challenge"
            f"?return={quote(play_path, safe='')}"
            f"&triggerindex={quote(trigger, safe='')}"
        )

    def _build_chromium_options(self):
        from DrissionPage import ChromiumOptions

        options = ChromiumOptions()
        proxy_config = self._proxy_config or {}
        if proxy_config.get("enabled"):
            host = str(proxy_config.get("host", "")).strip()
            if host:
                proxy_type = str(proxy_config.get("type", "HTTP")).lower()
                port = proxy_config.get("port", 8080)
                if proxy_type in {"http", "socks5"}:
                    options.set_proxy(f"{proxy_type}://{host}:{port}")
        return options

    def _sync_browser_session(self, page):
        """把浏览器 Cookie / UA 写回 requests Session。"""
        cookies = page.cookies().as_dict()
        if page.user_agent:
            self.session.headers["user-agent"] = page.user_agent
        self._apply_cookie(cookies)
        return cookies

    @staticmethod
    def _page_document_ready(page):
        try:
            state = page.run_js("return document.readyState") or ""
            return str(state) == "complete"
        except Exception:
            return False

    @staticmethod
    def _page_cf_clearance(page):
        try:
            cookies = page.cookies().as_dict() or {}
            return bool(str(cookies.get("cf_clearance") or "").strip())
        except Exception:
            return False

    @staticmethod
    def _page_title(page):
        try:
            return str(page.title or "")
        except Exception:
            return ""

    @staticmethod
    def _page_url(page):
        try:
            return str(getattr(page, "url", "") or "")
        except Exception:
            return ""

    @staticmethod
    def _is_challenge_url(url):
        return "/challenge" in (url or "").lower()

    def _is_challenge_content(self, html, title=""):
        text = f"{html or ''}\n{title or ''}"
        markers = (
            "Just a moment",
            "请稍候",
            "cf-challenge",
            "cf-browser-verification",
            "challenge-platform",
            "cdn-cgi/challenge",
            "Attention Required",
            "Enable JavaScript and cookies to continue",
            "检测到您的流量异常",
            "请验证您是真人",
            "请点击下方按钮确保您不是机器人",
            "cf-turnstile",
            "turnstile",
        )
        return any(marker in text for marker in markers)

    @staticmethod
    def _turnstile_checkbox_ready_from_html(html, title=""):
        """外层挑战页已出现（勾选框文案在 closed shadow 里，page.html 读不到）。"""
        text = f"{html or ''}\n{title or ''}"
        return any(
            marker in text
            for marker in (
                "请点击下方按钮确保您不是机器人",
                "检测到您的流量异常",
                "请验证您是真人",
                "Verify you are human",
                "cf-turnstile",
            )
        )

    def _turnstile_widget_present(self, page, html="", title=""):
        """判断 Turnstile 控件是否已挂上页面。

        「请验证您是真人」在 closed shadow root 内，普通 html 拿不到；
        因此以外层文案 + turnstile iframe/容器为准。
        """
        if self._turnstile_checkbox_ready_from_html(html, title):
            # 再确认有 iframe / 容器，避免标题刚出来、widget 还没挂上。
            try:
                html_l = (html or "").lower()
                if "cf-turnstile" in html_l or "turnstile" in html_l:
                    return True
                for iframe in page.eles("tag:iframe") or []:
                    src = (
                        f"{iframe.attr('src') or ''}"
                        f"{iframe.attr('id') or ''}"
                        f"{iframe.attr('name') or ''}"
                    ).lower()
                    if (
                        "turnstile" in src
                        or "challenges.cloudflare" in src
                        or "cf-chl" in src
                        or "cdn-cgi" in src
                    ):
                        return True
            except Exception:
                pass
            # 外层挑战文案已在，且文档 ready，通常 widget 已渲染（shadow 不可见）。
            return True
        return False

    def _wait_page_fully_loaded(self, page, timeout=20):
        """等待文档 readyState=complete。"""
        deadline = time.time() + timeout
        try:
            page.wait.doc_loaded(timeout=timeout)
        except Exception:
            pass
        while time.time() < deadline:
            if self._page_document_ready(page):
                return True
            time.sleep(0.3)
        return self._page_document_ready(page)

    def _challenge_bypass_success(self, page, saw_challenge):
        """过盾成功：只要离开 /challenge URL 即可。"""
        current_url = self._page_url(page)
        if not current_url:
            return False
        if self._is_challenge_url(current_url):
            return False
        return bool(saw_challenge) or "/play/" in current_url

    def bypass_cloudflare(self, url=None, timeout=None, require_keys=None):
        """用 DrissionPage 打开指定页过盾。

        - 首页：等到 pConfig 出现并解析密钥
        - 挑战页：等外层挑战 UI / Turnstile iframe 出现后再 Tab+Space；
          URL 离开 /challenge 即视为成功
        """
        from DrissionPage import ChromiumPage
        from DrissionPage.common import Keys

        target_url = url or self.HOME_URL
        timeout = self.CF_BYPASS_TIMEOUT if timeout is None else timeout
        if require_keys is None:
            require_keys = (
                "/play/" not in target_url
                and "/challenge" not in target_url
            )

        with self._browser_lock:
            page = ChromiumPage(addr_or_opts=self._build_chromium_options())
            try:
                logger.info("爱壹帆 Cloudflare：DrissionPage 打开 %s", target_url)
                print(f"Cloudflare 验证中，正在打开: {target_url}")
                page.get(target_url)
                self._wait_page_fully_loaded(page, timeout=min(25, timeout))

                started = time.time()
                deadline = started + timeout
                last_challenge_click = 0.0
                saw_challenge = self._is_challenge_url(target_url)
                widget_ready_at = 0.0
                last_wait_log = 0.0

                while time.time() < deadline:
                    current_url = self._page_url(page)
                    html = page.html or ""
                    title = self._page_title(page)
                    ready = self._page_document_ready(page)
                    on_challenge = self._is_challenge_url(current_url)
                    widget_ready = self._turnstile_widget_present(page, html, title)

                    if on_challenge:
                        saw_challenge = True

                    if require_keys and self._html_has_pconfig(html):
                        self._sync_browser_session(page)
                        self.public_key, self.private_key = self.parse_home_keys(html)
                        logger.info("爱壹帆 Cloudflare 已通过（首页），已同步 Cookie 与密钥")
                        return self.public_key, self.private_key

                    # 成功只看 URL：离开 /challenge 就过了。
                    if not require_keys and self._challenge_bypass_success(page, saw_challenge):
                        time.sleep(0.8)
                        current_url = self._page_url(page)
                        if self._is_challenge_url(current_url):
                            continue
                        self._sync_browser_session(page)
                        logger.info(
                            "爱壹帆 Cloudflare 已通过（URL 已离开 challenge）: %s",
                            current_url,
                        )
                        print(f"Cloudflare 验证已通过: {current_url}")
                        return self.public_key, self.private_key

                    if on_challenge and ready and widget_ready:
                        if not widget_ready_at:
                            widget_ready_at = time.time()
                            print("挑战页验证框已就绪，稍等后勾选...")
                            logger.info("爱壹帆 Cloudflare：外层挑战 UI / Turnstile 已就绪")
                        # 页面/控件就绪后每 0.5s 发送一次 Tab+Space。
                        if time.time() - last_challenge_click >= 0.5:
                            page.actions.type([Keys.TAB, Keys.SPACE])
                            last_challenge_click = time.time()
                            logger.info(
                                "爱壹帆 Cloudflare：发送 Tab + Space (%s)",
                                current_url[:100],
                            )
                            print("已发送 Tab + Space，等待跳转离开挑战页...")
                    elif on_challenge and ready and not widget_ready:
                        now = time.time()
                        if now - last_wait_log >= 3.0:
                            last_wait_log = now
                            print("挑战页已加载，等待 Turnstile 挂载...")

                    time.sleep(0.15)

                raise TimeoutError(
                    f"DrissionPage 在 {timeout}s 内未能通过 Cloudflare: {target_url}"
                )
            finally:
                try:
                    page.quit()
                except Exception:
                    pass


    def refresh_keys(self, allow_browser=True):
        """优先 requests 拉首页；遇盾则 DrissionPage 过验证。"""
        try:
            response = self.session.get(
                self.HOME_URL,
                headers={
                    "accept": (
                        "text/html,application/xhtml+xml,application/xml;q=0.9,"
                        "image/avif,image/webp,image/apng,*/*;q=0.8"
                    ),
                    "referer": self.HOME_URL,
                },
                timeout=self.REQUEST_TIMEOUT,
            )
            if response.status_code == 200 and self._html_has_pconfig(response.text):
                self.public_key, self.private_key = self.parse_home_keys(response.text)
                return self.public_key, self.private_key
            if not allow_browser:
                response.raise_for_status()
                raise ValueError("首页未包含 pConfig 配置")
            logger.info(
                "爱壹帆首页请求未拿到密钥(status=%s)，改用 DrissionPage",
                response.status_code,
            )
        except (requests.RequestException, ValueError) as exc:
            if not allow_browser:
                raise
            logger.info("爱壹帆首页请求失败，改用 DrissionPage: %s", exc)

        return self.bypass_cloudflare()

    def ensure_keys(self):
        if self.public_key and self.private_key:
            return self.public_key, self.private_key
        return self.refresh_keys(allow_browser=True)

    @staticmethod
    def parse_search_payload(payload):
        """将接口的多层 info/result 响应展开为搜索窗口统一字典。"""
        if payload.get("ret") != 200:
            raise ValueError(payload.get("msg") or "爱壹帆搜索请求失败")

        data = payload.get("data") or {}
        if data.get("code") != 0:
            raise ValueError(data.get("msg") or "爱壹帆搜索接口返回错误")

        results = []
        for group in data.get("info") or []:
            for item in group.get("result") or []:
                playlist = ((item.get("languagesPlayList") or {}).get("playList") or [])
                post_time = str(item.get("postTime") or "")
                results.append({
                    "title": item.get("title", ""),
                    "category": item.get("atypeName", ""),
                    "year": post_time[:4] if len(post_time) >= 4 else "",
                    "region": item.get("regional", ""),
                    "genre": item.get("cid", ""),
                    "actors": item.get("starring", ""),
                    "director": item.get("directed", ""),
                    "description": item.get("shortDes", ""),
                    "cover_url": item.get("imgPath", ""),
                    "remarks": item.get("lastName", ""),
                    "score": item.get("score", ""),
                    "total": len(playlist),
                    "content_key": item.get("contxt", ""),
                    "video_class_id": item.get("videoClassID", ""),
                    "episodes": [
                        {
                            "id": episode.get("id"),
                            "key": episode.get("key", ""),
                            "name": episode.get("name", ""),
                        }
                        for episode in playlist
                    ],
                })
        return results

    @staticmethod
    def pick_sd_m3u8(play_info):
        """优先取标清(576) HLS，其次非 VIP 可播清晰度，最后 flvPathList。"""
        def hls_url(path):
            if not isinstance(path, dict):
                return ""
            url = path.get("result") or path.get("rtmp") or ""
            if not url:
                return ""
            if path.get("isHls") or ".m3u8" in url:
                return url
            return ""

        for item in play_info.get("clarity") or []:
            title = str(item.get("title") or "")
            description = str(item.get("description") or "")
            if title == "576" or description == "标清":
                url = hls_url(item.get("path") or {})
                if url:
                    return url

        for item in play_info.get("clarity") or []:
            if item.get("isVIP") is False and item.get("isEnabled"):
                url = hls_url(item.get("path") or {})
                if url:
                    return url

        for item in play_info.get("flvPathList") or []:
            if item.get("isHls"):
                url = item.get("result") or item.get("rtmp") or ""
                if url:
                    return url
        return ""

    @staticmethod
    def parse_play_payload(payload):
        if payload.get("ret") != 200:
            raise ValueError(payload.get("msg") or "爱壹帆播放请求失败")

        data = payload.get("data") or {}
        if data.get("code") != 0:
            raise ValueError(data.get("msg") or "爱壹帆播放接口返回错误")

        info_list = data.get("info") or []
        if not info_list:
            raise ValueError("爱壹帆播放接口未返回媒体信息")
        return info_list[0]

    def search(self, keyword, verbose=True, enrich=False):
        """首页取 key → 计算 vv → 请求搜索接口。

        enrich=False（默认）：先快速返回搜索列表，剧集在提取时再补全。
        """
        keyword = keyword.strip()
        if not keyword:
            return []

        try:
            # 有缓存密钥时直接用，避免每次搜索都卡在首页请求上。
            public_key, private_key = self.ensure_keys()
            signature = self.build_search_signature(public_key, private_key)
            encoded_keyword = quote(keyword, safe="")
            response = self.session.post(
                self.SEARCH_URL,
                params={
                    "tags": keyword,
                    "orderby": 4,
                    "page": 1,
                    "size": 35,
                    "desc": 1,
                    "isserial": -1,
                },
                data={
                    # requests 会把百分号再次编码，得到浏览器请求中的 %25E9... 格式。
                    "tags": encoded_keyword,
                    "vv": signature,
                    "pub": public_key,
                },
                headers={
                    "accept": "application/json, text/plain, */*",
                    "content-type": "application/x-www-form-urlencoded",
                    "origin": self.HOME_URL.rstrip("/"),
                    "referer": f"{self.HOME_URL}search/{encoded_keyword}",
                },
                timeout=self.REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            results = self.parse_search_payload(response.json())
            if enrich:
                for item in results:
                    try:
                        self.enrich_episodes(item)
                    except (requests.RequestException, ValueError, TypeError) as exc:
                        logger.warning(
                            "爱壹帆补全剧集失败 %s: %s",
                            item.get("title"),
                            exc,
                        )
            if verbose:
                print(f"爱壹帆搜索到 {len(results)} 个结果")
                for item in results:
                    print(f"  - {item.get('title')}: {item.get('total')} 集")
            return results
        except (requests.RequestException, ValueError, TypeError) as exc:
            logger.warning("爱壹帆搜索失败: %s", exc)
            return []

    @staticmethod
    def parse_playlist_payload(payload):
        if payload.get("ret") != 200:
            raise ValueError(payload.get("msg") or "爱壹帆剧集列表请求失败")

        data = payload.get("data") or {}
        if data.get("code") != 0:
            raise ValueError(data.get("msg") or "爱壹帆剧集列表接口返回错误")

        info_list = data.get("info") or []
        if not info_list:
            raise ValueError("爱壹帆剧集列表为空")

        playlist = info_list[0].get("playList") or []
        return [
            {
                "id": episode.get("id"),
                "key": episode.get("key", ""),
                "name": episode.get("name", ""),
            }
            for episode in playlist
            if episode.get("key")
        ]

    def fetch_full_playlist(self, content_key, video_class_id, taxis=1, allow_cf_bypass=True):
        """拉取完整剧集列表（搜索接口的 languagesPlayList 可能不完整）。"""
        content_key = (content_key or "").strip()
        video_class_id = (video_class_id or "").strip()
        if not content_key or not video_class_id:
            raise ValueError("补全剧集需要 content_key 与 video_class_id")

        public_key, private_key = self.ensure_keys()
        params = [
            ("cinema", "1"),
            ("vid", content_key),
            ("lsk", "1"),
            ("taxis", str(taxis)),
            ("cid", video_class_id),
        ]
        query = "&".join(f"{key}={value}" for key, value in params)
        signature = self.build_signature(public_key, private_key, query.lower())
        # 手动拼 URL，避免 cid 中的逗号被二次编码导致验签失败。
        url = (
            f"{self.PLAYLIST_URL}?{query}"
            f"&vv={signature}&pub={public_key}"
        )
        play_page_url = self.build_play_page_url(content_key)
        response = self.session.get(
            url,
            headers={
                "accept": "application/json, text/plain, */*",
                "origin": self.HOME_URL.rstrip("/"),
                "referer": play_page_url,
            },
            timeout=self.REQUEST_TIMEOUT,
        )
        if self._response_is_cf_challenge(response):
            if not allow_cf_bypass:
                raise ValueError(f"Cloudflare 验证未通过: {play_page_url}")
            logger.warning("剧集列表接口触发 Cloudflare，打开播放页过盾: %s", play_page_url)
            self.bypass_cloudflare(url=play_page_url, require_keys=False)
            return self.fetch_full_playlist(
                content_key,
                video_class_id,
                taxis=taxis,
                allow_cf_bypass=False,
            )
        response.raise_for_status()
        return self.parse_playlist_payload(response.json())

    def enrich_episodes(self, item):
        """用完整剧集列表覆盖搜索结果中的截断 playList。"""
        content_key = item.get("content_key") or ""
        video_class_id = item.get("video_class_id") or ""
        brief_count = len(item.get("episodes") or [])
        episodes = self.fetch_full_playlist(content_key, video_class_id)
        if len(episodes) >= brief_count:
            item["episodes"] = episodes
            item["total"] = len(episodes)
        return item

    @staticmethod
    def _is_rate_limited(error):
        text = str(error or "").lower()
        return any(marker.lower() in text for marker in IYFSearcher.RATE_LIMIT_MARKERS)

    @staticmethod
    def _is_cf_error(error):
        text = str(error or "").lower()
        markers = (
            "cloudflare",
            "just a moment",
            "challenge-platform",
            "cf验证",
            "cf 验证",
            "未能通过 cloudflare",
        )
        return any(marker in text for marker in markers)

    @staticmethod
    def _is_transient_network_error(error):
        """超时/连接中断等可重试网络错误。"""
        if isinstance(
            error,
            (
                requests.exceptions.Timeout,
                requests.exceptions.ConnectionError,
                requests.exceptions.ChunkedEncodingError,
            ),
        ):
            return True
        text = str(error or "").lower()
        return any(marker in text for marker in IYFSearcher.NETWORK_ERROR_MARKERS)

    def fetch_play_info(self, content_key, episode_key, refresh_keys=False, allow_cf_bypass=True):
        """请求播放接口，返回 info[0]。遇 CF 则打开播放页过盾后重试一次。"""
        if refresh_keys:
            try:
                public_key, private_key = self.refresh_keys(allow_browser=False)
            except (requests.RequestException, ValueError, TypeError) as exc:
                logger.warning("刷新密钥失败，继续使用现有密钥: %s", exc)
                public_key, private_key = self.ensure_keys()
        else:
            public_key, private_key = self.ensure_keys()
        signature = self.build_play_signature(public_key, private_key, episode_key)
        play_page_url = self.build_play_page_url(content_key, episode_key)
        response = self.session.get(
            self.PLAY_URL,
            params={
                "cinema": "1",
                "id": episode_key,
                "a": "0",
                "lang": "none",
                "usersign": "1",
                "region": self.PLAY_REGION,
                "device": "1",
                "isMasterSupport": "0",
                "vv": signature,
                "pub": public_key,
            },
            headers={
                "accept": "application/json, text/plain, */*",
                "origin": self.HOME_URL.rstrip("/"),
                "referer": play_page_url,
            },
            timeout=self.REQUEST_TIMEOUT,
        )

        if self._response_is_cf_challenge(response):
            if not allow_cf_bypass:
                raise ValueError(f"Cloudflare 验证未通过: {play_page_url}")
            logger.warning("播放接口触发 Cloudflare，改用 DP 打开播放页: %s", play_page_url)
            self.bypass_cloudflare(url=play_page_url, require_keys=False)
            return self.fetch_play_info(
                content_key,
                episode_key,
                refresh_keys=True,
                allow_cf_bypass=False,
            )

        try:
            payload = response.json()
        except ValueError as exc:
            if allow_cf_bypass and self._is_cf_challenge(response.text):
                logger.warning("播放响应非 JSON 且疑似 CF，打开播放页过盾: %s", play_page_url)
                self.bypass_cloudflare(url=play_page_url, require_keys=False)
                return self.fetch_play_info(
                    content_key,
                    episode_key,
                    refresh_keys=True,
                    allow_cf_bypass=False,
                )
            raise ValueError("爱壹帆播放接口返回了无效 JSON") from exc

        response.raise_for_status()
        return self.parse_play_payload(payload)

    def get_episode_m3u8(self, content_key, episode_key):
        """获取单集标清 M3U8；遇访问过量/超时等可重试错误时自动重试。"""
        max_attempts = max(self.RATE_LIMIT_RETRIES, self.NETWORK_RETRIES)
        last_error = None
        for attempt in range(max_attempts):
            try:
                play_info = self.fetch_play_info(
                    content_key,
                    episode_key,
                    refresh_keys=attempt > 0,
                    # 限流分支统一过盾，避免 fetch_play_info 内部先静默重试一次。
                    allow_cf_bypass=False,
                )
                m3u8_url = self.pick_sd_m3u8(play_info)
                if not m3u8_url:
                    raise ValueError("未找到标清 M3U8 地址")
                return m3u8_url
            except (requests.RequestException, ValueError, TypeError, TimeoutError) as exc:
                last_error = exc
                is_rate = self._is_rate_limited(exc)
                is_cf = self._is_cf_error(exc) or self._is_cf_challenge(str(exc))
                is_network = self._is_transient_network_error(exc)
                if not (is_rate or is_cf or is_network) or attempt >= max_attempts - 1:
                    raise

                if is_network and not (is_rate or is_cf):
                    wait_seconds = self.NETWORK_RETRY_WAIT * (attempt + 1)
                    logger.warning(
                        "爱壹帆播放网络异常，%.1fs 后重试 (%s/%s): %s",
                        wait_seconds,
                        attempt + 1,
                        max_attempts,
                        exc,
                    )
                    print(
                        f"请求超时/网络异常，{wait_seconds:.1f}s 后重试 "
                        f"({attempt + 1}/{max_attempts})..."
                    )
                    time.sleep(wait_seconds)
                    continue

                challenge_url = self.build_challenge_url(content_key, episode_key)
                wait_seconds = self.RATE_LIMIT_BASE_WAIT * (2 ** attempt)
                logger.warning(
                    "爱壹帆播放限流/CF，打开挑战页过盾后重试 (%s/%s): %s",
                    attempt + 1,
                    max_attempts,
                    exc,
                )
                print(
                    f"访问过量，正在打开挑战页过验证后重试 "
                    f"({attempt + 1}/{max_attempts}): {challenge_url}"
                )
                try:
                    self.bypass_cloudflare(url=challenge_url, require_keys=False)
                except Exception as bypass_exc:
                    logger.warning(
                        "播放页过盾失败，%.1fs 后仅退避重试: %s",
                        wait_seconds,
                        bypass_exc,
                    )
                    print(f"过盾失败，等待 {wait_seconds:.1f}s 后重试...")
                    time.sleep(wait_seconds)
                    continue
                # 过盾成功后稍等再请求，降低立刻再次限流概率。
                if wait_seconds > 0:
                    time.sleep(min(wait_seconds, self.RATE_LIMIT_BASE_WAIT))
        raise last_error

    def extract_item(self, item):
        """从一条搜索结果提取全部剧集的标清 M3U8。"""
        title = item.get("title") or "未知"
        content_key = item.get("content_key") or ""
        episodes = item.get("episodes") or []
        if not content_key:
            raise ValueError(f"{title} 缺少 content_key")
        if not episodes:
            raise ValueError(f"{title} 没有剧集列表")

        self.ensure_keys()
        try:
            self.enrich_episodes(item)
        except (requests.RequestException, ValueError, TypeError) as exc:
            logger.warning("爱壹帆提取前补全剧集失败 %s: %s", title, exc)
        episodes = item.get("episodes") or []
        if not episodes:
            raise ValueError(f"{title} 没有剧集列表")

        extracted = {}
        for index, episode in enumerate(episodes):
            ep_name = str(episode.get("name") or "").strip() or "01"
            ep_key = episode.get("key") or ""
            if not ep_key:
                continue
            if index > 0 and self.PLAY_INTERVAL > 0:
                time.sleep(self.PLAY_INTERVAL)
            try:
                m3u8_url = self.get_episode_m3u8(content_key, ep_key)
            except (requests.RequestException, ValueError, TypeError) as exc:
                logger.warning("爱壹帆提取失败 %s %s: %s", title, ep_name, exc)
                print(f"爱壹帆提取失败 {title} {ep_name}: {exc}")
                continue
            result_key = f"{title}_标清_{ep_name}"
            extracted[result_key] = m3u8_url
            with self._result_lock:
                self._m3u8_urls[result_key] = m3u8_url
            print(f"   ✓ {ep_name}: {m3u8_url[:80]}...")
        return extracted

    def clear_results(self):
        with self._result_lock:
            self._m3u8_urls.clear()

    def get_result(self):
        with self._result_lock:
            return dict(self._m3u8_urls)
