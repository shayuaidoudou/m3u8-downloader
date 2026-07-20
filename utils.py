#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M3U8 下载器工具函数
"""

import os
import re
from urllib.parse import urlparse
from pathlib import Path


def is_valid_url(url: str) -> bool:
    """验证URL是否有效"""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False


def is_valid_m3u8_url(url: str) -> bool:
    """验证是否为有效的M3U8 URL"""
    if not is_valid_url(url):
        return False
    return url.lower().endswith('.m3u8') or 'm3u8' in url.lower()


def sanitize_filename(filename: str) -> str:
    """清理文件名，移除不安全字符"""
    # 移除Windows文件名中的非法字符
    illegal_chars = r'[<>:"/\\|?*]'
    sanitized = re.sub(illegal_chars, '_', filename)
    
    # 移除开头和结尾的空格和点
    sanitized = sanitized.strip('. ')
    
    # 限制长度
    if len(sanitized) > 200:
        sanitized = sanitized[:200]
    
    return sanitized


def ensure_extension(filepath: str, default_ext: str = '.mp4') -> str:
    """确保文件有正确的扩展名"""
    path = Path(filepath)
    if not path.suffix:
        return str(path.with_suffix(default_ext))
    return filepath


def format_size(size_bytes: int) -> str:
    """格式化文件大小"""
    if size_bytes == 0:
        return "0B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    
    return f"{size_bytes:.1f}{size_names[i]}"


def format_time(seconds: float) -> str:
    """格式化时间"""
    if seconds < 60:
        return f"{seconds:.0f}秒"
    elif seconds < 3600:
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes:.0f}分{secs:.0f}秒"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours:.0f}小时{minutes:.0f}分"


def create_temp_dir(base_path: str) -> str:
    """创建临时目录"""
    temp_dir = base_path + '_temp'
    os.makedirs(temp_dir, exist_ok=True)
    return temp_dir


def cleanup_temp_dir(temp_dir: str):
    """清理临时目录"""
    import shutil
    if os.path.exists(temp_dir):
        try:
            shutil.rmtree(temp_dir)
        except Exception as e:
            print(f"清理临时目录失败: {e}")


def get_available_filename(filepath: str) -> str:
    """获取可用的文件名（避免重复）"""
    if not os.path.exists(filepath):
        return filepath
    
    path = Path(filepath)
    base = path.stem
    suffix = path.suffix
    parent = path.parent
    
    counter = 1
    while True:
        new_name = f"{base}_{counter}{suffix}"
        new_path = parent / new_name
        if not os.path.exists(new_path):
            return str(new_path)
        counter += 1


def validate_output_path(filepath: str) -> tuple[bool, str]:
    """验证输出路径是否有效"""
    try:
        path = Path(filepath)
        
        # 检查父目录是否存在或可创建
        parent_dir = path.parent
        if not parent_dir.exists():
            try:
                parent_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                return False, f"无法创建目录: {e}"
        
        # 检查是否有写入权限
        if parent_dir.exists() and not os.access(parent_dir, os.W_OK):
            return False, "没有写入权限"
        
        # 检查文件名是否合法
        if not path.name or path.name == '.':
            return False, "文件名无效"
        
        return True, ""
        
    except Exception as e:
        return False, f"路径验证失败: {e}"


def extract_title_from_url(url: str) -> str:
    """从URL中提取可能的标题"""
    try:
        parsed = urlparse(url)
        path = parsed.path
        
        # 提取最后一个路径段作为可能的标题
        if path and path != '/':
            segments = path.strip('/').split('/')
            last_segment = segments[-1]
            
            # 移除扩展名
            if '.' in last_segment:
                title = last_segment.rsplit('.', 1)[0]
            else:
                title = last_segment
            
            # 清理标题
            title = sanitize_filename(title)
            if title:
                return title
        
        # 使用域名作为后备
        domain = parsed.netloc
        if domain:
            return sanitize_filename(domain.replace('.', '_'))
        
        return "未知视频"
        
    except Exception:
        return "未知视频"
