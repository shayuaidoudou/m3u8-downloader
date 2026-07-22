"""搜索渠道适配与统一创建入口。"""

import logging
import re
import threading
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup


logger = logging.getLogger(__name__)

AIGUA_CHANNEL = "爱瓜影视"
NCAT_CHANNEL = "NCat22影视"
MOFA_CHANNEL = "魔法影视"
IYF_CHANNEL = "爱壹帆影视"
NNYY_CHANNEL = "努努影院"
# NCat22 适配器暂时保留，但不暴露在搜索窗口的可选渠道中。
SEARCH_CHANNELS = (AIGUA_CHANNEL, MOFA_CHANNEL, IYF_CHANNEL, NNYY_CHANNEL)

CHANNEL_INPUT_TYPE = "type"
CHANNEL_INPUT_COOKIE = "ncat_cookie"
CHANNEL_INPUT_NONE = "none"


class AiGuaEngine:
    """爱瓜影视搜索与 M3U8 提取适配器。"""

    DOMAIN = "https://aigua.tv"
    REQUEST_TIMEOUT = 15
    COOKIES = {
        'hs13_bk123': '%7B%22count%22:%220%22,%22book%22:%5B%5D%7D',
        '_ga': 'GA1.1.406692144.1738847134',
        'currentcountry': '1',
        '_csrf-pc': (
            '27329b7b07834bab6c8232d1a6882fb941b0c601f7b7dda585f6ed41ac225046a%3A2%3A%7B'
            'i%3A0%3Bs%3A8%3A%22_csrf-pc%22%3Bi%3A1%3Bs%3A32%3A%22zkl4vPTk39LJYNrSDVBOtZ90BqVUaq4M%22%3B%7D'
        ),
        'Hm_lvt_acb48993923bb825b8c964792dfee455': '1756226236,1756366274,1756484441,1756545420',
        'HMACCOUNT': 'C8ED1E9E0FB8E4AC',
        'Hm_lpvt_acb48993923bb825b8c964792dfee455': '1756546424',
        '_ga_RRYTVBZ1PF': 'GS2.1.s1756545420$o13$g1$t1756546423$j11$l0$h0',
    }
    HEADERS = {
        'accept': (
            'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,'
            'image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7'
        ),
        'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'cache-control': 'no-cache',
        'pragma': 'no-cache',
        'priority': 'u=0, i',
        'referer': 'https://aigua.tv/video/search-result',
        'sec-ch-ua': '"Not;A=Brand";v="99", "Google Chrome";v="139", "Chromium";v="139"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'document',
        'sec-fetch-mode': 'navigate',
        'sec-fetch-site': 'same-origin',
        'upgrade-insecure-requests': '1',
        'user-agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'
        ),
    }

    def __init__(self, proxy_config=None, session=None, bootstrap=True):
        self.session = session or requests.Session()
        self.session.headers.update(self.HEADERS)
        self._m3u8_urls = {}
        self._result_lock = threading.Lock()
        self._configure_proxy(proxy_config)
        if bootstrap:
            self._bootstrap_session()

    def _configure_proxy(self, proxy_config):
        """将主窗口代理配置转换为 requests 代理字典。"""
        if not proxy_config or not proxy_config.get('enabled', False):
            return

        proxy_host = proxy_config.get('host', '').strip()
        if not proxy_host:
            return

        proxy_type = proxy_config.get('type', 'HTTP').lower()
        if proxy_type not in {'http', 'socks5'}:
            logger.warning("不支持的代理类型: %s", proxy_type)
            return

        proxy_port = proxy_config.get('port', 8080)
        proxy_url = f"{proxy_type}://{proxy_host}:{proxy_port}"
        self.session.proxies.update({'http': proxy_url, 'https': proxy_url})
        logger.info("已配置搜索代理: %s", proxy_url)

    def _bootstrap_session(self):
        """获取站点 Cookie；失败时保留 Session 以便后续重试。"""
        try:
            response = self.session.get(
                f'{self.DOMAIN}/video/index',
                cookies=self.COOKIES,
                timeout=self.REQUEST_TIMEOUT,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("爱瓜 Session 初始化失败: %s", exc)

    def search(self, keyword, choice=0):
        """搜索影片，choice=0 表示电影，其他值表示剧集类内容。"""
        params = {
            'page_num': '1',
            'sorttype': 'desc',
            'page_size': '24',
            'tvNum': '5',
            'sort': 'new',
            'keyword': keyword,
        }

        try:
            response = self.session.get(
                f'{self.DOMAIN}/video/refresh-video',
                params=params,
                timeout=self.REQUEST_TIMEOUT,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("爱瓜搜索失败: %s", exc)
            return []

        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')
        if choice == 0:
            return [
                urljoin(self.DOMAIN, link.get('href'))
                for link in soup.find_all('a', class_='SSjgImg', href=True)
            ]

        return [
            urljoin(self.DOMAIN, link.get('href'))
            for link in soup.find_all('a', href=True)
            if link.get('title') and not link.get('href', '').startswith('javascript:')
        ]

    def get_video_and_chapter_id(self, href):
        """从详情链接和页面中解析 videoId/chapterId。"""
        parsed_url = urlparse(href)
        if parsed_url.scheme not in {'http', 'https'} or parsed_url.netloc != urlparse(self.DOMAIN).netloc:
            logger.warning("拒绝请求非爱瓜域名的详情链接: %s", parsed_url.netloc)
            return None, None

        video_id = parse_qs(parsed_url.query).get('video_id', [None])[0]
        if not video_id:
            return None, None

        try:
            response = self.session.get(href, timeout=self.REQUEST_TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("获取爱瓜详情页失败: %s", exc)
            return None, None

        chapter_match = re.search(r"arrIndex\['chapterId'\]\s*=\s*'(.*?)';", response.text)
        if not chapter_match:
            return None, None
        return video_id, chapter_match.group(1)

    # 兼容旧调用名，新代码请使用 get_video_and_chapter_id。
    getSomeId = get_video_and_chapter_id

    def get_m3u8(self, href):
        """获取一个详情链接对应的 M3U8 地址。"""
        video_id, chapter_id = self.get_video_and_chapter_id(href)
        if not video_id or not chapter_id:
            return None

        params = {
            'citycode': 'LAX',
            'page': 'detail',
            'chapterId': chapter_id,
            'videoId': video_id,
            'sourceId': '1',
        }
        try:
            response = self.session.get(
                f'{self.DOMAIN}/video/play-url',
                params=params,
                timeout=self.REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
            m3u8_url = payload.get('data', {}).get('urlinfo', {}).get('resource_url')
        except (requests.RequestException, ValueError, AttributeError) as exc:
            logger.warning("获取爱瓜 M3U8 失败: %s", exc)
            return None

        if m3u8_url:
            with self._result_lock:
                self._m3u8_urls[chapter_id] = m3u8_url
        return m3u8_url

    def get_result(self):
        """返回按剧集编号排序的提取结果副本。"""
        def sort_key(item):
            chapter_id = item[0]
            return (0, int(chapter_id)) if chapter_id.isdigit() else (1, chapter_id)

        with self._result_lock:
            return dict(sorted(self._m3u8_urls.items(), key=sort_key))

    def clear_results(self):
        """清空已提取结果。"""
        with self._result_lock:
            self._m3u8_urls.clear()


# 保留对外的历史类名。
AiGua = AiGuaEngine


def get_channel_input_mode(channel):
    """返回渠道需要在搜索窗口展示的附加输入类型。"""
    if channel == AIGUA_CHANNEL:
        return CHANNEL_INPUT_TYPE
    if channel in {NCAT_CHANNEL, IYF_CHANNEL}:
        return CHANNEL_INPUT_COOKIE
    if channel in {MOFA_CHANNEL, NNYY_CHANNEL}:
        return CHANNEL_INPUT_NONE
    raise ValueError(f"未知搜索渠道: {channel}")


def channel_requires_refresh(channel):
    """返回搜索前是否需要重建引擎以读取最新输入。"""
    return channel in {NCAT_CHANNEL, IYF_CHANNEL}


def create_search_engine(channel, proxy_config=None, ncat_cookie='', iyf_cookie=''):
    """根据渠道名称创建搜索引擎。"""
    if channel == AIGUA_CHANNEL:
        return AiGuaEngine(proxy_config=proxy_config)
    if channel == NCAT_CHANNEL:
        from search_ncat import NCatSearcher

        return NCatSearcher(proxy_config=proxy_config, cdndefend_js_cookie=ncat_cookie)
    if channel == MOFA_CHANNEL:
        from search_mofa import MofaSearcher

        return MofaSearcher(proxy_config=proxy_config)
    if channel == IYF_CHANNEL:
        from search_iyf import IYFSearcher

        return IYFSearcher(proxy_config=proxy_config, cookie=iyf_cookie)
    if channel == NNYY_CHANNEL:
        from search_nnyy import NNYYSearcher

        return NNYYSearcher(proxy_config=proxy_config)
    raise ValueError(f"未知搜索渠道: {channel}")


def search_with_engine(channel, engine, keyword, choice=0):
    """屏蔽各搜索引擎的参数差异。"""
    if channel == AIGUA_CHANNEL:
        return engine.search(keyword, choice)
    if channel in {NCAT_CHANNEL, MOFA_CHANNEL, IYF_CHANNEL, NNYY_CHANNEL}:
        return engine.search(keyword, verbose=False)
    raise ValueError(f"未知搜索渠道: {channel}")
