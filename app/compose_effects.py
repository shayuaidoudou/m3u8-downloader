"""Animated aurora surface for the left-side download composition panel."""

from __future__ import annotations

import math

from PySide6.QtCore import Property, QEasingCurve, QPointF, QPropertyAnimation, Qt
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QFrame

from config import UI_TOKENS


def _alpha(color, value):
    result = QColor(color)
    result.setAlpha(max(0, min(255, int(value))))
    return result


class ComposeEnergyCard(QFrame):
    """A theme-aware background with slow, organic light movement."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._phase = 0.0
        self._motion_enabled = True
        self._tokens = dict(UI_TOKENS)

        self._animation = QPropertyAnimation(self, b"phase", self)
        self._animation.setDuration(8200)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setLoopCount(-1)
        self._animation.setEasingCurve(QEasingCurve.Linear)

    def set_tokens(self, tokens):
        self._tokens = dict(tokens or UI_TOKENS)
        self.update()

    def _get_phase(self):
        return self._phase

    def _set_phase(self, value):
        self._phase = float(value)
        self.update()

    phase = Property(float, _get_phase, _set_phase)

    def set_motion_enabled(self, enabled):
        self._motion_enabled = bool(enabled)
        if self._motion_enabled and self.isVisible():
            self.start_animation()
        else:
            self.stop_animation()
            self.update()

    def start_animation(self):
        if self._motion_enabled and self._animation.state() != QPropertyAnimation.Running:
            self._animation.start()

    def stop_animation(self):
        self._animation.stop()

    def showEvent(self, event):
        super().showEvent(event)
        self.start_animation()

    def hideEvent(self, event):
        self.stop_animation()
        super().hideEvent(event)

    def _primary(self):
        return QColor(self._tokens.get("primary", UI_TOKENS["primary"]))

    @staticmethod
    def _paint_elliptical_glow(painter, geometry, color, strength):
        center, radius, x_scale, y_scale = geometry
        painter.save()
        painter.translate(center)
        painter.scale(x_scale, y_scale)
        glow = QRadialGradient(QPointF(0.0, 0.0), radius)
        glow.setColorAt(0.0, _alpha(color, strength))
        glow.setColorAt(0.42, _alpha(color, strength * 0.48))
        glow.setColorAt(0.78, _alpha(color, strength * 0.12))
        glow.setColorAt(1.0, _alpha(color, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(glow))
        painter.drawEllipse(QPointF(0.0, 0.0), radius, radius)
        painter.restore()

    def _paint_aurora_fog(self, painter, primary, is_dark):
        width, height = self.width(), self.height()
        angle = self._phase * math.tau
        base = 42 if is_dark else 26

        self._paint_elliptical_glow(
            painter,
            (
                QPointF(
                    width * (0.20 + 0.05 * math.sin(angle)),
                    height * (0.74 + 0.035 * math.cos(angle * 0.82)),
                ),
                190.0,
                1.18,
                0.72,
            ),
            primary,
            base,
        )
        self._paint_elliptical_glow(
            painter,
            (
                QPointF(
                    width * (0.82 + 0.04 * math.cos(angle * 0.74)),
                    height * (0.61 + 0.045 * math.sin(angle * 0.66)),
                ),
                150.0,
                0.86,
                1.14,
            ),
            primary.lighter(118),
            base * 0.72,
        )

    def _silk_path(self, index):
        width, height = self.width(), self.height()
        angle = self._phase * math.tau
        drift = math.sin(angle + index * 1.7) * 18.0
        lift = math.cos(angle * 0.72 + index) * 12.0

        path = QPainterPath()
        if index == 0:
            path.moveTo(-50.0, height * 0.80 + drift)
            path.cubicTo(
                width * 0.16, height * 0.57 + lift,
                width * 0.49, height * 0.86 - drift,
                width * 0.70, height * 0.66 + lift,
            )
            path.cubicTo(
                width * 0.84, height * 0.54 - drift,
                width * 0.94, height * 0.58 + lift,
                width + 50.0, height * 0.50 - drift,
            )
        else:
            path.moveTo(-40.0, height * 0.62 - drift)
            path.cubicTo(
                width * 0.22, height * 0.77 - lift,
                width * 0.46, height * 0.48 + drift,
                width * 0.66, height * 0.70 - lift,
            )
            path.cubicTo(
                width * 0.80, height * 0.84 + drift,
                width * 0.92, height * 0.69 - lift,
                width + 40.0, height * 0.76 + drift,
            )
        return path

    @staticmethod
    def _ribbon_gradient(width, primary, alpha):
        gradient = QLinearGradient(0.0, 0.0, width, 0.0)
        gradient.setColorAt(0.0, _alpha(primary, 0))
        gradient.setColorAt(0.18, _alpha(primary, alpha * 0.34))
        gradient.setColorAt(0.46, _alpha(primary.lighter(122), alpha))
        gradient.setColorAt(0.68, _alpha(QColor("#FFFFFF"), alpha * 0.52))
        gradient.setColorAt(0.86, _alpha(primary, alpha * 0.26))
        gradient.setColorAt(1.0, _alpha(primary, 0))
        return gradient

    def _paint_silk_ribbons(self, painter, primary, is_dark):
        width = self.width()
        for index in range(2):
            path = self._silk_path(index)
            strength = (30 if is_dark else 19) * (1.0 - index * 0.28)
            brush = QBrush(self._ribbon_gradient(width, primary, strength))

            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(brush, 48.0 - index * 10.0, Qt.SolidLine, Qt.RoundCap))
            painter.drawPath(path)

            inner = QBrush(self._ribbon_gradient(width, primary, strength * 1.35))
            painter.setPen(QPen(inner, 12.0, Qt.SolidLine, Qt.RoundCap))
            painter.drawPath(path)

            highlight = QBrush(self._ribbon_gradient(width, primary, strength * 1.9))
            painter.setPen(QPen(highlight, 1.2, Qt.SolidLine, Qt.RoundCap))
            painter.drawPath(path)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.width() <= 0 or self.height() <= 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setClipRect(self.rect())
        primary = self._primary()
        is_dark = bool(self._tokens.get("is_dark", True))
        self._paint_aurora_fog(painter, primary, is_dark)
        self._paint_silk_ribbons(painter, primary, is_dark)
        painter.end()
