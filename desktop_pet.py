#!/usr/bin/env python3
"""
🐱 Desktop Pet — A smooth cartoon cat that lives on your macOS desktop!

A floating animated orange tabby that wanders around your screen.
It walks, runs, sits, grooms itself (licks its body), naps, plays,
and follows your cursor — all drawn as smooth vector shapes.

  • Left-click + drag  → pick up and move the cat
  • Right-click        → menu (change state / quit)
  • Double-click       → make the cat react

Install: pip install PySide6
Run:     python desktop_pet.py
"""

import os
import sys
import math
import random

from PySide6.QtCore import Qt, QTimer, QPoint, QRect, QPointF, QRectF
from PySide6.QtGui import (
    QPainter,
    QFont,
    QColor,
    QPen,
    QBrush,
    QFontMetrics,
    QCursor,
    QPainterPath,
    QRadialGradient,
)
from PySide6.QtWidgets import QApplication, QWidget, QMenu


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
WIDGET_W = 260
WIDGET_H = 220
TICK_MS = 100
GROUND_Y = WIDGET_H - 22          # baseline the cat stands on

# ---------------------------------------------------------------------------
# Orange-tabby colour palette
# ---------------------------------------------------------------------------
FUR        = QColor(240, 155, 60)
FUR_DARK   = QColor(205, 118, 38)
FUR_STRIPE = QColor(185, 105, 30)
BELLY      = QColor(255, 220, 175)
EAR_PINK   = QColor(255, 175, 165)
NOSE_PINK  = QColor(255, 140, 140)
EYE_GREEN  = QColor(85, 195, 85)
PUPIL_CLR  = QColor(22, 22, 28)
EYE_WHITE  = QColor(255, 255, 255, 230)
WHISKER_C  = QColor(75, 75, 75, 160)
TONGUE_C   = QColor(255, 145, 155)
OUTLINE_C  = QColor(160, 95, 30, 70)

# ---------------------------------------------------------------------------
# Cat dimensions (px)
# ---------------------------------------------------------------------------
BODY_RX   = 38          # body ellipse semi-width
BODY_RY   = 22          # body ellipse semi-height
HEAD_R    = 24           # head circle radius
EAR_W     = 12
EAR_H     = 17
LEG_W     = 10
LEG_H     = 22
TAIL_W    = 7

# ---------------------------------------------------------------------------
# Behaviour — states / speeds / transitions
# ---------------------------------------------------------------------------
SPEEDS = {
    "idle": 0, "walk": 3, "run": 9, "sleep": 0,
    "play": 2, "curious": 5, "groom": 0,
}
DURATIONS = {
    "idle": (25, 60), "walk": (50, 130), "run": (20, 45),
    "sleep": (60, 150), "play": (25, 55), "curious": (30, 70),
    "groom": (30, 70),
}
TRANSITIONS = {
    "idle":    ["walk", "walk", "groom", "groom", "sleep", "play", "curious"],
    "walk":    ["walk", "idle", "groom", "run", "curious", "sleep"],
    "run":     ["walk", "idle", "walk"],
    "sleep":   ["sleep", "idle", "groom", "walk"],
    "play":    ["walk", "idle", "groom"],
    "curious": ["walk", "idle", "groom"],
    "groom":   ["idle", "walk", "groom", "sleep"],
}
THOUGHTS = [
    "meow~", "purrr...", "snack?", "zzz...", "boop?", "hooman?",
    "🐟?", "?", "...", "!", "🐾", "play?", "hi!",
]
NFRAMES = {
    "idle": 4, "walk": 8, "run": 6, "sleep": 4,
    "play": 6, "curious": 8, "groom": 8,
}


# ╔═════════════════════════════════════════════════════════════════════════╗
# ║  DRAWING HELPERS                                                       ║
# ╚═════════════════════════════════════════════════════════════════════════╝

def _outline_pen(width: float = 1.6) -> QPen:
    return QPen(OUTLINE_C, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)


