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
    'theme_color': 0,               # 默认主题索引：电青（暗色工作台）
    'enable_effects': True,         # 粒子、轨道、流光等动态视觉特效

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

# 全局圆角
RADIUS = 14
RADIUS_CONTROL = 10

# 曜石深空 + 熔金强调：底色压得更深、表面分三层，金色带渐变与辉光
UI_TOKENS = {
    'primary': '#F2C94C',
    'primary_hover': '#FFDD70',
    'primary_active': '#D4A72C',
    'primary_soft': '#2B2410',
    'bg': '#070B16',
    'surface': '#0F1528',
    'surface_alt': '#171F36',
    'surface_hover': '#212C4A',
    'text': '#F4F6FB',
    'text_muted': '#9AA5BF',
    'text_subtle': '#5F6B88',
    'border': '#222C47',
    'border_strong': '#37436A',
    'border_focus': '#F2C94C',
    'success': '#3DDC97',
    'warning': '#F0A030',
    'danger': '#F07178',
    'radius': RADIUS,
    'radius_card': RADIUS,
    'radius_control': RADIUS_CONTROL,
    'radius_tag': RADIUS_CONTROL,
    'radius_progress': 3,
    'is_dark': True,
}

# 主界面可选主题。顺序与偏好设置中的下拉框保持一致。索引 0 = 默认。
THEME_NAMES = (
    '深空金',
    '经典蓝',
    '粉红',
    '翠绿',
    '琥珀',
    '紫罗兰',
    '绯红',
    '靛紫',
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
    0: _dark_theme(                                    # 曜石金（默认）
        '#F2C94C', '#FFDD70', '#D4A72C',
        '#070B16', '#0F1528', '#F4F6FB', '#222C47',
    ),
    1: _light_theme('#4F46E5', '#4338CA', '#6366F1'),   # 经典蓝 Indigo
    2: _light_theme('#DB2777', '#BE185D', '#EC4899'),   # 粉红
    3: _light_theme('#059669', '#047857', '#10B981'),   # 翠绿
    4: _light_theme('#D97706', '#B45309', '#F59E0B'),   # 琥珀
    5: _light_theme('#7C3AED', '#6D28D9', '#8B5CF6'),   # 紫罗兰
    6: _light_theme('#DC2626', '#B91C1C', '#EF4444'),   # 绯红
    7: _light_theme('#6366F1', '#4F46E5', '#A5B4FC'),   # 靛紫
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


def _hex_to_rgb(hex_color):
    value = hex_color.lstrip('#')
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _mix_hex(hex_color, other, ratio):
    """按 ratio 混合 two hex；ratio=0 偏向 hex_color，1 偏向 other。"""
    r1, g1, b1 = _hex_to_rgb(hex_color)
    r2, g2, b2 = _hex_to_rgb(other)
    r = int(r1 + (r2 - r1) * ratio)
    g = int(g1 + (g2 - g1) * ratio)
    b = int(b1 + (b2 - b1) * ratio)
    return f'#{r:02X}{g:02X}{b:02X}'


def merge_theme_tokens(theme_index, base=None):
    """把主题强调色/亮暗表面合并进 UI_TOKENS，供 stylesheet 一次生成。"""
    tokens = dict(base or UI_TOKENS)
    theme = get_theme(theme_index)

    primary = theme.get('primary', tokens['primary'])
    secondary = theme.get('secondary', tokens['primary_hover'])
    accent = theme.get('accent', tokens['primary_active'])
    is_dark = bool(theme.get('is_dark', False))

    tokens['primary'] = primary
    tokens['primary_hover'] = secondary
    tokens['primary_active'] = accent
    tokens['border_focus'] = _mix_hex(primary, '#FFFFFF', 0.55)

    if is_dark:
        bg = theme.get('bg_start', '#0E1116')
        surface = theme.get('groupbox_bg', '#151A21')
        text = theme.get('text_color', '#F0F3F6')
        border = theme.get('input_border', '#2A313C')
        tokens['primary_soft'] = _mix_hex(primary, bg, 0.88)
        tokens.update({
            'bg': bg,
            'surface': surface,
            'surface_alt': _mix_hex(surface, '#000000', 0.18),
            'surface_hover': _mix_hex(surface, '#FFFFFF', 0.08),
            'text': text,
            'text_muted': _mix_hex(text, bg, 0.35),
            'text_subtle': _mix_hex(text, bg, 0.50),
            'border': border,
            'border_strong': _mix_hex(border, '#FFFFFF', 0.12),
        })
    else:
        tokens['primary_soft'] = _mix_hex(primary, '#FFFFFF', 0.88)
        tokens.update({
            'bg': theme.get('bg_start', tokens['bg']),
            'surface': theme.get('groupbox_bg', tokens['surface']),
            'surface_alt': '#F5F5F5',
            'surface_hover': '#F0F0F0',
            'text': theme.get('text_color', tokens['text']),
            'text_muted': '#6B7280',
            'text_subtle': '#9CA3AF',
            'border': theme.get('input_border', tokens['border']),
            'border_strong': '#D1D5DB',
        })

    tokens['radius'] = RADIUS
    tokens['radius_card'] = RADIUS
    tokens['radius_control'] = RADIUS_CONTROL
    tokens['radius_tag'] = RADIUS_CONTROL
    tokens['radius_progress'] = 3
    tokens['is_dark'] = is_dark
    return tokens


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
