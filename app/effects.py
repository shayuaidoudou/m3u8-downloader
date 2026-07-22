"""Theme-aware motion primitives used by the main dashboard.

The effects in this module are deliberately paint-only: they never alter
layout or business state, and each animation stops automatically while its
widget is hidden.
"""

from __future__ import annotations

import math

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QRadialGradient,
)
from PySide6.QtWidgets import QFrame, QSizePolicy, QWidget

from config import UI_TOKENS
from .button_effects import ButtonShineOverlay, enable_button_shine
from .compose_effects import ComposeEnergyCard


def _with_alpha(color, alpha):
    result = QColor(color)
    result.setAlpha(max(0, min(255, int(alpha))))
    return result


def _token_color(tokens, name, fallback):
    return QColor(tokens.get(name, fallback))


class AmbientWorkspace(QWidget):
    """Cinematic, low-cost atmosphere behind the dashboard content."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._phase = 0.0
        self._motion_enabled = True
        self._tokens = dict(UI_TOKENS)
        self._animation = QPropertyAnimation(self, b"phase", self)
        self._animation.setDuration(10500)
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

    def _paint_grid(self, painter):
        width, height = self.width(), self.height()
        primary = _token_color(self._tokens, "primary", UI_TOKENS["primary"])
        is_dark = bool(self._tokens.get("is_dark", True))
        grid_color = _with_alpha(primary, 14 if is_dark else 10)
        painter.setPen(QPen(grid_color, 1))

        spacing = 72
        offset_x = int(self._phase * spacing) % spacing
        offset_y = int(self._phase * spacing * 0.45) % spacing
        for x in range(-spacing + offset_x, width + spacing, spacing):
            painter.drawLine(x, 0, x, height)
        for y in range(-spacing + offset_y, height + spacing, spacing):
            painter.drawLine(0, y, width, y)

    def _paint_aurora(self, painter):
        width, height = self.width(), self.height()
        is_dark = bool(self._tokens.get("is_dark", True))
        primary = _token_color(self._tokens, "primary", UI_TOKENS["primary"])
        secondary = _token_color(self._tokens, "primary_hover", primary)
        wave = math.sin(self._phase * math.tau)

        center = QPointF(width * (0.58 + wave * 0.20), height * (0.10 + abs(wave) * 0.10))
        radius = max(width * 0.58, 440)
        gradient = QRadialGradient(center, radius)
        gradient.setColorAt(0.0, _with_alpha(primary, 92 if is_dark else 58))
        gradient.setColorAt(0.38, _with_alpha(primary, 30 if is_dark else 20))
        gradient.setColorAt(1.0, _with_alpha(primary, 0))
        painter.fillRect(self.rect(), QBrush(gradient))

        counter = math.cos(self._phase * math.tau)
        second_center = QPointF(width * (0.86 + counter * 0.08), height * 0.78)
        second = QRadialGradient(second_center, max(width * 0.34, 300))
        second.setColorAt(0.0, _with_alpha(secondary, 48 if is_dark else 28))
        second.setColorAt(0.55, _with_alpha(secondary, 12 if is_dark else 9))
        second.setColorAt(1.0, _with_alpha(secondary, 0))
        painter.fillRect(self.rect(), QBrush(second))

    def _paint_particles(self, painter):
        width, height = self.width(), self.height()
        if width <= 0 or height <= 0:
            return
        primary = _token_color(self._tokens, "primary", UI_TOKENS["primary"])
        secondary = _token_color(self._tokens, "primary_hover", primary)
        is_dark = bool(self._tokens.get("is_dark", True))

        for index in range(22):
            seed_x = ((index * 137 + 53) % 997) / 997.0
            seed_y = ((index * 211 + 97) % 991) / 991.0
            drift = self._phase * (0.14 + (index % 5) * 0.018)
            y_ratio = (seed_y - drift) % 1.0
            sway = math.sin(self._phase * math.tau * 1.6 + index * 0.91)
            x = seed_x * width + sway * (8 + index % 4 * 3)
            y = y_ratio * height
            pulse = 0.55 + 0.45 * math.sin(self._phase * math.tau * 2.0 + index)
            core = QColor(primary if index % 3 else secondary)
            alpha = int((112 if is_dark else 74) * (0.48 + pulse * 0.52))
            radius = 1.0 + (index % 4) * 0.45

            painter.setPen(Qt.NoPen)
            painter.setBrush(_with_alpha(core, alpha // 4))
            painter.drawEllipse(QPointF(x, y), radius * 3.2, radius * 3.2)
            painter.setBrush(_with_alpha(core, alpha))
            painter.drawEllipse(QPointF(x, y), radius, radius)

    def _paint_sweeps(self, painter):
        width = self.width()
        primary = _token_color(self._tokens, "primary", UI_TOKENS["primary"])
        is_dark = bool(self._tokens.get("is_dark", True))

        sweep_x = self._phase * (width + 440) - 220
        sweep = QLinearGradient(sweep_x - 220, 0, sweep_x + 220, 0)
        sweep.setColorAt(0.0, _with_alpha(primary, 0))
        sweep.setColorAt(0.46, _with_alpha(primary, 28 if is_dark else 16))
        sweep.setColorAt(0.5, _with_alpha(primary, 210 if is_dark else 152))
        sweep.setColorAt(0.54, _with_alpha(primary, 28 if is_dark else 16))
        sweep.setColorAt(1.0, _with_alpha(primary, 0))
        painter.fillRect(QRectF(sweep_x - 220, 0, 440, 3.2), QBrush(sweep))

        # A broad diagonal ribbon gives the workspace a visible second motion plane.
        ribbon_x = ((self._phase + 0.38) % 1.0) * (width + 520) - 260
        ribbon = QLinearGradient(ribbon_x - 100, 0, ribbon_x + 100, 0)
        ribbon.setColorAt(0.0, _with_alpha(primary, 0))
        ribbon.setColorAt(0.5, _with_alpha(primary, 18 if is_dark else 10))
        ribbon.setColorAt(1.0, _with_alpha(primary, 0))
        path = QPolygonF([
            QPointF(ribbon_x - 140, self.height()),
            QPointF(ribbon_x - 60, self.height()),
            QPointF(ribbon_x + 160, 0),
            QPointF(ribbon_x + 80, 0),
        ])
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(ribbon))
        painter.drawPolygon(path)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.width() <= 0 or self.height() <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        self._paint_grid(painter)
        self._paint_aurora(painter)
        self._paint_particles(painter)
        self._paint_sweeps(painter)
        painter.end()


class EnergyBorderCard(QFrame):
    """A card with a moving perimeter beam and animated signal nodes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._phase = 0.0
        self._motion_enabled = True
        self._tokens = dict(UI_TOKENS)
        self._animation = QPropertyAnimation(self, b"phase", self)
        self._animation.setDuration(4600)
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

    def _paint_beam(self, painter, rect, primary, is_dark):
        beam = QConicalGradient(rect.center(), -self._phase * 360.0)
        beam.setColorAt(0.00, _with_alpha(primary, 0))
        beam.setColorAt(0.06, _with_alpha(primary, 0))
        beam.setColorAt(0.10, _with_alpha(primary, 76 if is_dark else 52))
        beam.setColorAt(0.125, _with_alpha(primary, 245 if is_dark else 210))
        beam.setColorAt(0.15, _with_alpha(primary, 74 if is_dark else 48))
        beam.setColorAt(0.20, _with_alpha(primary, 0))
        beam.setColorAt(0.56, _with_alpha(primary, 0))
        beam.setColorAt(0.59, _with_alpha(primary, 92 if is_dark else 62))
        beam.setColorAt(0.61, _with_alpha(primary, 0))
        beam.setColorAt(1.00, _with_alpha(primary, 0))
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QBrush(beam), 2.2))
        radius = float(self._tokens.get("radius_card", 14))
        painter.drawRoundedRect(rect, radius, radius)

    def _paint_brackets(self, painter, rect, primary, is_dark):
        bracket = _with_alpha(primary, 82 if is_dark else 60)
        painter.setPen(QPen(bracket, 1.2, Qt.SolidLine, Qt.RoundCap))
        inset, length = 12.0, 18.0
        left, top, right, bottom = rect.left(), rect.top(), rect.right(), rect.bottom()
        for p1, p2 in (
            (QPointF(left + inset, top), QPointF(left + inset + length, top)),
            (QPointF(left, top + inset), QPointF(left, top + inset + length)),
            (QPointF(right - inset - length, top), QPointF(right - inset, top)),
            (QPointF(right, top + inset), QPointF(right, top + inset + length)),
            (QPointF(left + inset, bottom), QPointF(left + inset + length, bottom)),
            (QPointF(left, bottom - inset - length), QPointF(left, bottom - inset)),
            (QPointF(right - inset - length, bottom), QPointF(right - inset, bottom)),
            (QPointF(right, bottom - inset - length), QPointF(right, bottom - inset)),
        ):
            painter.drawLine(p1, p2)

    def _paint_signal_nodes(self, painter, rect, primary, is_dark):
        painter.setPen(Qt.NoPen)
        for index in range(7):
            x = rect.left() + rect.width() * ((index * 0.163 + 0.09) % 0.92)
            y = rect.top() + rect.height() * ((index * 0.271 + 0.16) % 0.76 + 0.12)
            pulse = 0.5 + 0.5 * math.sin(self._phase * math.tau * 2 + index * 1.7)
            alpha = int((36 if is_dark else 22) + pulse * (72 if is_dark else 44))
            painter.setBrush(_with_alpha(primary, alpha // 4))
            painter.drawEllipse(QPointF(x, y), 5.0, 5.0)
            painter.setBrush(_with_alpha(primary, alpha))
            painter.drawEllipse(QPointF(x, y), 1.35, 1.35)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.width() < 8 or self.height() < 8:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        primary = _token_color(self._tokens, "primary", UI_TOKENS["primary"])
        is_dark = bool(self._tokens.get("is_dark", True))
        rect = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        self._paint_beam(painter, rect, primary, is_dark)
        self._paint_brackets(painter, rect, primary, is_dark)
        self._paint_signal_nodes(painter, rect, primary, is_dark)
        painter.end()


class EmptyStateVisual(QWidget):
    """Animated orbital download core used as the empty-state focal point."""

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(190, 180)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("点击填写下载链接")
        self.setAccessibleName("添加下载任务")
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._phase = 0.0
        self._burst = 1.0
        self._hovered = False
        self._motion_enabled = True
        self._tokens = dict(UI_TOKENS)

        self._animation = QPropertyAnimation(self, b"phase", self)
        self._animation.setDuration(5200)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setLoopCount(-1)
        self._animation.setEasingCurve(QEasingCurve.Linear)

        self._burst_animation = QPropertyAnimation(self, b"burst", self)
        self._burst_animation.setDuration(520)
        self._burst_animation.setStartValue(0.0)
        self._burst_animation.setEndValue(1.0)
        self._burst_animation.setEasingCurve(QEasingCurve.OutCubic)

    def set_tokens(self, tokens):
        self._tokens = dict(tokens or UI_TOKENS)
        self.update()

    def _get_phase(self):
        return self._phase

    def _set_phase(self, value):
        self._phase = float(value)
        self.update()

    phase = Property(float, _get_phase, _set_phase)

    def _get_burst(self):
        return self._burst

    def _set_burst(self, value):
        self._burst = float(value)
        self.update()

    burst = Property(float, _get_burst, _set_burst)

    def set_motion_enabled(self, enabled):
        self._motion_enabled = bool(enabled)
        if self._motion_enabled and self.isVisible():
            self.start_animation()
        else:
            self.stop_animation()

    def start_animation(self):
        if self._motion_enabled and self._animation.state() != QPropertyAnimation.Running:
            self._animation.start()

    def stop_animation(self):
        self._animation.stop()
        self._set_phase(0.0)

    def showEvent(self, event):
        super().showEvent(event)
        self.start_animation()

    def hideEvent(self, event):
        self.stop_animation()
        super().hideEvent(event)

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def _paint_halo(self, painter, center, primary):
        is_dark = bool(self._tokens.get("is_dark", True))
        halo = QRadialGradient(center, 82)
        halo.setColorAt(0.0, _with_alpha(primary, 90 if is_dark else 54))
        halo.setColorAt(0.28, _with_alpha(primary, 44 if is_dark else 26))
        halo.setColorAt(0.72, _with_alpha(primary, 10 if is_dark else 7))
        halo.setColorAt(1.0, _with_alpha(primary, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(halo))
        painter.drawEllipse(center, 82, 82)

    def _paint_orbits(self, painter, center, primary, secondary):
        is_dark = bool(self._tokens.get("is_dark", True))
        cx, cy = center.x(), center.y()

        painter.setBrush(Qt.NoBrush)
        for radius, alpha in ((38, 46), (53, 34), (68, 25)):
            painter.setPen(QPen(_with_alpha(primary, alpha if is_dark else int(alpha * 0.75)), 1.0))
            painter.drawEllipse(center, radius, radius)

        # Three independently rotating arc bands create a mechanical orbital core.
        for index, (radius, span, width, direction) in enumerate(
            ((39, 82, 2.8, 1), (53, 58, 2.0, -1), (68, 36, 1.6, 1))
        ):
            angle = (self._phase * 360.0 * direction + index * 117.0) % 360.0
            color = primary if index != 1 else secondary
            painter.setPen(QPen(_with_alpha(color, 230 if index == 0 else 168), width, Qt.SolidLine, Qt.RoundCap))
            rect = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)
            painter.drawArc(rect, int(angle * 16), int(span * 16))
            painter.setPen(QPen(_with_alpha(color, 52), width + 4.5, Qt.SolidLine, Qt.RoundCap))
            painter.drawArc(rect, int(angle * 16), int(span * 16))

        # Counter-rotating calibration ticks.
        painter.setPen(QPen(_with_alpha(primary, 92 if is_dark else 70), 1.0, Qt.SolidLine, Qt.RoundCap))
        for index in range(12):
            angle = math.radians(index * 30.0 - self._phase * 180.0)
            inner = 72 if index % 3 == 0 else 74
            outer = 78 if index % 3 == 0 else 77
            painter.drawLine(
                QPointF(cx + math.cos(angle) * inner, cy + math.sin(angle) * inner),
                QPointF(cx + math.cos(angle) * outer, cy + math.sin(angle) * outer),
            )

        # Luminous particles and short comet tails on two elliptical orbits.
        for index in range(8):
            orbit = 48 if index < 4 else 64
            direction = 1 if index % 2 == 0 else -1
            angle = self._phase * math.tau * direction * (1.0 + (index % 3) * 0.16) + index * 0.92
            x = cx + math.cos(angle) * orbit
            y = cy + math.sin(angle) * orbit * 0.78
            tail_angle = angle - direction * 0.10
            tx = cx + math.cos(tail_angle) * orbit
            ty = cy + math.sin(tail_angle) * orbit * 0.78
            particle = primary if index % 3 else secondary
            painter.setPen(QPen(_with_alpha(particle, 74), 1.4, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(QPointF(tx, ty), QPointF(x, y))
            painter.setPen(Qt.NoPen)
            painter.setBrush(_with_alpha(particle, 48))
            painter.drawEllipse(QPointF(x, y), 5.0, 5.0)
            painter.setBrush(_with_alpha(particle, 235))
            painter.drawEllipse(QPointF(x, y), 1.8 + index % 2 * 0.6, 1.8 + index % 2 * 0.6)

    def _paint_core(self, painter, center, primary, secondary):
        cx, cy = center.x(), center.y()
        rotation = self._phase * math.tau * -0.34
        diamond = QPolygonF()
        for index in range(4):
            angle = rotation + math.pi / 4 + index * math.pi / 2
            diamond.append(QPointF(cx + math.cos(angle) * 30, cy + math.sin(angle) * 30))
        painter.setPen(QPen(_with_alpha(primary, 82), 1.1))
        painter.setBrush(_with_alpha(primary, 14))
        painter.drawPolygon(diamond)

        core_gradient = QRadialGradient(QPointF(cx - 8, cy - 10), 38)
        core_gradient.setColorAt(0.0, _with_alpha(secondary, 238))
        core_gradient.setColorAt(0.45, _with_alpha(primary, 216))
        core_gradient.setColorAt(1.0, _with_alpha(primary, 82))
        painter.setPen(QPen(_with_alpha(primary, 210), 1.4))
        painter.setBrush(QBrush(core_gradient))
        painter.drawEllipse(center, 25, 25)

        # Download glyph with a soft luminous under-stroke.
        glyph_points = (
            (QPointF(cx, cy - 12), QPointF(cx, cy + 3)),
            (QPointF(cx - 7, cy - 2), QPointF(cx, cy + 5)),
            (QPointF(cx + 7, cy - 2), QPointF(cx, cy + 5)),
        )
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(_with_alpha(primary, 74), 7.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        for p1, p2 in glyph_points:
            painter.drawLine(p1, p2)
        painter.setPen(QPen(_with_alpha(QColor("#FFFFFF"), 238), 2.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        for p1, p2 in glyph_points:
            painter.drawLine(p1, p2)

        tray = QPainterPath()
        tray.moveTo(cx - 13, cy + 10)
        tray.lineTo(cx - 10, cy + 16)
        tray.lineTo(cx + 10, cy + 16)
        tray.lineTo(cx + 13, cy + 10)
        painter.setPen(QPen(_with_alpha(primary, 78), 7.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPath(tray)
        painter.setPen(QPen(_with_alpha(QColor("#FFFFFF"), 238), 2.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPath(tray)

    def _paint_burst(self, painter, center, primary):
        if not 0.0 <= self._burst < 1.0:
            return
        progress = self._burst
        alpha = int(210 * (1.0 - progress))
        radius = 27 + 58 * progress
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(_with_alpha(primary, alpha), 2.3 * (1.0 - progress) + 0.6))
        painter.drawEllipse(center, radius, radius)
        painter.setPen(QPen(_with_alpha(primary, alpha // 2), 1.4, Qt.SolidLine, Qt.RoundCap))
        for index in range(10):
            angle = index * math.tau / 10 + progress * 0.25
            inner = radius + 5
            outer = inner + 17 * (1.0 - progress)
            painter.drawLine(
                QPointF(center.x() + math.cos(angle) * inner, center.y() + math.sin(angle) * inner),
                QPointF(center.x() + math.cos(angle) * outer, center.y() + math.sin(angle) * outer),
            )

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        center = QPointF(self.width() / 2, 82)
        primary = _token_color(self._tokens, "primary", UI_TOKENS["primary"])
        secondary = _token_color(self._tokens, "primary_hover", primary)

        self._paint_halo(painter, center, primary)
        self._paint_orbits(painter, center, primary, secondary)
        self._paint_core(painter, center, primary, secondary)
        self._paint_burst(painter, center, primary)

        label_font = QFont("Menlo")
        label_font.setPixelSize(9)
        label_font.setWeight(QFont.DemiBold)
        label_font.setLetterSpacing(QFont.AbsoluteSpacing, 1.1)
        painter.setFont(label_font)
        painter.setPen(_with_alpha(primary, 230 if self._hovered else 176))
        painter.drawText(QRectF(0, 165, self.width(), 14), Qt.AlignHCenter | Qt.AlignTop, "M3U8 CORE  ·  READY")
        painter.end()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self._burst_animation.stop()
            self._set_burst(0.0)
            self._burst_animation.start()
            self.clicked.emit()
        super().mouseReleaseEvent(event)


__all__ = [
    "AmbientWorkspace",
    "ButtonShineOverlay",
    "ComposeEnergyCard",
    "EmptyStateVisual",
    "EnergyBorderCard",
    "enable_button_shine",
]