def draw_body(p: QPainter, cx: float, cy: float,
              rx: float = BODY_RX, ry: float = BODY_RY, angle: float = 0):
    """Orange ellipse with lighter belly crescent."""
    p.save()
    p.translate(cx, cy)
    if angle:
        p.rotate(angle)
    # Main fur
    p.setPen(_outline_pen())
    p.setBrush(QBrush(FUR))
    p.drawEllipse(QRectF(-rx, -ry, rx * 2, ry * 2))
    # Belly highlight (bottom-center)
    belly_path = QPainterPath()
    belly_path.addEllipse(QRectF(-rx * 0.55, -ry * 0.1, rx * 1.1, ry * 1.5))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(BELLY))
    p.setOpacity(0.45)
    p.drawPath(belly_path)
    p.setOpacity(1.0)
    # Tabby stripes (3 arcs across back)
    stripe_pen = QPen(FUR_STRIPE, 2.2, Qt.SolidLine, Qt.RoundCap)
    p.setPen(stripe_pen)
    p.setBrush(Qt.NoBrush)
    for i, frac in enumerate([0.25, 0.48, 0.71]):
        sx = -rx + rx * 2 * frac
        p.drawArc(QRectF(sx - 6, -ry - 4, 12, ry * 1.2), 30 * 16, 120 * 16)
    p.restore()


def draw_head(p: QPainter, cx: float, cy: float,
              eye_open: float = 1.0, look_back: bool = False):
    """Full head: circle + ears + eyes + nose + mouth + whiskers."""
    r = HEAD_R
    p.save()
    p.translate(cx, cy)

    # -- Ears (behind head circle) --
    for side in (-1, 1):
        ex = side * (r - 4)
        ey = -r + 2
        ear = QPainterPath()
        ear.moveTo(ex - EAR_W * 0.5, ey + 4)
        ear.lineTo(ex, ey - EAR_H + 4)
        ear.lineTo(ex + EAR_W * 0.5, ey + 4)
        ear.closeSubpath()
        p.setPen(_outline_pen())
        p.setBrush(QBrush(FUR))
        p.drawPath(ear)
        # Inner pink
        inner = QPainterPath()
        inner.moveTo(ex - EAR_W * 0.28, ey + 3)
        inner.lineTo(ex, ey - EAR_H * 0.55 + 4)
        inner.lineTo(ex + EAR_W * 0.28, ey + 3)
        inner.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(EAR_PINK))
        p.drawPath(inner)

    # -- Head circle --
    p.setPen(_outline_pen())
    p.setBrush(QBrush(FUR))
    p.drawEllipse(QRectF(-r, -r, r * 2, r * 2))

    # -- Tabby "M" on forehead --
    m_pen = QPen(FUR_STRIPE, 1.6, Qt.SolidLine, Qt.RoundCap)
    p.setPen(m_pen)
    p.setBrush(Qt.NoBrush)
    mp = QPainterPath()
    mp.moveTo(-10, -6)
    mp.quadTo(-5, -14, 0, -7)
    mp.quadTo(5, -14, 10, -6)
    p.drawPath(mp)

    if look_back:
        # Simplified profile — just the ear tips & back of head visible
        p.restore()
        return

    # -- Eyes --
    for side in (-1, 1):
        ex = side * 9
        ey = -2
        ew = 7.5 * eye_open + 0.5
        eh = 8.0 * eye_open + 0.5
        if eye_open > 0.15:
            # Sclera
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(EYE_WHITE))
            p.drawEllipse(QPointF(ex, ey), ew, eh)
            # Iris
            p.setBrush(QBrush(EYE_GREEN))
            p.drawEllipse(QPointF(ex, ey + 0.5), ew * 0.72, eh * 0.72)
            # Pupil
            p.setBrush(QBrush(PUPIL_CLR))
            p.drawEllipse(QPointF(ex, ey + 0.8), ew * 0.35, eh * 0.55)
            # Highlight
            p.setBrush(QBrush(QColor(255, 255, 255, 200)))
            p.drawEllipse(QPointF(ex - 1.5, ey - 2), 1.8, 1.8)
        else:
            # Closed — a curved line
            p.setPen(QPen(PUPIL_CLR, 1.8, Qt.SolidLine, Qt.RoundCap))
            p.setBrush(Qt.NoBrush)
            p.drawArc(QRectF(ex - 5, ey - 2, 10, 6), 0, 180 * 16)

    # -- Nose --
    nose = QPainterPath()
    nose.moveTo(0, 4)
    nose.lineTo(-3.5, 0.5)
    nose.lineTo(3.5, 0.5)
    nose.closeSubpath()
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(NOSE_PINK))
    p.drawPath(nose)

    # -- Mouth --
    p.setPen(QPen(FUR_DARK, 1.2, Qt.SolidLine, Qt.RoundCap))
    p.setBrush(Qt.NoBrush)
    mouth = QPainterPath()
    mouth.moveTo(-4, 6.5)
    mouth.quadTo(0, 10, 4, 6.5)
    p.drawPath(mouth)

    # -- Whiskers --
    wp = QPen(WHISKER_C, 1.0, Qt.SolidLine, Qt.RoundCap)
    p.setPen(wp)
    for side in (-1, 1):
        bx = side * 5
        for angle_d in (-15, 0, 15):
            rad = math.radians(angle_d)
            length = 22
            dx = side * length * math.cos(rad)
            dy = length * math.sin(rad)
            p.drawLine(QPointF(bx, 4), QPointF(bx + dx, 4 + dy))

    p.restore()


