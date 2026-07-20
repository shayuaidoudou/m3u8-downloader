#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M3U8 下载器核心模块
支持多线程、异步下载和AES解密
"""

import os
import re
import requests
import asyncio
import aiohttp
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse, urlsplit, urlunsplit
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import threading
from typing import List, Optional, Callable, Dict, Any
import time
import subprocess
import shutil
import platform
import urllib3

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DEFAULT_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/150.0.0.0 Safari/537.36"
)

DEFAULT_REQUEST_HEADERS = {
    "User-Agent": DEFAULT_BROWSER_UA,
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


def merge_headers(base: Dict[str, str] = None, custom: Dict[str, str] = None) -> Dict[str, str]:
    """合并请求头：按不区分大小写覆盖，避免同时出现 User-Agent / user-agent。"""
    merged: Dict[str, str] = {}
    key_map: Dict[str, str] = {}  # lower -> canonical key currently in merged

    def _apply(source: Dict[str, str]):
        for raw_key, value in (source or {}).items():
            if value is None:
                continue
            key = str(raw_key).strip()
            if not key:
                continue
            lower = key.lower()
            if lower in key_map:
                del merged[key_map[lower]]
            key_map[lower] = key
            merged[key] = str(value)

    _apply(base or {})
    _apply(custom or {})
    return merged


class FFmpegMerger:
    """FFmpeg视频合并工具"""

    def __init__(self):
        self.ffmpeg_path = self._find_ffmpeg()
        self.available = self.ffmpeg_path is not None

    def _find_ffmpeg(self) -> Optional[str]:
        """查找FFmpeg可执行文件"""
        # 1. 检查项目目录下的 ffmpeg 文件夹（兼容 Windows/macOS/Linux）
        project_dir = os.path.dirname(__file__)
        project_candidates = [
            os.path.join(project_dir, 'ffmpeg', 'ffmpeg.exe'),
            os.path.join(project_dir, 'ffmpeg', 'ffmpeg'),
        ]
        for project_ffmpeg in project_candidates:
            if os.path.isfile(project_ffmpeg) and os.access(project_ffmpeg, os.X_OK):
                print(f"[DEBUG] 找到项目内置FFmpeg: {project_ffmpeg}")
                return project_ffmpeg

        # 2. 检查系统 PATH 中的 ffmpeg
        ffmpeg_in_path = shutil.which('ffmpeg')
        if ffmpeg_in_path:
            print(f"[DEBUG] PATH中找到FFmpeg: {ffmpeg_in_path}")
            return ffmpeg_in_path

        # 3. 常见安装路径
        common_paths = []
        system_name = platform.system()
        if system_name == 'Windows':
            common_paths = [
                r'C:\ffmpeg\bin\ffmpeg.exe',
                r'C:\Program Files\ffmpeg\bin\ffmpeg.exe',
                r'C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe',
            ]
        elif system_name == 'Darwin':
            common_paths = [
                '/opt/homebrew/bin/ffmpeg',
                '/usr/local/bin/ffmpeg',
                '/opt/local/bin/ffmpeg',
            ]
        else:
            common_paths = [
                '/usr/bin/ffmpeg',
                '/usr/local/bin/ffmpeg',
                '/snap/bin/ffmpeg',
            ]
        for path in common_paths:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                print(f"[DEBUG] 找到FFmpeg: {path}")
                return path

        print("[WARNING] 未找到FFmpeg，将使用备用合并方案")
        return None

    def merge_segments(self, segment_files: List[str], output_path: str) -> bool:
        """使用FFmpeg合并TS片段"""
        if not self.available:
            return False

        try:
            # 创建临时的文件列表
            concat_file = output_path + '_concat.txt'

            try:
                with open(concat_file, 'w', encoding='utf-8') as f:
                    for segment_file in sorted(segment_files):
                        # FFmpeg concat demuxer 格式
                        abs_path = os.path.abspath(segment_file)
                        f.write(f"file '{abs_path}'\n")

                print(f"[DEBUG] 创建FFmpeg文件列表: {concat_file}")

                # 构建FFmpeg命令
                cmd = [
                    self.ffmpeg_path,
                    '-f', 'concat',
                    '-safe', '0',
                    '-i', concat_file,
                    '-c', 'copy',  # 直接复制，不重新编码
                    '-y',  # 覆盖输出文件
                    output_path
                ]

                print(f"[DEBUG] 执行FFmpeg命令: {' '.join(cmd)}")

                # 执行FFmpeg (Windows下隐藏控制台窗口)
                startupinfo = None
                if platform.system() == 'Windows':
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = subprocess.SW_HIDE
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=3600,  # 1小时超时
                    startupinfo=startupinfo  # 隐藏窗口
                )

                if result.returncode != 0:
                    print(f"[ERROR] FFmpeg合并失败: {result.stderr}")
                    return False

                print(f"[DEBUG] FFmpeg合并成功: {output_path}")
                return True

            finally:
                # 清理临时文件
                if os.path.exists(concat_file):
                    try:
                        os.remove(concat_file)
                    except Exception as e:
                        print(f"[WARNING] 删除临时文件失败: {e}")

        except Exception as e:
            print(f"[ERROR] FFmpeg合并异常: {e}")
            return False


class AESDecryptor:
    """AES解密处理器"""
    
    def __init__(self, custom_headers: Dict[str, str] = None):
        self.key_cache: Dict[str, bytes] = {}
        self.headers = merge_headers(
            {"User-Agent": DEFAULT_BROWSER_UA},
            custom_headers,
        )
    
    def get_key(self, key_uri: str, headers: Dict[str, str] = None) -> bytes:
        """获取AES密钥"""
        if key_uri in self.key_cache:
            return self.key_cache[key_uri]
        
        try:
            # 优先使用传入的headers，否则使用实例的headers
            request_headers = headers or self.headers
            print(f"[DEBUG] 获取密钥: {key_uri}")
            print(f"[DEBUG] 密钥请求头: {request_headers}")
            
            # 禁用SSL证书验证以避免证书错误
            response = requests.get(key_uri, headers=request_headers, timeout=10, verify=False)
            response.raise_for_status()
            key = response.content
            self.key_cache[key_uri] = key
            print(f"[DEBUG] 密钥获取成功，长度: {len(key)} 字节")
            return key
        except Exception as e:
            print(f"[ERROR] 获取AES密钥失败: {e}")
            raise Exception(f"获取AES密钥失败: {e}")
    
    def decrypt_segment(self, encrypted_data: bytes, key: bytes, iv: bytes = None) -> bytes:
        """解密TS片段"""
        if iv is None:
            iv = b'\x00' * 16
        
        cipher = Cipher(
            algorithms.AES(key),
            modes.CBC(iv),
            backend=default_backend()
        )
        decryptor = cipher.decryptor()
        decrypted_data = decryptor.update(encrypted_data) + decryptor.finalize()
        
        # 移除PKCS7填充
        padding_length = decrypted_data[-1]
        if padding_length <= 16:
            decrypted_data = decrypted_data[:-padding_length]
        
        return decrypted_data


class M3U8Parser:
    """M3U8播放列表解析器"""
    
    def __init__(self, custom_headers: Dict[str, str] = None):
        self.base_url = ""
        self.headers = merge_headers(DEFAULT_REQUEST_HEADERS, custom_headers)
        if custom_headers:
            print(f"[DEBUG] 使用自定义请求头: {custom_headers}")
            print(f"[DEBUG] 合并后请求头: {self.headers}")
    
    def parse_m3u8(self, url: str) -> Dict[str, Any]:
        """解析M3U8文件"""
        try:
            print(f"[DEBUG] 请求M3U8文件: {url}")
            print(f"[DEBUG] 请求头: {self.headers}")

            # 禁用SSL证书验证以避免证书错误
            response = requests.get(url, headers=self.headers, timeout=15, verify=False)
            print(f"[DEBUG] 响应状态码: {response.status_code}")
            print(f"[DEBUG] 响应头: {dict(response.headers)}")
            
            response.raise_for_status()
            content = response.text
            print(f"[DEBUG] 内容长度: {len(content)} 字符")
            print(f"[DEBUG] 内容预览: {content[:500]}")
            
            if not content.strip():
                raise Exception("M3U8文件内容为空")
            
            if not content.startswith('#EXTM3U'):
                print(f"[WARNING] M3U8文件没有标准开头，内容可能不是有效的M3U8格式")
            
            # 更准确的基础URL处理
            parsed_url = urlparse(url)
            if parsed_url.path.endswith('.m3u8'):
                # 移除文件名，保留目录路径
                path_parts = parsed_url.path.rsplit('/', 1)
                base_path = path_parts[0] + '/' if len(path_parts) > 1 else '/'
                self.base_url = f"{parsed_url.scheme}://{parsed_url.netloc}{base_path}"
            else:
                self.base_url = url if url.endswith('/') else url + '/'
            print(f"[DEBUG] 基础URL: {self.base_url}")
            
            # 解析播放列表信息
            playlist_info = {
                'segments': [],
                'encryption': None,
                'total_duration': 0,
                'base_url': self.base_url
            }
            
            lines = content.strip().split('\n')
            print(f"[DEBUG] M3U8文件行数: {len(lines)}")
            
            current_segment = {}
            encryption_info = None
            
            # 检查是否是主播放列表（master playlist）
            is_master_playlist = any('#EXT-X-STREAM-INF' in line for line in lines)
            if is_master_playlist:
                print("[DEBUG] 检测到主播放列表，查找子播放列表...")
                # 找到第一个子播放列表URL
                for i, line in enumerate(lines):
                    if line.startswith('#EXT-X-STREAM-INF'):
                        if i + 1 < len(lines):
                            next_line = lines[i + 1].strip()
                            if next_line and not next_line.startswith('#'):
                                sub_m3u8_url = urljoin(self.base_url, next_line)
                                print(f"[DEBUG] 找到子播放列表: {sub_m3u8_url}")
                                # 递归解析子播放列表
                                return self.parse_m3u8(sub_m3u8_url)
                
                raise Exception("主播放列表中未找到有效的子播放列表")
            
            for line_num, line in enumerate(lines):
                line = line.strip()
                
                if line.startswith('#EXT-X-KEY:'):
                    # 解析加密信息
                    encryption_info = self._parse_key_line(line)
                    playlist_info['encryption'] = encryption_info
                    print(f"[DEBUG] 找到加密信息: {encryption_info}")
                
                elif line.startswith('#EXTINF:'):
                    # 解析段信息
                    duration_match = re.search(r'#EXTINF:([\d.]+)', line)
                    if duration_match:
                        duration = float(duration_match.group(1))
                        current_segment = {'duration': duration}
                        playlist_info['total_duration'] += duration
                
                elif line and not line.startswith('#'):
                    # TS文件URL
                    if current_segment:
                        segment_url = urljoin(self.base_url, line)
                        current_segment['url'] = segment_url
                        current_segment['index'] = len(playlist_info['segments'])
                        if encryption_info:
                            current_segment['encryption'] = encryption_info.copy()
                        
                        playlist_info['segments'].append(current_segment)
                        print(f"[DEBUG] 添加片段 {current_segment['index']}: {segment_url}")
                        current_segment = {}
                    else:
                        # 没有对应的EXTINF，可能是直接的TS文件
                        segment_url = urljoin(self.base_url, line)
                        segment_info = {
                            'url': segment_url,
                            'index': len(playlist_info['segments']),
                            'duration': 10.0  # 默认时长
                        }
                        if encryption_info:
                            segment_info['encryption'] = encryption_info.copy()
                        
                        playlist_info['segments'].append(segment_info)
                        print(f"[DEBUG] 添加片段(无EXTINF) {segment_info['index']}: {segment_url}")
            
            print(f"[DEBUG] 解析完成: {len(playlist_info['segments'])} 个片段, 总时长: {playlist_info['total_duration']:.1f}秒")
            
            if len(playlist_info['segments']) == 0:
                raise Exception("未找到任何视频片段，可能不是有效的M3U8文件")
            
            return playlist_info
            
        except requests.exceptions.RequestException as e:
            response = getattr(e, 'response', None)
            print(f"[ERROR] M3U8网络请求异常类型: {type(e).__name__}")
            print(f"[ERROR] M3U8请求失败URL: {url}")
            if response is not None:
                print(f"[ERROR] M3U8失败状态码: {response.status_code}")
                print(f"[ERROR] M3U8失败响应头: {dict(response.headers)}")
                print(f"[ERROR] M3U8失败响应预览: {response.text[:500]}")
                body = (response.text or "").lower()
                header_blob = " ".join(f"{k}:{v}" for k, v in response.headers.items()).lower()
                if response.status_code == 403 and (
                    "cloudflare" in body
                    or "attention required" in body
                    or "cf-ray" in header_blob
                    or "cloudflare" in header_blob
                ):
                    raise Exception(
                        "CDN 返回 Cloudflare 403，链接可能已过期或请求头/Cookie 不被接受。"
                        "请重新提取 M3U8，确认 Referer/Origin/User-Agent 与播放页一致，"
                        "并避免同时开太多并发任务。"
                    ) from e
            raise Exception(f"网络请求失败: {e}")
        except Exception as e:
            print(f"[ERROR] M3U8解析异常: {str(e)}")
            import traceback
            print(f"[ERROR] 详细错误: {traceback.format_exc()}")
            raise Exception(f"解析M3U8失败: {e}")
    
    def _parse_key_line(self, line: str) -> Dict[str, str]:
        """解析KEY行"""
        key_info = {}
        
        # 解析METHOD
        method_match = re.search(r'METHOD=([^,\s]+)', line)
        if method_match:
            key_info['method'] = method_match.group(1)
        
        # 解析URI
        uri_match = re.search(r'URI="([^"]+)"', line)
        if uri_match:
            key_uri = uri_match.group(1)
            key_info['uri'] = urljoin(self.base_url, key_uri)
        
        # 解析IV
        iv_match = re.search(r'IV=0x([0-9a-fA-F]+)', line)
        if iv_match:
            key_info['iv'] = bytes.fromhex(iv_match.group(1))
        
        return key_info


class ProgressCallback:
    """进度回调处理器"""
    
    def __init__(self, callback: Callable = None):
        self.callback = callback
        self.total_segments = 0
        self.completed_segments = 0
        self.failed_segments = 0
        self.start_time = time.time()
        self._lock = threading.Lock()
    
    def set_total(self, total: int):
        """设置总段数"""
        self.total_segments = total
    
    def update_progress(self, success: bool = True):
        """更新进度"""
        with self._lock:
            if success:
                self.completed_segments += 1
            else:
                self.failed_segments += 1
            
            if self.callback:
                progress_data = {
                    'completed': self.completed_segments,
                    'failed': self.failed_segments,
                    'total': self.total_segments,
                    'progress': (self.completed_segments + self.failed_segments) / self.total_segments * 100 if self.total_segments > 0 else 0,
                    'speed': self.completed_segments / (time.time() - self.start_time + 1),
                    'eta': (self.total_segments - self.completed_segments - self.failed_segments) / (self.completed_segments / (time.time() - self.start_time + 1)) if self.completed_segments > 0 else 0
                }
                self.callback(progress_data)


class M3U8Downloader:
    """M3U8 下载器"""

    def __init__(self, max_workers: int = 10, max_retries: int = 3, custom_headers: Dict[str, str] = None):
        self.max_workers = max_workers
        self.max_retries = max_retries
        self.custom_headers = custom_headers or {}

        self.parser = M3U8Parser(custom_headers)
        self.decryptor = AESDecryptor(custom_headers)
        self.ffmpeg_merger = FFmpegMerger()  # 初始化FFmpeg合并器
        self.session = requests.Session()

        # 合并自定义请求头（大小写不敏感，避免重复 UA）
        merged_headers = merge_headers(DEFAULT_REQUEST_HEADERS, custom_headers)
        if custom_headers:
            print(f"[DEBUG] 下载器使用自定义请求头: {custom_headers}")
            print(f"[DEBUG] 下载器合并后请求头: {merged_headers}")

        self.session.headers.clear()
        self.session.headers.update(merged_headers)
        self._stop_flag = threading.Event()
    
    def download(self, m3u8_url: str, output_path: str, progress_callback: Callable = None) -> bool:
        """下载M3U8视频"""
        try:
            # 重置停止标志
            self._stop_flag.clear()
            
            # 解析M3U8
            if progress_callback:
                progress_callback({'status': 'parsing', 'message': '正在解析M3U8文件...'})
            
            print(f"[DEBUG] 开始解析M3U8: {m3u8_url}")
            playlist_info = self.parser.parse_m3u8(m3u8_url)
            segments = playlist_info['segments']
            print(f"[DEBUG] 解析完成，找到 {len(segments)} 个片段")
            
            if not segments:
                raise Exception("未找到视频片段，请检查M3U8链接是否正确")
            
            # 检查加密信息
            encryption = playlist_info.get('encryption')
            if encryption:
                print(f"[DEBUG] 检测到加密: {encryption}")
                if progress_callback:
                    progress_callback({'status': 'parsing', 'message': f'检测到{encryption["method"]}加密，正在准备解密...'})
            
            # 创建输出目录
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            temp_dir = output_path + '_temp'
            os.makedirs(temp_dir, exist_ok=True)
            print(f"[DEBUG] 临时目录: {temp_dir}")
            
            # 设置进度回调
            progress = ProgressCallback(progress_callback)
            progress.set_total(len(segments))
            
            if progress_callback:
                progress_callback({'status': 'downloading', 'message': f'开始下载 {len(segments)} 个片段...'})
            
            # 多线程下载片段
            downloaded_files = self._download_segments(segments, temp_dir, encryption, progress)
            print(f"[DEBUG] 下载完成，成功下载 {len([f for f in downloaded_files if f])} 个片段")
            
            if self._stop_flag.is_set():
                print("[DEBUG] 下载被用户停止")
                return False
            
            # 检查下载结果
            successful_downloads = [f for f in downloaded_files if f]
            if len(successful_downloads) == 0:
                raise Exception("所有片段下载都失败了，请检查网络连接和链接有效性")
            elif len(successful_downloads) < len(segments) * 0.8:  # 如果超过20%的片段失败
                print(f"[WARNING] 只有 {len(successful_downloads)}/{len(segments)} 个片段下载成功")
                if progress_callback:
                    progress_callback({'status': 'warning', 'message': f'警告: 只下载了 {len(successful_downloads)}/{len(segments)} 个片段'})
            
            # 合并片段
            if progress_callback:
                progress_callback({'status': 'merging', 'message': '正在合并视频片段...'})
            
            self._merge_segments(successful_downloads, output_path)
            print(f"[DEBUG] 视频合并完成: {output_path}")
            
            # 清理临时文件
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            
            if progress_callback:
                progress_callback({'status': 'completed', 'message': '下载完成！'})
            
            return True
            
        except Exception as e:
            print(f"[ERROR] 下载失败: {str(e)}")
            import traceback
            print(f"[ERROR] 详细错误: {traceback.format_exc()}")
            if progress_callback:
                progress_callback({'status': 'error', 'message': f'下载失败: {str(e)}'})
            return False
    
    def _download_segments(self, segments: List[Dict], temp_dir: str, encryption: Dict = None, progress: ProgressCallback = None) -> List[str]:
        """多线程下载片段"""
        downloaded_files = [''] * len(segments)
        executor = ThreadPoolExecutor(max_workers=self.max_workers)
        future_to_index = {}
        try:
            for i, segment in enumerate(segments):
                if self._stop_flag.is_set():
                    break
                future = executor.submit(self._download_segment, segment, temp_dir, encryption)
                future_to_index[future] = i

            for future in as_completed(future_to_index):
                if self._stop_flag.is_set():
                    break

                index = future_to_index[future]
                try:
                    file_path = future.result()
                    if file_path:
                        downloaded_files[index] = file_path
                        if progress:
                            progress.update_progress(True)
                    else:
                        if progress:
                            progress.update_progress(False)
                except Exception as e:
                    print(f"[ERROR] 片段任务 {index} 执行异常: {type(e).__name__}: {e}")
                    if progress:
                        progress.update_progress(False)
        finally:
            # 停止时取消未开始任务并尽快返回，避免退出阶段卡在线程池
            stopped = self._stop_flag.is_set()
            for pending in future_to_index:
                if not pending.done():
                    pending.cancel()
            executor.shutdown(wait=not stopped, cancel_futures=True)

        return [f for f in downloaded_files if f]
    
    def _download_segment(self, segment: Dict, temp_dir: str, encryption: Dict = None) -> Optional[str]:
        """下载单个片段"""
        url = segment['url']
        index = segment['index']
        file_path = os.path.join(temp_dir, f'segment_{index:06d}.ts')
        
        for attempt in range(self.max_retries):
            if self._stop_flag.is_set():
                return None
                
            try:
                if attempt == 0:
                    print(f"[DEBUG] 开始下载片段 {index}: {url}")
                
                # 禁用SSL证书验证以避免证书错误
                response = self.session.get(url, timeout=30, verify=False)
                response.raise_for_status()
                
                data = response.content
                print(f"[DEBUG] 片段 {index} 下载完成，大小: {len(data)} 字节")
                
                if len(data) == 0:
                    raise Exception("片段数据为空")
                
                # AES解密处理
                if encryption and encryption.get('method') == 'AES-128':
                    print(f"[DEBUG] 对片段 {index} 进行AES解密")
                    try:
                        # 传递session的headers给解密器
                        key = self.decryptor.get_key(encryption['uri'], dict(self.session.headers))
                        iv = encryption.get('iv', bytes.fromhex(f'{index:032x}'))
                        data = self.decryptor.decrypt_segment(data, key, iv)
                        print(f"[DEBUG] 片段 {index} 解密成功，解密后大小: {len(data)} 字节")
                    except Exception as decrypt_error:
                        print(f"[ERROR] 片段 {index} 解密失败: {decrypt_error}")
                        raise decrypt_error
                
                # 写入文件
                with open(file_path, 'wb') as f:
                    f.write(data)
                
                print(f"[DEBUG] 片段 {index} 保存成功: {file_path}")
                return file_path
                
            except Exception as e:
                response = getattr(e, 'response', None)
                print(f"[ERROR] 下载片段 {index} 失败 (尝试 {attempt + 1}/{self.max_retries}): {type(e).__name__}: {e}")
                print(f"[ERROR] 片段 {index} URL: {url}")
                if response is not None:
                    print(f"[ERROR] 片段 {index} 状态码: {response.status_code}")
                    print(f"[ERROR] 片段 {index} 响应头: {dict(response.headers)}")
                    print(f"[ERROR] 片段 {index} 响应预览: {response.text[:300]}")
                if attempt == self.max_retries - 1:
                    print(f"[ERROR] 片段 {index} 最终下载失败: {e}")
                    return None
                
                # 等待后重试
                wait_time = min(2 ** attempt, 10)  # 指数退避，最多等10秒
                print(f"[DEBUG] 等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
        
        return None
    
    def _merge_segments(self, segment_files: List[str], output_path: str):
        """合并视频片段 - 优先使用FFmpeg，备用简单合并"""
        print(f"[DEBUG] 开始合并 {len(segment_files)} 个片段到 {output_path}")

        # 尝试使用FFmpeg合并
        if self.ffmpeg_merger.available:
            print("[DEBUG] 使用FFmpeg进行合并...")
            if self.ffmpeg_merger.merge_segments(segment_files, output_path):
                print("[DEBUG] FFmpeg合并成功")
                return
            else:
                print("[WARNING] FFmpeg合并失败，尝试备用方案...")
        else:
            print("[INFO] FFmpeg不可用，使用备用合并方案")

        # 备用方案：智能TS合并（跳过冗余的PAT/PMT）
        self._merge_segments_fallback(segment_files, output_path)

    def _merge_segments_fallback(self, segment_files: List[str], output_path: str):
        """备用合并方案 - 智能TS合并，处理PAT/PMT冗余"""
        TS_PACKET_SIZE = 188

        with open(output_path, 'wb') as output_file:
            for idx, segment_file in enumerate(sorted(segment_files)):
                if not os.path.exists(segment_file):
                    continue

                with open(segment_file, 'rb') as f:
                    data = f.read()

                if idx == 0:
                    # 第一个片段完整保留（包含PAT/PMT）
                    output_file.write(data)
                    print(f"[DEBUG] 片段 {idx}: 完整写入 {len(data)} 字节")
                else:
                    # 后续片段：跳过前面的PAT/PMT包（通常前10个包）
                    skip_packets = 10
                    skip_bytes = skip_packets * TS_PACKET_SIZE

                    if len(data) > skip_bytes:
                        output_file.write(data[skip_bytes:])
                        print(f"[DEBUG] 片段 {idx}: 跳过 {skip_bytes} 字节，写入 {len(data) - skip_bytes} 字节")
                    else:
                        output_file.write(data)
                        print(f"[DEBUG] 片段 {idx}: 数据过小，完整写入 {len(data)} 字节")

        print(f"[DEBUG] 备用合并完成: {output_path}")
    
    def stop_download(self):
        """停止下载"""
        self._stop_flag.set()


if __name__ == "__main__":
    # 测试代码
    def progress_callback(data):
        if 'progress' in data:
            print(f"进度: {data['progress']:.1f}% ({data['completed']}/{data['total']})")
        elif 'message' in data:
            print(data['message'])
    
    downloader = M3U8Downloader(max_workers=16)
    # 这里需要真实的m3u8 URL进行测试
    # success = downloader.download("your_m3u8_url_here", "output_video.mp4", progress_callback)
