#!/usr/bin/env python3
"""
🐱 Desktop Pet — A smart cat that lives on your macOS desktop!

A floating animated cat that wanders around your screen.
It walks, naps, plays, gets curious, follows your cursor, and chats
in little speech bubbles.

  • Left-click + drag  → pick up and move the cat
  • Right-click        → menu (change state / quit)
  • Double-click       → make the cat react

Install: pip install PySide6
Run:     python desktop_pet.py
"""

import sys
import random

from PySide6.QtCore import Qt, QTimer, QPoint, QRect
from PySide6.QtGui import (
    QPainter, QFont, QColor, QPen, QBrush, QFontMetrics, QCursor,
)
from PySide6.QtWidgets import QApplication, QWidget, QMenu


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
WIDGET_W       = 130     # widget width
WIDGET_H       = 200     # widget height (extra room for thought bubble on top)
EMOJI_SIZE     = 80      # pet emoji font size — larger = more visible
TICK_MS        = 120     # animation tick interval

# Animation frames per state
FRAMES = {
    "idle":    ["🐱", "😺", "🐱", "😼"],
    "walk":    ["🐈", "🐱", "🐈", "🐱"],
    "run":     ["🐈", "🐈\u200d⬛", "🐈", "🐈\u200d⬛"],
    "sleep":   ["😴", "💤", "😴", "💤"],
    "play":    ["😸", "😺", "🙀", "😺"],
    "curious": ["😼", "🐱", "😼", "🐱"],
}

# Horizontal movement speed (px/tick)
SPEEDS = {
    "idle":    0,
    "walk":    3,
    "run":     9,
    "sleep":   0,
    "play":    2,
    "curious": 5,
}

# State duration in ticks (1 tick ≈ TICK_MS ms)
DURATIONS = {
    "idle":    (25, 60),
    "walk":    (50, 130),
    "run":     (20, 45),
    "sleep":   (60, 150),
    "play":    (25, 55),
    "curious": (30, 70),
}

# Weighted next-state choices
TRANSITIONS = {
    "idle":    ["walk", "walk", "walk", "sleep", "play", "curious"],
    "walk":    ["walk", "idle", "run", "sleep", "curious", "play"],
    "run":     ["walk", "walk", "idle"],
    "sleep":   ["sleep", "idle", "walk"],
    "play":    ["walk", "idle", "play"],
    "curious": ["walk", "idle", "play"],
}

# Random thoughts (shown in a speech bubble)
THOUGHTS = [
    "meow~", "purrr...", "snack?", "zzz...", "boop?", "hooman?",
    "🐟?", "?", "...", "!", "🐾", "play?", "hi!",
]


