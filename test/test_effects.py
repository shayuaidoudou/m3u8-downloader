import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QAbstractAnimation
from PySide6.QtWidgets import QApplication, QPushButton

from app.effects import (
    AmbientWorkspace,
    ComposeEnergyCard,
    EmptyStateVisual,
    EnergyBorderCard,
    enable_button_shine,
)
from config import DEFAULT_CONFIG, merge_theme_tokens


class EffectWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_motion_widgets_follow_theme_and_can_be_frozen(self):
        tokens = merge_theme_tokens(1)
        widgets = [AmbientWorkspace(), ComposeEnergyCard(), EnergyBorderCard(), EmptyStateVisual()]
        for widget in widgets:
            widget.set_tokens(tokens)
            widget.show()
            self.app.processEvents()
            self.assertEqual(widget._tokens["primary"], tokens["primary"])
            self.assertEqual(widget._animation.state(), QAbstractAnimation.Running)

            widget.set_motion_enabled(False)
            self.assertEqual(widget._animation.state(), QAbstractAnimation.Stopped)

            widget.set_motion_enabled(True)
            self.assertEqual(widget._animation.state(), QAbstractAnimation.Running)
            self.assertFalse(widget.grab().isNull())
            widget.close()

    def test_button_shine_timer_obeys_effect_switch(self):
        button = QPushButton("加入下载队列")
        button.resize(220, 48)
        overlay = enable_button_shine(button, interval_ms=1800)
        button.show()
        self.app.processEvents()

        self.assertTrue(overlay._timer.isActive())
        overlay.set_enabled(False)
        self.assertFalse(overlay._timer.isActive())
        self.assertEqual(overlay._animation.state(), QAbstractAnimation.Stopped)

        overlay.set_enabled(True)
        self.assertTrue(overlay._timer.isActive())
        button.close()

    def test_effects_are_enabled_by_default(self):
        self.assertTrue(DEFAULT_CONFIG["enable_effects"])


if __name__ == "__main__":
    unittest.main()
