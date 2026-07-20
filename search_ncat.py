"""
-*- coding: utf-8 -*-
@File   : search_ncat.py
@author : @鲨鱼爱兜兜
@Time   : 2025/11/25
@Desc   : NCat22影视搜索引擎
"""

import re
import time
import requests
from bs4 import BeautifulSoup
from typing import List, Tuple, Dict
from functools import wraps


def retry_on_failure(max_retries: int = 3, delay: float = 2.0, backoff: float = 2.0):
    """
    装饰器：失败时自动重试
    :param max_retries: 最大重试次数
    :param delay: 初始延迟时间（秒）
    :param backoff: 延迟时间的倍增因子
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            current_delay = delay

            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except (
                    requests.exceptions.SSLError,
                    requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout,
                    requests.exceptions.RequestException,
                    Exception
                ) as e:
                    retries += 1
                    error_type = type(e).__name__
                    error_msg = str(e)

                    if "SSL" in error_msg or "ssl" in error_msg.lower():
                        error_type = "SSL Error"

                    if retries < max_retries:
                        print(f"️  请求失败 ({error_type}): {error_msg[:100]}...")
                        print(f"   第 {retries}/{max_retries} 次重试，等待 {current_delay} 秒...")
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        print(f" 达到最大重试次数 ({max_retries})，请求失败")
                        print(f"   最后错误: {error_msg[:200]}")
                        raise

            return None
        return wrapper
    return decorator


class NCatSearcher:
    """NCat22搜索引擎类"""
    
    def __init__(self, base_url: str = "https://www.ncat22.com", proxy_config: dict = None, cdndefend_js_cookie: str = None):
        """
        初始化NCat22搜索器
        :param base_url: 基础URL
        :param proxy_config: 代理配置
        :param cdndefend_js_cookie: 用户自定义的cdndefend_js_cookie值，如果为None则使用默认值
        """
        self.base_url = base_url
        self.session = requests.Session()
        self.cookies = self._init_cookies(cdndefend_js_cookie)
        self.headers = self._init_headers()
        
        # 配置代理
        self.proxies = None
        if proxy_config and proxy_config.get('enabled', False):
            proxy_host = proxy_config.get('host', '127.0.0.1')
            proxy_port = proxy_config.get('port', 7897)
            proxy_url = f'http://{proxy_host}:{proxy_port}'
            self.proxies = {
                'http': proxy_url,
                'https': proxy_url
            }
            print(f" 已配置代理: {proxy_url}")
    
    @staticmethod
    def _init_cookies(cdndefend_js_cookie: str = None) -> dict:
        """
        初始化cookies
        :param cdndefend_js_cookie: 用户自定义的cdndefend_js_cookie值，如果为None或空字符串则使用默认值
        """
        # 默认的cdndefend_js_cookie值
        default_cookie = '9D26C06506785F350529EE218BC500823FC3AEC333061'
        
        # 判断：只有当cdndefend_js_cookie不为None且不为空字符串时才使用用户输入的值
        if cdndefend_js_cookie and cdndefend_js_cookie.strip():
            final_cookie = cdndefend_js_cookie.strip()
            print(f" 使用用户自定义cdndefend_js_cookie: {final_cookie[:50]}...")
        else:
            final_cookie = default_cookie
            print(f"️  使用默认cdndefend_js_cookie: {final_cookie[:50]}...")
        
        return {
            'cdndefend_js_cookie': final_cookie,
        }
    
    @staticmethod
    def _init_headers() -> dict:
        """初始化请求头"""
        return {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'cache-control': 'max-age=0',
            'sec-ch-ua': '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'upgrade-insecure-requests': '1',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-user': '?1',
            'sec-fetch-dest': 'document',
            'referer': 'https://www.ncat22.com/',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'priority': 'u=0, i',
        }
    
    @retry_on_failure()
    def _get_search_token(self) -> str:
        """
        获取搜索所需的t参数
        :return: t参数值
        """
        response = self.session.get(
            f'{self.base_url}',
            cookies=self.cookies,
            headers=self.headers,
            proxies=self.proxies,
            timeout=10,
            verify=False
        )
        response.encoding = 'utf-8'
        print(response.text)
        # 提取t参数 - 匹配 <input type="hidden" name="t" value="xxx"/>
        # <input type="hidden" name="t" value="TS4LiDpPFbUlgq3YjjF+yQ=="/>
        t_match = re.findall(r'name="t"\s+value="([^"]+)"', response.text)
        if t_match:
            return t_match[0]
        
        # 备用方案：尝试其他可能的格式
        t_match = re.findall(r'<input[^>]*name=["\']t["\'][^>]*value=["\']([^"\']+)["\']', response.text)
        if t_match:
            return t_match[0]
        
        # 再尝试反向顺序 (value在name前面)
        t_match = re.findall(r'<input[^>]*value=["\']([^"\']+)["\'][^>]*name=["\']t["\']', response.text)
        if t_match:
            return t_match[0]
        
        raise Exception("无法获取搜索token(t参数)")
    
    @staticmethod
    def parse_search_results(html_content: str) -> List[Dict]:
        """
        解析搜索结果页面,提取影片信息
        :param html_content: HTML页面内容
        :return: 包含影片信息的字典列表
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        results = []

        # 查找所有搜索结果项
        search_items = soup.find_all('a', class_='search-result-item')

        for item in search_items:
            # 提取详情页URL并拼接完整域名
            detail_url = item.get('href', '')
            if detail_url and not detail_url.startswith('http'):
                detail_url = 'https://www.ncat22.com' + detail_url

            # 提取分类
            category_div = item.find('div', class_='search-result-item-header')
            category = category_div.find('div').text.strip() if category_div else ''

            # 提取标题
            title_div = item.find('div', class_='title')
            title = title_div.text.strip() if title_div else ''

            # 提取标签信息(年份、地区、类型)
            tags_div = item.find('div', class_='tags')
            tags_info = {}
            if tags_div:
                tags_text = tags_div.get_text(separator='|', strip=True)
                tags_parts = [t.strip() for t in tags_text.split('|') if t.strip() and t.strip() != '/']
                if len(tags_parts) >= 1:
                    tags_info['year'] = tags_parts[0]
                if len(tags_parts) >= 2:
                    tags_info['region'] = tags_parts[1]
                if len(tags_parts) >= 3:
                    tags_info['genre'] = tags_parts[2]

            # 提取演员信息
            actors_div = item.find('div', class_='actors')
            actors = ''
            if actors_div:
                actors_span = actors_div.find('span')
                actors = actors_span.text.strip() if actors_span else ''

            # 提取简介
            desc_div = item.find('div', class_='desc')
            description = desc_div.text.strip() if desc_div else ''
            # 清理HTML标签
            description = re.sub(r'<br>', ' ', description)
            description = re.sub(r'&lt;br&gt;', ' ', description)

            # 提取封面图片URL并拼接完整域名
            img_tag = item.find('img', class_='lazy lazyload')
            cover_url = ''
            if img_tag:
                cover_url = img_tag.get('data-original', '')
                if cover_url and not cover_url.startswith('http'):
                    cover_url = 'https://www.ncat22.com' + cover_url

            # 组装数据
            result_data = {
                'title': title,
                'detail_url': detail_url,
                'category': category,
                'year': tags_info.get('year', ''),
                'region': tags_info.get('region', ''),
                'genre': tags_info.get('genre', ''),
                'actors': actors,
                'description': description,
                'cover_url': cover_url
            }

            results.append(result_data)

        return results

    @retry_on_failure()
    def search(self, keyword: str, verbose: bool = True) -> List[Dict]:
        """
        搜索视频
        :param keyword: 搜索关键词
        :param verbose: 是否打印详细信息
        :return: 包含影片信息的字典列表
        """
        try:
            if verbose:
                print(f"搜索关键词: {keyword}\n")

            # 第一步：获取搜索token
            t_param = self._get_search_token()
            if verbose:
                print(f" 获取到t参数: {t_param}")

            # 第二步：执行搜索
            params = {
                't': t_param,
                'k': keyword,
            }

            response = self.session.get(
                f'{self.base_url}/search',
                params=params,
                cookies=self.cookies,
                headers=self.headers,
                proxies=self.proxies,
                timeout=10,
                verify=False
            )
            response.encoding = 'utf-8'

            # 解析搜索结果
            results = self.parse_search_results(response.text)

            if verbose:
                print(f" 搜索到 {len(results)} 个结果\n")

            return results

        except Exception as e:
            print(f"搜索失败: {e}")
            import traceback
            traceback.print_exc()
            return []

    @staticmethod
    def parse_detail_page(html_content: str) -> Dict:
        """
        解析详情页,提取线路信息和剧集信息
        :param html_content: 详情页HTML内容
        :return: 包含线路和剧集信息的字典
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        detail_info = {
            'title': '',
            'routes': []  # 线路列表
        }

        # 提取标题
        title_tag = soup.find('h1', class_='title') or soup.find('div', class_='title')
        if title_tag:
            detail_info['title'] = title_tag.text.strip()

        # 定义需要过滤的线路关键词(只能APP内观看的线路)
        app_only_keywords = ['4K', '高峰不卡', 'APP专享', '专享']

        # 查找所有线路标签 (在 source-swiper-slide 中)
        route_slides = soup.find_all('div', class_='source-swiper-slide')
        route_names = []

        for slide in route_slides:
            label_span = slide.find('span', class_='source-item-label')
            if label_span:
                route_name = label_span.text.strip()
                # 检查是否包含APP专享关键词
                is_app_only = any(keyword in route_name for keyword in app_only_keywords)
                if not is_app_only:
                    route_names.append(route_name)
                else:
                    # 添加None作为占位符,保持索引对应
                    route_names.append(None)

        # 查找所有剧集列表容器 (class="episode-list")
        episode_lists = soup.find_all('div', class_='episode-list')

        # 将线路名称和剧集列表对应起来
        for idx, episode_list in enumerate(episode_lists):
            # 获取线路名称
            route_name = route_names[idx] if idx < len(route_names) else f"线路{idx + 1}"

            # 跳过被过滤的线路
            if route_name is None:
                continue

            # 提取该线路下的所有剧集
            episodes = []
            episode_links = episode_list.find_all('a', class_='episode-item')

            for ep_link in episode_links:
                episode_url = ep_link.get('href', '')
                if episode_url and not episode_url.startswith('http'):
                    episode_url = 'https://www.ncat22.com' + episode_url

                episode_name = ep_link.text.strip()

                if episode_name and episode_url:
                    episodes.append({
                        'name': episode_name,
                        'url': episode_url
                    })

            if episodes:
                detail_info['routes'].append({
                    'route_name': route_name,
                    'episodes': episodes
                })

        return detail_info

    @retry_on_failure()
    def fetch_detail_page(self, detail_url: str) -> str:
        """
        获取详情页面的HTML内容
        :param detail_url: 详情页面URL
        :return: 页面HTML内容
        """
        response = self.session.get(
            detail_url,
            cookies=self.cookies,
            headers=self.headers,
            proxies=self.proxies,
            timeout=10,
            verify=False
        )
        response.encoding = 'utf-8'
        return response.text

    def parse_detail_routes(self, html: str, detail_url: str = "") -> Dict[str, Dict]:
        """
        解析详情页的线路和剧集信息
        :param html: 详情页HTML内容
        :param detail_url: 详情页URL（保持接口兼容性）
        :return: 字典 {线路名: {"total": 集数, "episodes": [(集名, 完整URL), ...]}}
        """
        detail_info = self.parse_detail_page(html)

        # 转换为与其他搜索引擎兼容的格式
        result = {}
        for route in detail_info['routes']:
            route_name = route['route_name']
            episodes = route['episodes']

            # 转换episodes格式: [{name, url}] -> [(name, url)]
            episodes_tuples = [(ep['name'], ep['url']) for ep in episodes]

            result[route_name] = {
                'total': len(episodes),
                'episodes': episodes_tuples
            }

        return result

    @staticmethod
    def parse_play_page(html_content: str) -> str:
        """
        解析播放页面,提取m3u8视频链接
        :param html_content: 播放页HTML内容
        :return: m3u8视频链接
        """
        # 方法1: 使用正则表达式提取 src: "xxx.m3u8"
        m3u8_pattern = r'src:\s*["\']([^"\']+\.m3u8[^"\']*)["\']'
        matches = re.findall(m3u8_pattern, html_content)

        if matches:
            return matches[0]

        # 方法2: 尝试查找其他可能的视频链接格式
        video_pattern = r'["\']([^"\']*(?:\.m3u8|\.mp4)[^"\']*)["\']'
        matches = re.findall(video_pattern, html_content)

        for match in matches:
            if 'http' in match and ('.m3u8' in match or '.mp4' in match):
                return match

        return None

    @retry_on_failure()
    def fetch_episode_page(self, episode_url: str) -> str:
        """
        获取剧集播放页面的HTML内容
        :param episode_url: 剧集播放页面URL
        :return: 页面HTML内容
        """
        response = self.session.get(
            episode_url,
            cookies=self.cookies,
            headers=self.headers,
            proxies=self.proxies,
            timeout=10,
            verify=False
        )
        response.encoding = 'utf-8'
        return response.text

    @retry_on_failure()
    def get_episode_play_url(self, episode_url: str) -> Tuple[str, str]:
        """
        获取剧集的实际播放URL（M3U8）
        :param episode_url: 剧集播放页面URL
        :return: (原始URL, M3U8 URL) 元组
        """
        try:
            print(f"\n正在处理剧集: {episode_url}")

            # 获取播放页面
            html = self.fetch_episode_page(episode_url)

            # 解析m3u8链接
            m3u8_url = self.parse_play_page(html)

            if m3u8_url:
                print(f" 成功提取到M3U8链接")
                return episode_url, m3u8_url
            else:
                print(f" 未能提取到M3U8链接")
                return episode_url, ""

        except Exception as e:
            print(f"获取播放URL失败: {e}")
            import traceback
            traceback.print_exc()
            return episode_url, ""

    def clear_results(self):
        """清空结果（兼容性方法）"""
        pass

    def get_result(self):
        """获取结果（兼容性方法）"""
        return {}


if __name__ == '__main__':
    """测试代码"""
    # 创建搜索器实例
    searcher = NCatSearcher()

    # 搜索视频
    keyword = input('请输入您要搜索的关键词: ')
    results = searcher.search(keyword)

    # 打印结果
    print("\n" + "=" * 60)
    print(f"搜索到 {len(results)} 个结果")
    for idx, item in enumerate(results, 1):
        print(f"{idx}. {item['title']}")
        print(f"   分类: {item['category']} | 年份: {item['year']} | 地区: {item['region']}")
        print(f"   链接: {item['detail_url']}")
        print()