def draw_leg(p: QPainter, x: float, ground_y: float,
             swing: float = 0, shorter: bool = False):
    """One rounded-rectangle leg. *swing* moves the foot forward/back."""
    h = LEG_H * (0.65 if shorter else 1.0)
    top_y = ground_y - h
    p.setPen(_outline_pen(1.2))
    p.setBrush(QBrush(FUR_DARK))
    path = QPainterPath()
    foot_x = x + swing
    path.moveTo(x - LEG_W / 2, top_y)
    path.lineTo(foot_x - LEG_W / 2, ground_y - 4)
    path.quadTo(foot_x - LEG_W / 2, ground_y, foot_x, ground_y)
    path.quadTo(foot_x + LEG_W / 2, ground_y, foot_x + LEG_W / 2, ground_y - 4)
    path.lineTo(x + LEG_W / 2, top_y)
    path.closeSubpath()
    p.drawPath(path)


def draw_tail(p: QPainter, bx: float, by: float,
              curl: float = 0.5, base_angle: float = 130):
    """Bézier tail. curl ∈ [0,1] controls how curved it is."""
    length = 45
    rad = math.radians(base_angle)
    # End-point direction
    ex = bx + length * math.cos(rad)
    ey = by + length * math.sin(rad) * -1  # negative = upward

    # Control points — curl bends the tip inward
    cp1x = bx + 20 * math.cos(rad + 0.3)
    cp1y = by - 20
    cp2x = ex + curl * 25
    cp2y = ey - curl * 20

    path = QPainterPath()
    path.moveTo(bx, by)
    path.cubicTo(cp1x, cp1y, cp2x, cp2y, ex, ey)

    p.setPen(QPen(FUR_DARK, TAIL_W, Qt.SolidLine, Qt.RoundCap))
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)
    # Slightly thinner orange core
    p.setPen(QPen(FUR, TAIL_W - 2.5, Qt.SolidLine, Qt.RoundCap))
    p.drawPath(path)


def draw_tongue(p: QPainter, tx: float, ty: float, size: float = 5):
    """Small pink tongue for grooming."""
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(TONGUE_C))
    p.drawEllipse(QPointF(tx, ty), size, size * 1.3)


# ╔═════════════════════════════════════════════════════════════════════════╗
# ║  DESKTOP PET                                                           ║
# ╚═════════════════════════════════════════════════════════════════════════╝

