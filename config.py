#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M3U8下载器配置文件
"""

# 默认配置
DEFAULT_CONFIG = {
    # 下载设置
    'max_workers': 16,              # 默认线程数
    'max_retries': 3,               # 最大重试次数
    'timeout': 30,                  # 请求超时时间（秒）
    'chunk_size': 8192,             # 下载块大小
    
    # UI设置
    'window_width': 1200,           # 窗口默认宽度
    'window_height': 900,           # 窗口默认高度
    'theme': 'modern',              # 界面主题
    
    # 网络设置
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'headers': {
        'Accept': '*/*',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
    },
    
    # 文件设置
    'temp_dir_suffix': '_temp',     # 临时目录后缀
    'segment_name_format': 'segment_{index:06d}.ts',  # 片段文件命名格式
    
    # 高级设置
    'enable_proxy': False,          # 是否启用代理
    'proxy_url': '',               # 代理地址
    'enable_logging': True,        # 是否启用日志
    'log_level': 'INFO',           # 日志级别
}

# 现代极简设计 token（亮色默认；暗色主题由 THEMES 覆盖表面色）
UI_TOKENS = {
    'primary': '#4F46E5',
    'primary_hover': '#4338CA',
    'primary_active': '#3730A3',
    'primary_soft': '#EEF2FF',
    'bg': '#FAFAFA',
    'surface': '#FFFFFF',
    'surface_alt': '#F5F5F5',
    'surface_hover': '#F0F0F0',
    'text': '#111827',
    'text_muted': '#6B7280',
    'text_subtle': '#9CA3AF',
    'border': '#E5E7EB',
    'border_strong': '#D1D5DB',
    'border_focus': '#C7D2FE',
    'success': '#059669',
    'warning': '#D97706',
    'danger': '#DC2626',
    'radius_card': 12,
    'radius_control': 8,
    'radius_tag': 6,
    'radius_progress': 3,
}

# 主界面可选主题。顺序与偏好设置中的下拉框保持一致。
THEME_NAMES = (
    '经典蓝',
    '粉红',
    '翠绿',
    '琥珀',
    '紫罗兰',
    '绯红',
    '靛紫',
    '深海',
    '极光',
    '日落',
    '星空',
    '雨林',
    '薰衣草',
    '霓虹',
)

# 亮色主题共用表面色
_LIGHT_SURFACE = {
    'bg_start': '#F8FAFC',
    'bg_mid': '#F8FAFC',
    'bg_end': '#F8FAFC',
    'text_color': '#0F172A',
    'input_bg': '#FFFFFF',
    'input_border': '#E2E8F0',
    'groupbox_bg': '#FFFFFF',
    'is_dark': False,
}


def _light_theme(primary, secondary, accent):
    theme = {
        'primary': primary,
        'secondary': secondary,
        'accent': accent,
    }
    theme.update(_LIGHT_SURFACE)
    return theme


def _dark_theme(primary, secondary, accent, bg, surface, text, border):
    return {
        'primary': primary,
        'secondary': secondary,
        'accent': accent,
        'bg_start': bg,
        'bg_mid': bg,
        'bg_end': bg,
        'text_color': text,
        'input_bg': surface,
        'input_border': border,
        'groupbox_bg': surface,
        'is_dark': True,
    }


THEMES = {
    0: _light_theme('#4F46E5', '#4338CA', '#6366F1'),   # 经典蓝 Indigo
    1: _light_theme('#DB2777', '#BE185D', '#EC4899'),   # 粉红
    2: _light_theme('#059669', '#047857', '#10B981'),   # 翠绿
    3: _light_theme('#D97706', '#B45309', '#F59E0B'),   # 琥珀
    4: _light_theme('#7C3AED', '#6D28D9', '#8B5CF6'),   # 紫罗兰
    5: _light_theme('#DC2626', '#B91C1C', '#EF4444'),   # 绯红
    6: _light_theme('#7C3AED', '#6D28D9', '#A78BFA'),   # 靛紫
    7: _dark_theme(                                    # 深海
        '#22D3EE', '#06B6D4', '#67E8F9',
        '#0F172A', '#1E293B', '#E2E8F0', '#334155',
    ),
    8: _dark_theme(                                    # 极光
        '#818CF8', '#6366F1', '#A5B4FC',
        '#0F172A', '#1E1B4B', '#E0E7FF', '#312E81',
    ),
    9: _light_theme('#EA580C', '#C2410C', '#FB923C'),   # 日落
    10: _dark_theme(                                   # 星空
        '#818CF8', '#6366F1', '#C4B5FD',
        '#0F172A', '#1E293B', '#E2E8F0', '#334155',
    ),
    11: _dark_theme(                                   # 雨林
        '#34D399', '#10B981', '#6EE7B7',
        '#022C22', '#064E3B', '#D1FAE5', '#065F46',
    ),
    12: _light_theme('#9333EA', '#7E22CE', '#C084FC'),  # 薰衣草
    13: _dark_theme(                                   # 霓虹
        '#F472B6', '#EC4899', '#22D3EE',
        '#18181B', '#27272A', '#F4F4F5', '#3F3F46',
    ),
}


def get_theme(theme_index):
    """返回指定主题的独立副本，无效索引回退到经典蓝。"""
    return THEMES.get(theme_index, THEMES[0]).copy()


def get_theme_name(theme_index):
    """返回用于状态和日志显示的主题名称。"""
    if 0 <= theme_index < len(THEME_NAMES):
        return THEME_NAMES[theme_index]
    return f'未知主题 ({theme_index})'

# 支持的视频格式
SUPPORTED_FORMATS = [
    '.mp4', '.ts', '.m4v', '.mkv', '.avi', '.mov'
]

# 错误消息
ERROR_MESSAGES = {
    'invalid_url': '无效的M3U8链接',
    'network_error': '网络连接错误',
    'parse_error': '解析M3U8文件失败',
    'download_error': '下载失败',
    'decrypt_error': 'AES解密失败',
    'file_error': '文件操作失败',
}

# 状态消息
STATUS_MESSAGES = {
    'ready': '准备就绪',
    'parsing': '正在解析M3U8文件...',
    'downloading': '正在下载...',
    'merging': '正在合并视频片段...',
    'completed': '下载完成！',
    'failed': '下载失败',
    'stopped': '已停止',
}