# ---------------------------------------------------------------------------
# Desktop Pet
# ---------------------------------------------------------------------------
class DesktopPet(QWidget):

    def __init__(self):
        super().__init__()

        # ---- Window: frameless, transparent, always on top ----
        # NOTE: macOS-specific - use SplashScreen flag instead of Tool which
        # was hiding the window on some macOS versions. Also avoid
        # WindowDoesNotAcceptFocus which can prevent rendering entirely.
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.SplashScreen               # show across spaces, no dock icon
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_AlwaysStackOnTop)
        self.setAttribute(Qt.WA_ShowWithoutActivating)  # don't steal focus

        # Debug mode: pass DESKTOP_PET_DEBUG=1 env var to see a red border
        # around the widget so you can locate the cat on your screen.
        import os
        self._debug = os.environ.get("DESKTOP_PET_DEBUG") == "1"

        self.resize(WIDGET_W, WIDGET_H)

        # ---- Screen bounds ----
        screen = QApplication.primaryScreen().availableGeometry()
        self.screen_rect = screen

        # ---- Initial state ----
        self.state          = "idle"
        self.frame_idx      = 0
        self.direction      = random.choice([-1, 1])   # -1 left, +1 right
        self.state_ticks    = 0
        self.state_duration = random.randint(*DURATIONS["idle"])

        # ---- Thought bubble ----
        self.thought       = None
        self.thought_ticks = 0

        # ---- Mouse / drag ----
        self.dragging    = False
        self.drag_offset = QPoint()

        # ---- Spawn position: bottom of screen, random x ----
        start_x = random.randint(100, max(101, screen.width() - 200))
        start_y = screen.height() - WIDGET_H - 40
        self.move(start_x, start_y)

        # ---- Animation timer ----
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(TICK_MS)

        self.show()
        self.raise_()
        self.activateWindow()

        # ---- Debug info to stderr ----
        print(
            f"[DesktopPet] screen={screen.width()}x{screen.height()} "
            f"pos=({start_x},{start_y}) size=({WIDGET_W}x{WIDGET_H}) "
            f"visible={self.isVisible()}",
            file=sys.stderr, flush=True,
        )

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------
    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)

        # Debug: draw a red border + crosshair so you can locate the widget
        if self._debug:
            p.setPen(QPen(QColor(255, 0, 0, 200), 2))
            p.setBrush(QBrush(QColor(255, 255, 0, 60)))
            p.drawRect(0, 0, WIDGET_W - 1, WIDGET_H - 1)
            p.drawLine(0, WIDGET_H // 2, WIDGET_W, WIDGET_H // 2)
            p.drawLine(WIDGET_W // 2, 0, WIDGET_W // 2, WIDGET_H)

        # Speech bubble (top of widget)
        if self.thought:
            self._draw_thought(p, self.thought)

        # Pet emoji (bottom of widget)
        emoji = FRAMES[self.state][self.frame_idx % len(FRAMES[self.state])]
        font = QFont("Apple Color Emoji", EMOJI_SIZE)
        p.setFont(font)

        pet_rect = QRect(0, WIDGET_H - WIDGET_W, WIDGET_W, WIDGET_W)

        # Mirror horizontally if facing left
        p.save()
        if self.direction == -1:
            p.translate(WIDGET_W, 0)
            p.scale(-1, 1)
        p.drawText(pet_rect, Qt.AlignCenter, emoji)
        p.restore()

    def _draw_thought(self, p, text):
        font = QFont(".AppleSystemUIFont", 13)
        p.setFont(font)
        metrics = QFontMetrics(font)
        text_w = metrics.horizontalAdvance(text)
        text_h = metrics.height()

        pad_x, pad_y = 12, 6
        bubble_w = text_w + pad_x * 2
        bubble_h = text_h + pad_y * 2
        bubble_x = (WIDGET_W - bubble_w) // 2
        bubble_y = 6

        # Bubble background
        p.setBrush(QBrush(QColor(255, 255, 255, 235)))
        p.setPen(QPen(QColor(80, 80, 80, 200), 1.4))
        p.drawRoundedRect(bubble_x, bubble_y, bubble_w, bubble_h, 12, 12)

        # Bubble tail (little triangle pointing down to the cat)
        tail_x = WIDGET_W // 2
        tail_y = bubble_y + bubble_h
        p.setBrush(QBrush(QColor(255, 255, 255, 235)))
        p.drawPolygon([
            QPoint(tail_x - 6, tail_y - 1),
            QPoint(tail_x + 6, tail_y - 1),
            QPoint(tail_x,     tail_y + 8),
        ])

        # Text
        p.setPen(QColor(40, 40, 40))
        p.drawText(
            QRect(bubble_x, bubble_y, bubble_w, bubble_h),
            Qt.AlignCenter,
            text,
        )

    # ------------------------------------------------------------------
    # Tick loop
    # ------------------------------------------------------------------
    def _tick(self):
        self.frame_idx   += 1
        self.state_ticks += 1

        # Thought bubble lifecycle
        if self.thought_ticks > 0:
            self.thought_ticks -= 1
            if self.thought_ticks == 0:
                self.thought = None
        elif random.random() < 0.006:
            self.thought = random.choice(THOUGHTS)
            self.thought_ticks = 22

        # Movement
        if self.state == "curious":
            self._move_toward_cursor()
        else:
            self._move_horizontal()

        # State transition
        if self.state_ticks >= self.state_duration:
            self._transition()

        self.update()

    # ------------------------------------------------------------------
    # Movement
    # ------------------------------------------------------------------
    def _move_horizontal(self):
        speed = SPEEDS[self.state]
        if speed == 0:
            return
        new_x = self.x() + self.direction * speed
        max_x = self.screen_rect.width() - WIDGET_W
        if new_x < 0:
            new_x = 0
            self.direction = 1
        elif new_x > max_x:
            new_x = max_x
            self.direction = -1
        self.move(new_x, self.y())

    def _move_toward_cursor(self):
        cursor   = QCursor.pos()
        center_x = self.x() + WIDGET_W // 2
        dx       = cursor.x() - center_x
        if abs(dx) < 30:
            return
        speed = SPEEDS["curious"]
        step  = max(-speed, min(speed, dx // 6))
        self.direction = 1 if step > 0 else -1
        new_x = self.x() + step
        new_x = max(0, min(self.screen_rect.width() - WIDGET_W, new_x))
        self.move(new_x, self.y())

    def _transition(self):
        self.state          = random.choice(TRANSITIONS[self.state])
        self.frame_idx      = 0
        self.state_ticks    = 0
        self.state_duration = random.randint(*DURATIONS[self.state])
        if random.random() < 0.4:
            self.direction *= -1

    # ------------------------------------------------------------------
    # Mouse interaction
    # ------------------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging    = True
            self.drag_offset = event.globalPosition().toPoint() - self.pos()
            self._set_state("play")
            self.thought       = random.choice(["wheee!", "boop!", "!!"])
            self.thought_ticks = 18
        elif event.button() == Qt.RightButton:
            self._show_menu(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event):
        if self.dragging:
            self.move(event.globalPosition().toPoint() - self.drag_offset)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.dragging:
            self.dragging = False
            self._set_state("idle")

    def mouseDoubleClickEvent(self, _event):
        self.thought       = random.choice(["meow!", "purr~", "love u", "🐾"])
        self.thought_ticks = 22

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------
    def _show_menu(self, pos):
        menu = QMenu(self)
        for label, state in [
            ("😺   Walk",    "walk"),
            ("💨   Run",     "run"),
            ("😴   Sleep",   "sleep"),
            ("😸   Play",    "play"),
            ("😼   Curious", "curious"),
            ("🐱   Idle",    "idle"),
        ]:
            menu.addAction(label, lambda s=state: self._set_state(s))
        menu.addSeparator()
        menu.addAction("Quit", QApplication.quit)
        menu.exec(pos)

    def _set_state(self, state):
        self.state          = state
        self.frame_idx      = 0
        self.state_ticks    = 0
        self.state_duration = random.randint(*DURATIONS[state])


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    _pet = DesktopPet()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
