"""Reusable, opt-in button motion effects."""

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QEvent,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QTimer,
    Qt,
)
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPolygonF
from PySide6.QtWidgets import QWidget


class ButtonShineOverlay(QWidget):
    """Transparent child overlay that sweeps a specular band over a button."""

    def __init__(self, button, interval_ms=2800):
        super().__init__(button)
        self._button = button
        self._progress = 1.0
        self._enabled = True
        self._interval_ms = max(1200, int(interval_ms))
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setGeometry(button.rect())
        self.raise_()

        self._animation = QPropertyAnimation(self, b"progress", self)
        self._animation.setDuration(720)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setEasingCurve(QEasingCurve.InOutCubic)

        self._timer = QTimer(self)
        self._timer.setInterval(self._interval_ms)
        self._timer.timeout.connect(self.play)
        button.installEventFilter(self)
        self._timer.start()
        QTimer.singleShot(450, self.play)

    def set_interval(self, interval_ms):
        self._interval_ms = max(1200, int(interval_ms))
        self._timer.setInterval(self._interval_ms)

    def set_enabled(self, enabled):
        self._enabled = bool(enabled)
        if self._enabled and self._button.isVisible():
            self._timer.start()
        else:
            self._timer.stop()
            self._animation.stop()
            self._set_progress(1.0)

    def _get_progress(self):
        return self._progress

    def _set_progress(self, value):
        self._progress = float(value)
        self.update()

    progress = Property(float, _get_progress, _set_progress)

    def play(self):
        if not self._enabled or not self._button.isVisible() or not self._button.isEnabled():
            return
        self.raise_()
        self._animation.stop()
        self._set_progress(0.0)
        self._animation.start()

    def eventFilter(self, watched, event):
        if watched is self._button:
            if event.type() == QEvent.Resize:
                self.setGeometry(self._button.rect())
                self.raise_()
            elif event.type() == QEvent.Enter:
                self.play()
            elif event.type() == QEvent.Show:
                self.setGeometry(self._button.rect())
                if self._enabled:
                    self._timer.start()
            elif event.type() == QEvent.Hide:
                self._timer.stop()
                self._animation.stop()
        return False

    def paintEvent(self, event):
        if self._progress >= 1.0 or self.width() <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 10, 10)
        painter.setClipPath(clip)

        travel = self.width() + 150.0
        x = -90.0 + self._progress * travel
        band = QPolygonF([
            QPointF(x - 44, self.height()),
            QPointF(x + 2, self.height()),
            QPointF(x + 48, 0),
            QPointF(x + 2, 0),
        ])
        gradient = QLinearGradient(x - 44, 0, x + 48, 0)
        gradient.setColorAt(0.0, QColor(255, 255, 255, 0))
        gradient.setColorAt(0.42, QColor(255, 255, 255, 18))
        gradient.setColorAt(0.58, QColor(255, 255, 255, 126))
        gradient.setColorAt(0.72, QColor(255, 255, 255, 24))
        gradient.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawPolygon(band)
        painter.end()


def enable_button_shine(button, interval_ms=2800):
    """Attach or update a reusable shine overlay without changing button APIs."""
    overlay = getattr(button, "_shine_overlay", None)
    if overlay is None:
        overlay = ButtonShineOverlay(button, interval_ms=interval_ms)
        button._shine_overlay = overlay
    else:
        overlay.set_interval(interval_ms)
    return overlay
