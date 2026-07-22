import unittest

from config import (
    THEMES,
    THEME_NAMES,
    UI_TOKENS,
    get_theme,
    get_theme_name,
    merge_theme_tokens,
)
from theme import build_stylesheet


REQUIRED_THEME_FIELDS = {
    'primary',
    'secondary',
    'accent',
    'bg_start',
    'bg_mid',
    'bg_end',
    'text_color',
    'input_bg',
    'input_border',
    'groupbox_bg',
    'is_dark',
}


class ThemeConfigTests(unittest.TestCase):
    def test_theme_names_and_registry_are_aligned(self):
        self.assertEqual(len(THEMES), len(THEME_NAMES))
        self.assertEqual(set(THEMES), set(range(len(THEME_NAMES))))

    def test_every_theme_has_all_required_fields(self):
        for theme_index, theme in THEMES.items():
            with self.subTest(theme_index=theme_index):
                self.assertEqual(set(theme), REQUIRED_THEME_FIELDS)
                self.assertIsInstance(theme['is_dark'], bool)

    def test_get_theme_falls_back_and_returns_a_copy(self):
        original_primary = THEMES[0]['primary']
        fallback = get_theme(999)
        self.assertEqual(fallback, THEMES[0])

        fallback['primary'] = '#000000'
        self.assertEqual(THEMES[0]['primary'], original_primary)

    def test_get_theme_name_handles_unknown_index(self):
        self.assertEqual(get_theme_name(0), THEME_NAMES[0])
        self.assertEqual(get_theme_name(999), '未知主题 (999)')

    def test_merge_theme_tokens_unifies_radius_and_primary(self):
        light_index = next(index for index, theme in THEMES.items() if not theme['is_dark'])
        dark_index = next(index for index, theme in THEMES.items() if theme['is_dark'])

        tokens = merge_theme_tokens(light_index)
        self.assertEqual(tokens['radius'], UI_TOKENS['radius'])
        self.assertEqual(tokens['radius_card'], tokens['radius'])
        self.assertEqual(tokens['primary'], THEMES[light_index]['primary'])
        self.assertFalse(tokens['is_dark'])

        dark = merge_theme_tokens(dark_index)
        self.assertTrue(dark['is_dark'])
        self.assertEqual(dark['primary'], THEMES[dark_index]['primary'])
        self.assertNotEqual(dark['bg'], tokens['bg'])

    def test_build_stylesheet_contains_interaction_states(self):
        qss = build_stylesheet(merge_theme_tokens(0))
        self.assertTrue(qss)
        for needle in (
            'QPushButton:hover',
            'QPushButton:pressed',
            'QPushButton:disabled',
            'QLineEdit:focus',
            'border-radius:',
        ):
            self.assertIn(needle, qss)


if __name__ == '__main__':
    unittest.main()
