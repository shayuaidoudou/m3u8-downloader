"""
-*- coding: utf-8 -*-
@File   : search_mofa.py
@author : @鲨鱼爱兜兜
@Time   : 2025/12/12
@Desc   : 魔法影视搜索引擎
"""

import time
import requests
from typing import List, Dict, Tuple
from functools import wraps


def retry_on_failure(max_retries: int = 3, delay: float = 2.0, backoff: float = 2.0):
    """
    装饰器：失败时自动重试
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
                        print(f"⚠️  请求失败 ({error_type}): {error_msg[:100]}...")
                        print(f"   第 {retries}/{max_retries} 次重试，等待 {current_delay} 秒...")
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        print(f"❌ 达到最大重试次数 ({max_retries})，请求失败")
                        print(f"   最后错误: {error_msg[:200]}")
                        raise

            return None
        return wrapper
    return decorator


class MofaSearcher:
    """魔法影视搜索引擎类"""
    
    def __init__(self, base_url: str = "https://movie.mofaxi.cn", proxy_config: dict = None):
        """
        初始化魔法影视搜索器
        :param base_url: 基础URL
        :param proxy_config: 代理配置
        """
        self.base_url = base_url
        self.api_url = f"{base_url}/api/search"
        self.default_api = "https://bf.xoxowin86cisyap.com/api.php/provide/vod/"
        self.session = requests.Session()
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
            print(f"✓ 已配置代理: {proxy_url}")
    
    def _init_headers(self) -> dict:
        """初始化请求头"""
        return {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'cache-control': 'no-cache',
            'content-type': 'application/json',
            'origin': self.base_url,
            'pragma': 'no-cache',
            'priority': 'u=1, i',
            'referer': f'{self.base_url}/',
            'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
        }

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

            json_data = {
                'api': self.default_api,
                'keyword': keyword,
            }

            response = self.session.post(
                self.api_url,
                headers=self.headers,
                json=json_data,
                proxies=self.proxies,
                timeout=15,
                verify=False
            )
            response.encoding = 'utf-8'
            
            result = response.json()
            
            if not result.get('success'):
                print(f"❌ 搜索失败: {result.get('message', '未知错误')}")
                return []
            
            data = result.get('data', [])
            
            # 转换为统一格式
            results = []
            for item in data:
                result_data = {
                    'vod_id': item.get('vod_id', ''),
                    'title': item.get('vod_name', ''),
                    'sub_title': item.get('vod_sub', ''),
                    'category': item.get('type_name', ''),
                    'year': item.get('vod_year', ''),
                    'region': item.get('vod_area', ''),
                    'genre': item.get('vod_class', ''),
                    'actors': item.get('vod_actor', ''),
                    'director': item.get('vod_director', ''),
                    'description': item.get('vod_content', ''),
                    'cover_url': item.get('vod_pic', ''),
                    'remarks': item.get('vod_remarks', ''),
                    'score': item.get('vod_score', ''),
                    'play_from': item.get('vod_play_from', ''),
                    'play_url': item.get('vod_play_url', ''),  # 直接包含播放链接
                    'total': item.get('vod_total', 0),
                }
                results.append(result_data)

            if verbose:
                print(f"✓ 搜索到 {len(results)} 个结果\n")

            return results

        except Exception as e:
            print(f"搜索失败: {e}")
            import traceback
            traceback.print_exc()
            return []

    def parse_play_urls(self, play_url_str: str) -> List[Tuple[str, str]]:
        """
        解析播放URL字符串
        :param play_url_str: 格式如 "第01集$url1#第02集$url2#..."
        :return: [(集名, URL), ...]
        """
        episodes = []
        if not play_url_str:
            return episodes
        
        # 按#分割每一集
        parts = play_url_str.split('#')
        for part in parts:
            if '$' in part:
                name, url = part.split('$', 1)
                episodes.append((name.strip(), url.strip()))
        
        return episodes

    def parse_detail_routes(self, item: Dict) -> Dict[str, Dict]:
        """
        解析详情页的线路和剧集信息（魔法影视搜索结果直接包含播放链接）
        :param item: 搜索结果中的单个影片数据
        :return: 字典 {线路名: {"total": 集数, "episodes": [(集名, URL), ...]}}
        """
        result = {}
        
        play_from = item.get('play_from', 'default')
        play_url = item.get('play_url', '')
        
        if play_url:
            episodes = self.parse_play_urls(play_url)
            if episodes:
                result[play_from] = {
                    'total': len(episodes),
                    'episodes': episodes
                }
        
        return result

    def get_episode_play_url(self, episode_url: str) -> Tuple[str, str]:
        """
        获取剧集的实际播放URL（魔法影视直接返回m3u8链接，无需额外解析）
        :param episode_url: 剧集播放URL
        :return: (原始URL, M3U8 URL) 元组
        """
        # 魔法影视的播放链接已经是m3u8格式，直接返回
        return episode_url, episode_url

    def clear_results(self):
        """清空结果（兼容性方法）"""
        pass

    def get_result(self):
        """获取结果（兼容性方法）"""
        return {}


if __name__ == '__main__':
    """测试代码"""
    # 创建搜索器实例
    searcher = MofaSearcher()

    # 搜索视频
    keyword = input('请输入您要搜索的关键词: ')
    results = searcher.search(keyword)

    # 打印结果
    print("\n" + "=" * 60)
    print(f"搜索到 {len(results)} 个结果")
    for idx, item in enumerate(results, 1):
        print(f"{idx}. {item['title']}")
        print(f"   分类: {item['category']} | 年份: {item['year']} | 地区: {item['region']}")
        print(f"   备注: {item['remarks']} | 评分: {item['score']}")
        
        # 解析播放链接
        routes = searcher.parse_detail_routes(item)
        for route_name, route_info in routes.items():
            print(f"   线路: {route_name} | 共 {route_info['total']} 集")
        print()
