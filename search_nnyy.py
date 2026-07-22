"""努努影院搜索、详情页剧集解析与 M3U8 线路聚合。"""

from __future__ import annotations

import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup


logger = logging.getLogger(__name__)


class NNYYSearcher:
    """通过首页 Session、搜索页、详情页和 ``/_gp`` 接口提取播放线路。"""

    BASE_URL = "https://nnyy.in"
    HOME_URL = f"{BASE_URL}/"
    SEARCH_URL = f"{BASE_URL}/so"
    REQUEST_TIMEOUT = 15
    ROUTE_WORKERS = 4
    API_REQUEST_INTERVAL = 0.35
    RATE_LIMIT_RETRIES = 4
    RATE_LIMIT_BASE_WAIT = 1.0
    ROUTE_LABELS = {
        "hnzy": "HN",
        "gszy": "GS",
        "mdzy": "MD",
        "bfzy": "BF",
        "lzzy": "LZ",
        "ukzy": "UK",
        "ffzy": "FF",
        "sdzy2": "SD",
        "xlzy": "XL",
        "wjzy2": "WJ",
        "yhzy": "YH",
        "jyzy": "JY",
        "bdzy2": "BD",
    }
    CATEGORY_LABELS = {
        "dianying": "电影",
        "dianshiju": "电视剧",
        "zongyi": "综艺",
        "dongman": "动漫",
    }
    HEADERS = {
        "accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,image/apng,*/*;q=0.8"
        ),
        "accept-language": "zh-CN,zh;q=0.9",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "sec-ch-ua": '"Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "upgrade-insecure-requests": "1",
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/150.0.0.0 Safari/537.36"
        ),
    }

    def __init__(self, base_url=None, proxy_config=None, session=None):
        self.base_url = (base_url or self.BASE_URL).rstrip("/")
        self.home_url = f"{self.base_url}/"
        self.search_url = f"{self.base_url}/so"
        self.session = session or requests.Session()
        self.session.headers.update(self.HEADERS)
        self._bootstrap_done = False
        self._bootstrap_lock = threading.Lock()
        self._api_request_lock = threading.Lock()
        self._next_api_request_at = 0.0
        self._last_search_url = self.search_url
        self._configure_proxy(proxy_config)

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

    def _same_origin(self, url):
        parsed = urlparse(url)
        base = urlparse(self.base_url)
        return parsed.scheme in {"http", "https"} and parsed.netloc == base.netloc

    def _bootstrap_session(self):
        """访问首页，让 Session 自动接收站点下发的 Cookie。"""
        if self._bootstrap_done:
            return
        with self._bootstrap_lock:
            if self._bootstrap_done:
                return
            response = self.session.get(self.home_url, timeout=self.REQUEST_TIMEOUT)
            response.raise_for_status()
            self._bootstrap_done = True

    @staticmethod
    def _category_from_url(detail_url):
        path_parts = [part for part in urlparse(detail_url).path.split("/") if part]
        slug = path_parts[0] if path_parts else ""
        return NNYYSearcher.CATEGORY_LABELS.get(slug, slug)

    @staticmethod
    def parse_search_results(html, base_url=BASE_URL):
        """解析搜索结果卡片，并统一为项目通用字典格式。"""
        soup = BeautifulSoup(html or "", "html.parser")
        base_netloc = urlparse(base_url).netloc
        results = []
        seen_urls = set()
        for item in soup.select(".lists-filter .lists-content li"):
            title_link = item.select_one("h2 a[href]")
            if title_link is None:
                continue
            detail_url = urljoin(base_url, title_link.get("href", ""))
            if (
                not detail_url
                or urlparse(detail_url).netloc != base_netloc
                or detail_url in seen_urls
            ):
                continue
            seen_urls.add(detail_url)

            image = item.select_one("a.thumbnail img")
            note = item.select_one(".note span")
            tags = [node.get_text(" ", strip=True) for node in item.select(".countrie span")]
            rate = item.select_one(".rate")
            results.append({
                "title": title_link.get_text(" ", strip=True),
                "detail_url": detail_url,
                "category": NNYYSearcher._category_from_url(detail_url),
                "year": tags[0] if tags else "",
                "region": tags[1] if len(tags) > 1 else "",
                "remarks": note.get_text(" ", strip=True) if note else "",
                "score": rate.get_text(" ", strip=True) if rate else "",
                "cover_url": urljoin(base_url, image.get("src", "")) if image else "",
            })
        return results

    def search(self, keyword, verbose=True):
        keyword = (keyword or "").strip()
        if not keyword:
            return []
        try:
            self._bootstrap_session()
            response = self.session.get(
                self.search_url,
                params={"q": keyword},
                headers={"referer": self.home_url},
                timeout=self.REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            response.encoding = "utf-8"
            self._last_search_url = getattr(response, "url", "") or (
                f"{self.search_url}?q={quote(keyword)}"
            )
            results = self.parse_search_results(response.text, self.base_url)
            if verbose:
                print(f"努努影院搜索到 {len(results)} 个结果")
            return results
        except requests.RequestException as exc:
            logger.warning("努努影院搜索失败: %s", exc)
            return []

    def fetch_detail_page(self, detail_url):
        detail_url = urljoin(self.base_url, detail_url or "")
        if not self._same_origin(detail_url):
            logger.warning("拒绝请求非努努影院域名的详情链接: %s", detail_url)
            return ""
        try:
            self._bootstrap_session()
            response = self.session.get(
                detail_url,
                headers={"referer": self._last_search_url},
                timeout=self.REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            response.encoding = "utf-8"
            return response.text
        except requests.RequestException as exc:
            logger.warning("获取努努影院详情页失败: %s", exc)
            return ""

    @staticmethod
    def _video_id(detail_url, html):
        match = re.search(r"/(?:[^/]+)/([0-9]+)\.html(?:$|[?#])", detail_url or "")
        if not match:
            match = re.search(r"replace\('\{0\}',\s*'([0-9]+)'\)", html or "")
        return match.group(1) if match else ""

    @staticmethod
    def _episode_sort_key(episode):
        slug = episode[1].rsplit("/", 1)[-1]
        match = re.fullmatch(r"ep([0-9]+)", slug)
        return (0, int(match.group(1))) if match else (1, slug)

    def parse_detail_episodes(self, html, detail_url):
        """读取详情页影片 ID 与所有 ``ep_slug``。"""
        video_id = self._video_id(detail_url, html)
        if not video_id:
            return {"title": "", "video_id": "", "episodes": []}

        soup = BeautifulSoup(html or "", "html.parser")
        title_node = soup.select_one("h1.product-title")
        title = ""
        if title_node is not None:
            title = next(title_node.stripped_strings, "")

        episodes = []
        seen_slugs = set()
        for node in soup.select("#eps-ul li[ep_slug]"):
            slug = (node.get("ep_slug") or "").strip()
            if not re.fullmatch(r"[A-Za-z0-9_]+", slug) or slug in seen_slugs:
                continue
            seen_slugs.add(slug)
            name = node.get_text(" ", strip=True) or slug
            api_url = urljoin(self.base_url, f"/_gp/{video_id}/{slug}")
            episodes.append((name, api_url))
        episodes.sort(key=self._episode_sort_key)
        return {"title": title, "video_id": video_id, "episodes": episodes}

    @staticmethod
    def parse_episode_payload(payload):
        """提取并去重单集接口中的 ``(src_site, m3u8)``。"""
        if not isinstance(payload, dict):
            return []
        sources = []
        seen_sources = set()
        for item in payload.get("video_plays") or []:
            if not isinstance(item, dict):
                continue
            source = str(item.get("src_site") or "default").strip().lower()
            m3u8_url = str(item.get("play_data") or "").strip()
            parsed = urlparse(m3u8_url)
            if (
                parsed.scheme not in {"http", "https"}
                or ".m3u8" not in parsed.path.lower()
                or source in seen_sources
            ):
                continue
            seen_sources.add(source)
            sources.append((source, m3u8_url))
        return sources

    def fetch_episode_sources(self, api_url, detail_url):
        if not self._same_origin(api_url) or not urlparse(api_url).path.startswith("/_gp/"):
            raise ValueError(f"无效的努努影院剧集接口: {api_url}")
        for attempt in range(self.RATE_LIMIT_RETRIES + 1):
            self._wait_for_api_slot()
            response = self.session.get(
                api_url,
                headers={
                    "accept": "application/json, text/javascript, */*; q=0.01",
                    "referer": detail_url,
                    "x-requested-with": "XMLHttpRequest",
                },
                timeout=self.REQUEST_TIMEOUT,
            )
            if getattr(response, "status_code", 200) != 429:
                response.raise_for_status()
                return self.parse_episode_payload(response.json())
            if attempt >= self.RATE_LIMIT_RETRIES:
                response.raise_for_status()

            retry_after = self._retry_after_seconds(response, attempt)
            self._defer_api_requests(retry_after)
            logger.warning("努努影院接口限流，%.1f 秒后重试: %s", retry_after, api_url)
        return []

    def _wait_for_api_slot(self):
        """全局节流，避免并发线程同时撞上站点限流。"""
        with self._api_request_lock:
            now = time.monotonic()
            if self._next_api_request_at > now:
                time.sleep(self._next_api_request_at - now)
            self._next_api_request_at = time.monotonic() + self.API_REQUEST_INTERVAL

    def _defer_api_requests(self, seconds):
        with self._api_request_lock:
            self._next_api_request_at = max(
                self._next_api_request_at,
                time.monotonic() + max(0.0, seconds),
            )

    def _retry_after_seconds(self, response, attempt):
        raw_value = (getattr(response, "headers", {}) or {}).get("Retry-After", "")
        try:
            return max(float(raw_value), self.RATE_LIMIT_BASE_WAIT)
        except (TypeError, ValueError):
            return self.RATE_LIMIT_BASE_WAIT * (2 ** attempt)

    def _route_name(self, source):
        label = self.ROUTE_LABELS.get(source, source.upper() or "默认")
        return f"{label} · {source}" if source else label

    @staticmethod
    def _is_regular_episode(api_url):
        """区分正片剧集与彩蛋等特别内容。"""
        slug = urlparse(api_url or "").path.rsplit("/", 1)[-1]
        return re.fullmatch(r"ep[0-9]+", slug, re.IGNORECASE) is not None

    def build_routes(self, episodes, detail_url, max_workers=ROUTE_WORKERS):
        """并发请求各集接口，再按 ``src_site`` 聚合成线路。"""
        if not episodes:
            return {}
        workers = max(1, min(int(max_workers), len(episodes)))
        indexed_sources = {}
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(self.fetch_episode_sources, api_url, detail_url): index
                for index, (_, api_url) in enumerate(episodes)
            }
            for future in as_completed(futures):
                index = futures[future]
                try:
                    indexed_sources[index] = future.result()
                except (requests.RequestException, ValueError) as exc:
                    logger.warning("努努影院第 %s 个剧集接口失败: %s", index + 1, exc)

        grouped = {}
        grouped_regular_counts = {}
        regular_flags = [self._is_regular_episode(api_url) for _, api_url in episodes]
        for index, (episode_name, _) in enumerate(episodes):
            for source, m3u8_url in indexed_sources.get(index, []):
                grouped.setdefault(source, []).append((episode_name, m3u8_url))
                if regular_flags[index]:
                    grouped_regular_counts[source] = grouped_regular_counts.get(source, 0) + 1
        total = len(episodes)
        regular_total = sum(regular_flags)
        special_total = total - regular_total
        return {
            self._route_name(source): {
                "total": total,
                "episodes": route_episodes,
                "regular_total": regular_total,
                "special_total": special_total,
                "regular_count": grouped_regular_counts.get(source, 0),
                "special_count": (
                    len(route_episodes) - grouped_regular_counts.get(source, 0)
                ),
            }
            for source, route_episodes in grouped.items()
            if route_episodes
        }

    def fetch_item_routes(self, item):
        """从一个搜索结果进入详情页，并返回标题与线路集合。"""
        if not isinstance(item, dict):
            return "", {}
        detail_url = item.get("detail_url", "")
        html = self.fetch_detail_page(detail_url)
        if not html:
            return item.get("title", ""), {}
        detail = self.parse_detail_episodes(html, detail_url)
        title = detail.get("title") or item.get("title", "")
        routes = self.build_routes(detail.get("episodes") or [], detail_url)
        return title, routes

    @staticmethod
    def get_episode_play_url(episode_url):
        """兼容通用线路接口；聚合后的 episode_url 已是 M3U8。"""
        return episode_url, episode_url

    def clear_results(self):
        """兼容搜索窗口的统一引擎接口。"""

    def get_result(self):
        """兼容搜索窗口的统一引擎接口。"""
        return {}