class DesktopPet(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.SplashScreen
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_AlwaysStackOnTop)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self._debug = os.environ.get("DESKTOP_PET_DEBUG") == "1"
        self.resize(WIDGET_W, WIDGET_H)

        screen = QApplication.primaryScreen().availableGeometry()
        self.screen_rect = screen

        self.state          = "idle"
        self.frame_idx      = 0
        self.direction      = random.choice([-1, 1])
        self.state_ticks    = 0
        self.state_duration = random.randint(*DURATIONS["idle"])
        self.thought        = None
        self.thought_ticks  = 0
        self.dragging       = False
        self.drag_offset    = QPoint()

        sx = random.randint(100, max(101, screen.width() - 200))
        sy = screen.height() - WIDGET_H - 40
        self.move(sx, sy)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(TICK_MS)

        self.show()
        self.raise_()
        self.activateWindow()
        print(
            f"[DesktopPet] screen={screen.width()}x{screen.height()} "
            f"pos=({sx},{sy}) visible={self.isVisible()}",
            file=sys.stderr, flush=True,
        )

    # ==================================================================
    #  PAINT
    # ==================================================================
    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)

        # Paint a nearly-invisible fill so macOS doesn't pass clicks
        # through fully-transparent pixels to the desktop behind us.
        p.fillRect(0, 0, WIDGET_W, WIDGET_H, QColor(0, 0, 0, 1))

        if self._debug:
            p.setPen(QPen(QColor(255, 0, 0, 200), 2))
            p.setBrush(QBrush(QColor(255, 255, 0, 40)))
            p.drawRect(0, 0, WIDGET_W - 1, WIDGET_H - 1)

        if self.thought:
            self._draw_thought(p, self.thought)

        p.save()
        if self.direction == -1:
            p.translate(WIDGET_W, 0)
            p.scale(-1, 1)
        self._draw_cat(p)
        p.restore()

    # ------------------------------------------------------------------
    #  Cat dispatcher
    # ------------------------------------------------------------------
    def _draw_cat(self, p):
        s = self.state
        f = self.frame_idx % NFRAMES.get(s, 4)
        {
            "walk":    self._pose_walk,
            "curious": self._pose_walk,
            "run":     self._pose_run,
            "idle":    self._pose_idle,
            "groom":   self._pose_groom,
            "sleep":   self._pose_sleep,
            "play":    self._pose_play,
        }.get(s, self._pose_idle)(p, f)

    # ------------------------------------------------------------------
    #  WALK  (8 frames)
    # ------------------------------------------------------------------
    def _pose_walk(self, p, f):
        t = f / 8.0
        ang = t * 2 * math.pi
        bob = math.sin(ang * 2) * 2.5

        bcx = WIDGET_W / 2
        bcy = GROUND_Y - LEG_H - BODY_RY + bob

        # back legs
        draw_leg(p, bcx - BODY_RX + 14, GROUND_Y, math.sin(ang + math.pi) * 10)
        draw_leg(p, bcx + BODY_RX - 14, GROUND_Y, math.sin(ang) * 10)
        # tail
        draw_tail(p, bcx - BODY_RX - 2, bcy - 4,
                  curl=0.45 + 0.15 * math.sin(ang), base_angle=135)
        # body
        draw_body(p, bcx, bcy)
        # front legs
        draw_leg(p, bcx - BODY_RX + 20, GROUND_Y, math.sin(ang) * 10)
        draw_leg(p, bcx + BODY_RX - 8, GROUND_Y, math.sin(ang + math.pi) * 10)
        # head
        hx = bcx + BODY_RX + HEAD_R * 0.45
        hy = bcy - BODY_RY * 0.55 + bob
        draw_head(p, hx, hy, eye_open=1.0)

    # ------------------------------------------------------------------
    #  RUN  (6 frames)
    # ------------------------------------------------------------------
    def _pose_run(self, p, f):
        t = f / 6.0
        ang = t * 2 * math.pi
        bob = math.sin(ang * 2) * 4
        stretch = 1.1 + 0.08 * math.sin(ang * 2)

        bcx = WIDGET_W / 2
        bcy = GROUND_Y - LEG_H - BODY_RY + bob - 4

        draw_leg(p, bcx - BODY_RX * stretch + 10, GROUND_Y,
                 math.sin(ang + math.pi) * 18)
        draw_leg(p, bcx + BODY_RX * stretch - 10, GROUND_Y,
                 math.sin(ang) * 18)
        draw_tail(p, bcx - BODY_RX * stretch - 2, bcy,
                  curl=0.2 + 0.2 * math.sin(ang), base_angle=160)
        draw_body(p, bcx, bcy, rx=BODY_RX * stretch, ry=BODY_RY * 0.85)
        draw_leg(p, bcx - BODY_RX * stretch + 18, GROUND_Y,
                 math.sin(ang) * 18)
        draw_leg(p, bcx + BODY_RX * stretch - 4, GROUND_Y,
                 math.sin(ang + math.pi) * 18)
        hx = bcx + BODY_RX * stretch + HEAD_R * 0.4
        hy = bcy - BODY_RY * 0.5 + bob
        draw_head(p, hx, hy, eye_open=0.85)

    # ------------------------------------------------------------------
    #  IDLE / SIT  (4 frames — occasional blink)
    # ------------------------------------------------------------------
    def _pose_idle(self, p, f):
        bcx = WIDGET_W / 2
        bcy = GROUND_Y - BODY_RY * 0.9          # body lower (sitting)
        breath = math.sin(f / 4.0 * math.pi) * 1.5

        # Tucked legs (small visible paws)
        draw_leg(p, bcx - 14, GROUND_Y, 0, shorter=True)
        draw_leg(p, bcx + 14, GROUND_Y, 0, shorter=True)

        # Tail wraps in front
        draw_tail(p, bcx - BODY_RX + 2, bcy + 4,
                  curl=0.8, base_angle=200)

        # Body (slightly rounder when sitting)
        draw_body(p, bcx, bcy + breath, rx=BODY_RX * 0.88,
                  ry=BODY_RY * 1.1)

        # Head
        hx = bcx + BODY_RX * 0.3
        hy = bcy - BODY_RY * 1.15 + breath
        eye = 0.1 if f == 3 else 1.0       # blink on frame 3
        draw_head(p, hx, hy, eye_open=eye)

    # ------------------------------------------------------------------
    #  GROOM  (8 frames — head turns back, tongue licks body)
    # ------------------------------------------------------------------
    def _pose_groom(self, p, f):
        bcx = WIDGET_W / 2
        bcy = GROUND_Y - BODY_RY * 0.9

        draw_leg(p, bcx - 14, GROUND_Y, 0, shorter=True)
        draw_leg(p, bcx + 14, GROUND_Y, 0, shorter=True)
        draw_tail(p, bcx - BODY_RX + 2, bcy + 4,
                  curl=0.75, base_angle=200)
        draw_body(p, bcx, bcy, rx=BODY_RX * 0.88, ry=BODY_RY * 1.1)

        # Head turns to look back at body — position shifts left & down
        progress = min(f / 3.0, 1.0)          # 0→1 as head turns
        hx = bcx + BODY_RX * 0.3 - progress * BODY_RX * 0.55
        hy = bcy - BODY_RY * 1.15 + progress * 12

        # Draw head facing backwards
        draw_head(p, hx, hy, eye_open=0.6, look_back=(progress > 0.5))

        # Tongue licking body (visible on frames 2–6)
        if 2 <= f <= 6:
            lick_bob = math.sin(f * 1.5) * 2
            draw_tongue(p, hx - 8, hy + HEAD_R + 2 + lick_bob,
                        size=4 + abs(lick_bob))

    # ------------------------------------------------------------------
    #  SLEEP  (4 frames — curled, breathing)
    # ------------------------------------------------------------------
    def _pose_sleep(self, p, f):
        breath = math.sin(f / 4.0 * math.pi) * 2
        bcx = WIDGET_W / 2
        bcy = GROUND_Y - BODY_RY * 0.65 + breath

        # Tail wraps around the front
        draw_tail(p, bcx + BODY_RX * 0.7, bcy + 6,
                  curl=0.95, base_angle=20)

        # Rounder curled body
        draw_body(p, bcx, bcy, rx=BODY_RX * 0.8,
                  ry=BODY_RY * 0.95, angle=-8)

        # Tiny tucked paws just visible at front
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(FUR_DARK))
        for dx in (-6, 6):
            p.drawEllipse(QPointF(bcx + BODY_RX * 0.55 + dx,
                                  bcy + BODY_RY * 0.5), 5, 4)

        # Head resting on paws
        hx = bcx + BODY_RX * 0.45
        hy = bcy - BODY_RY * 0.4 + breath
        draw_head(p, hx, hy, eye_open=0.0)     # eyes closed

        # "zzz" floating above
        if f % 2 == 0:
            p.setPen(QPen(QColor(120, 120, 180, 180), 1.5))
            zfont = QFont(".AppleSystemUIFont", 11)
            p.setFont(zfont)
            p.drawText(QPointF(hx + 18, hy - 22), "z")
            zfont.setPointSize(9)
            p.setFont(zfont)
            p.drawText(QPointF(hx + 28, hy - 32), "z")

    # ------------------------------------------------------------------
    #  PLAY  (6 frames — bouncy)
    # ------------------------------------------------------------------
    def _pose_play(self, p, f):
        t = f / 6.0
        ang = t * 2 * math.pi
        jump = abs(math.sin(ang)) * 15       # hop height
        bob = math.sin(ang * 2) * 2

        bcx = WIDGET_W / 2
        bcy = GROUND_Y - LEG_H - BODY_RY - jump

        draw_leg(p, bcx - BODY_RX + 14, GROUND_Y - jump * 0.4,
                 math.sin(ang) * 12)
        draw_leg(p, bcx + BODY_RX - 14, GROUND_Y - jump * 0.4,
                 math.sin(ang + math.pi) * 12)
        draw_tail(p, bcx - BODY_RX - 2, bcy,
                  curl=0.3 + 0.4 * abs(math.sin(ang)), base_angle=120)
        draw_body(p, bcx, bcy + bob)
        draw_leg(p, bcx - BODY_RX + 20, GROUND_Y - jump * 0.4,
                 math.sin(ang + math.pi) * 12)
        draw_leg(p, bcx + BODY_RX - 8, GROUND_Y - jump * 0.4,
                 math.sin(ang) * 12)
        hx = bcx + BODY_RX + HEAD_R * 0.45
        hy = bcy - BODY_RY * 0.55
        draw_head(p, hx, hy, eye_open=1.0)

    # ==================================================================
    #  Thought bubble (unchanged)
    # ==================================================================
    def _draw_thought(self, p, text):
        font = QFont(".AppleSystemUIFont", 13)
        p.setFont(font)
        metrics = QFontMetrics(font)
        tw = metrics.horizontalAdvance(text)
        th = metrics.height()
        px, py = 12, 6
        bw = tw + px * 2
        bh = th + py * 2
        bx = (WIDGET_W - bw) // 2
        by = 4
        p.setBrush(QBrush(QColor(255, 255, 255, 235)))
        p.setPen(QPen(QColor(80, 80, 80, 200), 1.4))
        p.drawRoundedRect(bx, by, bw, bh, 12, 12)
        tail_x = WIDGET_W // 2
        tail_y = by + bh
        p.setBrush(QBrush(QColor(255, 255, 255, 235)))
        p.drawPolygon([
            QPoint(tail_x - 6, tail_y - 1),
            QPoint(tail_x + 6, tail_y - 1),
            QPoint(tail_x,     tail_y + 8),
        ])
        p.setPen(QColor(40, 40, 40))
        p.drawText(QRect(bx, by, bw, bh), Qt.AlignCenter, text)

    # ==================================================================
    #  Tick
    # ==================================================================
    def _tick(self):
        if self.state == "run":
            self.frame_idx += 1
        elif self.state_ticks % 2 == 0:
            self.frame_idx += 1
        self.state_ticks += 1

        if self.thought_ticks > 0:
            self.thought_ticks -= 1
            if self.thought_ticks == 0:
                self.thought = None
        elif random.random() < 0.006:
            self.thought = random.choice(THOUGHTS)
            self.thought_ticks = 22

        if self.state == "curious":
            self._move_toward_cursor()
        else:
            self._move_horizontal()

        if self.state_ticks >= self.state_duration:
            self._transition()

        self.update()

    # ==================================================================
    #  Movement
    # ==================================================================
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
        cur = QCursor.pos()
        cx = self.x() + WIDGET_W // 2
        dx = cur.x() - cx
        if abs(dx) < 30:
            return
        speed = SPEEDS["curious"]
        step = max(-speed, min(speed, dx // 6))
        self.direction = 1 if step > 0 else -1
        nx = max(0, min(self.screen_rect.width() - WIDGET_W, self.x() + step))
        self.move(nx, self.y())

    def _transition(self):
        self.state          = random.choice(TRANSITIONS[self.state])
        self.frame_idx      = 0
        self.state_ticks    = 0
        self.state_duration = random.randint(*DURATIONS[self.state])
        if self.state in ("walk", "run") and random.random() < 0.35:
            self.direction *= -1

    # ==================================================================
    #  Mouse interaction
    # ==================================================================
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

    def _show_menu(self, pos):
        menu = QMenu(self)
        for label, state in [
            ("🐈   Walk",    "walk"),
            ("💨   Run",     "run"),
            ("😴   Sleep",   "sleep"),
            ("🐾   Play",    "play"),
            ("👀   Curious", "curious"),
            ("👅   Groom",   "groom"),
            ("🪑   Idle",    "idle"),
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
def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    _pet = DesktopPet()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
