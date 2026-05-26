#!/usr/bin/env python3
"""
✈️ Meeting Flyby — A cute airplane that flies across your screen
to remind you about upcoming meetings!

Reads from:
  • macOS Calendar  (automatic — uses AppleScript, no extra deps)
  • Google Calendar  (optional — drop a credentials.json next to this file)

Run:
    ./venv/bin/python meeting_flyby.py

The app sits quietly in your menu bar (✈️ icon). Every 60 seconds it checks
your calendars.  When a meeting is ~5 minutes away, a cartoon airplane tows
a banner with the meeting name & time across your screen.

Google Calendar setup (optional):
  1. Go to https://console.cloud.google.com
  2. Create a project → enable "Google Calendar API"
  3. Create OAuth 2.0 credentials (Desktop app)
  4. Download the JSON and save it as  credentials.json  next to this file
  5. On first run, a browser window opens for you to authorize — then it's
     remembered in  token.json.
"""

import os
import sys
import math
import subprocess
import threading
from datetime import datetime, timedelta
from dataclasses import dataclass, field

from PySide6.QtCore import Qt, QTimer, QPointF, QRectF
from PySide6.QtGui import (
    QPainter,
    QColor,
    QPen,
    QBrush,
    QPainterPath,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QIcon,
    QPixmap,
    QAction,
    QTransform,
)
from PySide6.QtWidgets import QApplication, QWidget, QSystemTrayIcon, QMenu

# ---------------------------------------------------------------------------
# Optional: Google Calendar API
# ---------------------------------------------------------------------------
try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    _HAS_GOOGLE = True
except ImportError:
    _HAS_GOOGLE = False

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
POLL_SECONDS = 60  # how often to check calendars
REMIND_AHEAD_MIN = 5  # notify when meeting is this many minutes away
FLYBY_SPEED = 4  # px per animation tick
FLYBY_TICK_MS = 25  # animation frame interval
WIDGET_H = 170  # flyby strip height
FLYBY_SOUND = "/System/Library/Sounds/Hero.aiff"  # played when flyby starts

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------
BODY_WHITE = QColor(245, 248, 255)
BODY_GREY = QColor(200, 210, 225)
WING_BLUE = QColor(100, 160, 220)
WING_DARK = QColor(70, 120, 180)
NOSE_RED = QColor(230, 80, 80)
TAIL_RED = QColor(220, 70, 70)
WINDOW_CLR = QColor(60, 140, 220)
WINDOW_HI = QColor(180, 220, 255)
BANNER_BG = QColor(255, 255, 240)
BANNER_BRD = QColor(220, 180, 100)
ROPE_CLR = QColor(180, 140, 90, 200)
OUTLINE = QColor(60, 75, 100, 120)
CLOUD_CLR = QColor(255, 255, 255, 110)
TEXT_CLR = QColor(55, 55, 65)


# ╔═════════════════════════════════════════════════════════════════════════╗
# ║  DATA                                                                  ║
# ╚═════════════════════════════════════════════════════════════════════════╝


@dataclass
class Meeting:
    name: str
    start: datetime
    source: str = ""  # "macos" or "google"

    @property
    def uid(self) -> str:
        return f"{self.name}|{self.start.strftime('%Y%m%d%H%M')}"

    @property
    def time_str(self) -> str:
        return self.start.strftime("%-I:%M %p")

    @property
    def banner_text(self) -> str:
        mins = max(1, round((self.start - datetime.now()).total_seconds() / 60))
        return f"{self.name}  •  in {mins} min  •  {self.time_str}"


# ╔═════════════════════════════════════════════════════════════════════════╗
# ║  CALENDAR SOURCES                                                      ║
# ╚═════════════════════════════════════════════════════════════════════════╝


_CAL_HELPER_SRC = os.path.join(BASE_DIR, "cal_helper.swift")
_CAL_HELPER_BIN = os.path.join(BASE_DIR, ".cal_helper")
_cal_helper_ready: bool | None = None  # cached compilation status
_cal_access_warned = False              # only print the permission hint once


def _ensure_cal_helper() -> bool:
    """Compile the Swift EventKit helper once. Returns True if binary is ready."""
    global _cal_helper_ready
    if _cal_helper_ready is not None:
        return _cal_helper_ready

    # Already compiled and source hasn't changed?
    if os.path.exists(_CAL_HELPER_BIN) and os.path.exists(_CAL_HELPER_SRC):
        if os.path.getmtime(_CAL_HELPER_SRC) <= os.path.getmtime(_CAL_HELPER_BIN):
            _cal_helper_ready = True
            return True

    if not os.path.exists(_CAL_HELPER_SRC):
        print("[Flyby] cal_helper.swift not found — using fallback", file=sys.stderr, flush=True)
        _cal_helper_ready = False
        return False

    print("[Flyby] Compiling calendar helper (one-time)…", file=sys.stderr, flush=True)
    try:
        result = subprocess.run(
            ["swiftc", _CAL_HELPER_SRC, "-o", _CAL_HELPER_BIN,
             "-framework", "EventKit", "-framework", "Foundation"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            print(f"[Flyby] Swift compile failed: {result.stderr.strip()}", file=sys.stderr, flush=True)
            _cal_helper_ready = False
            return False
        print("[Flyby] Calendar helper compiled ✓", file=sys.stderr, flush=True)
        _cal_helper_ready = True
        return True
    except Exception as e:
        print(f"[Flyby] Swift compile error: {e}", file=sys.stderr, flush=True)
        _cal_helper_ready = False
        return False


def _parse_event_lines(output: str, source: str) -> list[Meeting]:
    """Parse 'Title||YYYY-MM-DD HH:MM' lines into Meeting objects."""
    events: list[Meeting] = []
    for line in output.strip().split("\n"):
        if "||" not in line:
            continue
        name, dt_str = line.rsplit("||", 1)
        try:
            dt = datetime.strptime(dt_str.strip(), "%Y-%m-%d %H:%M")
            events.append(Meeting(name.strip(), dt, source))
        except ValueError:
            pass
    return events


def get_macos_events(minutes_ahead: int = 10) -> list[Meeting]:
    """Query macOS Calendar — uses compiled Swift EventKit helper (fast),
    falls back to Calendar.app JXA scripting if compilation isn't available."""
    if _ensure_cal_helper():
        try:
            result = subprocess.run(
                [_CAL_HELPER_BIN, str(minutes_ahead)],
                capture_output=True, text=True, timeout=10,
            )
            if "NO_CALENDAR_ACCESS" in result.stderr:
                global _cal_access_warned
                if not _cal_access_warned:
                    _cal_access_warned = True
                    print(
                        "[Flyby] Swift helper lacks calendar access — "
                        "falling back to Calendar.app.\n"
                        "        (Grant in: System Settings → Privacy & Security → Calendars"
                        " to use the faster helper)",
                        file=sys.stderr, flush=True,
                    )
                # Fall through to JXA — Calendar.app has its own access
            else:
                return _parse_event_lines(result.stdout, "macos")
        except Exception as e:
            print(f"[Flyby] Calendar helper error: {e}", file=sys.stderr, flush=True)

    # ── Fallback: Calendar.app JXA scripting ──────────────────────
    return _get_macos_events_jxa(minutes_ahead)


def _get_macos_events_jxa(minutes_ahead: int = 10) -> list[Meeting]:
    """Fallback: query Calendar.app via JXA (slower — uses whose clause)."""
    script = (
        "var Cal = Application('Calendar');\n"
        "var now = new Date();\n"
        "var later = new Date(now.getTime() + %d * 60 * 1000);\n"
        "var cals = Cal.calendars();\n"
        "var lines = [];\n"
        "for (var c = 0; c < cals.length; c++) {\n"
        "  try {\n"
        "    var evts = cals[c].events.whose({\n"
        "      _and: [{startDate: {_greaterThanEquals: now}},\n"
        "             {startDate: {_lessThanEquals: later}}]\n"
        "    })();\n"
        "    for (var j = 0; j < evts.length; j++) {\n"
        "      try {\n"
        "        if (evts[j].alldayEvent()) continue;\n"
        "        var d = evts[j].startDate();\n"
        "        var title = evts[j].summary();\n"
        "        var y = d.getFullYear();\n"
        "        var mo = String(d.getMonth()+1).padStart(2,'0');\n"
        "        var dy = String(d.getDate()).padStart(2,'0');\n"
        "        var h = String(d.getHours()).padStart(2,'0');\n"
        "        var mi = String(d.getMinutes()).padStart(2,'0');\n"
        "        lines.push(title+'||'+y+'-'+mo+'-'+dy+' '+h+':'+mi);\n"
        "      } catch(e2) {}\n"
        "    }\n"
        "  } catch(e) {}\n"
        "}\n"
        "lines.join('\\n');\n"
    ) % minutes_ahead
    try:
        result = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", script],
            capture_output=True, text=True, timeout=8,
        )
        return _parse_event_lines(result.stdout, "macos")
    except subprocess.TimeoutExpired:
        print("[Flyby] Calendar.app query slow — skipping this poll", file=sys.stderr, flush=True)
        return []
    except Exception as e:
        print(f"[Flyby] Calendar.app fallback error: {e}", file=sys.stderr, flush=True)
        return []


def get_google_events(minutes_ahead: int = 10) -> list[Meeting]:
    """Query Google Calendar API. Returns [] if not configured."""
    if not _HAS_GOOGLE:
        return []

    creds_path = os.path.join(BASE_DIR, "credentials.json")
    token_path = os.path.join(BASE_DIR, "token.json")

    if not os.path.exists(creds_path):
        return []  # not configured — silently skip

    SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None
        if not creds:
            try:
                flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
                creds = flow.run_local_server(port=0)
            except Exception as e:
                print(f"[Flyby] Google auth error: {e}", file=sys.stderr, flush=True)
                return []
        with open(token_path, "w") as f:
            f.write(creds.to_json())

    try:
        service = build("calendar", "v3", credentials=creds)
        now_utc = datetime.utcnow()
        later_utc = now_utc + timedelta(minutes=minutes_ahead)

        result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=now_utc.isoformat() + "Z",
                timeMax=later_utc.isoformat() + "Z",
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events: list[Meeting] = []
        for item in result.get("items", []):
            start_raw = item["start"].get("dateTime")
            if not start_raw:  # all-day event — skip
                continue
            name = item.get("summary", "Meeting")
            dt = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
            dt = dt.astimezone().replace(tzinfo=None)  # to local naive
            events.append(Meeting(name, dt, "google"))
        return events
    except Exception as e:
        print(f"[Flyby] Google calendar error: {e}", file=sys.stderr, flush=True)
        return []


# ╔═════════════════════════════════════════════════════════════════════════╗
# ║  AIRPLANE DRAWING HELPERS                                              ║
# ╚═════════════════════════════════════════════════════════════════════════╝


def _outline_pen(w: float = 1.5) -> QPen:
    return QPen(OUTLINE, w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)


def draw_airplane(p: QPainter, ax: float, ay: float):
    """Draw the cute cartoon airplane centered at (ax, ay)."""
    body_w, body_h = 80, 28

    # --- Tail fin (vertical, red) ---
    p.setPen(_outline_pen(1.2))
    p.setBrush(QBrush(TAIL_RED))
    tail = QPainterPath()
    tail.moveTo(ax - body_w / 2, ay - body_h / 3)
    tail.lineTo(ax - body_w / 2 - 8, ay - body_h / 2 - 20)
    tail.lineTo(ax - body_w / 2 + 14, ay - body_h / 2 - 2)
    tail.closeSubpath()
    p.drawPath(tail)

    # --- Tail stabiliser (horizontal, blue) ---
    p.setBrush(QBrush(WING_BLUE))
    htail = QPainterPath()
    htail.moveTo(ax - body_w / 2 + 2, ay)
    htail.lineTo(ax - body_w / 2 - 14, ay - 8)
    htail.lineTo(ax - body_w / 2 - 14, ay + 2)
    htail.lineTo(ax - body_w / 2 + 2, ay + 4)
    htail.closeSubpath()
    p.drawPath(htail)

    # --- Wings ---
    wing_grad = QLinearGradient(ax, ay - body_h, ax, ay - body_h - 18)
    wing_grad.setColorAt(0.0, WING_BLUE)
    wing_grad.setColorAt(1.0, WING_DARK)
    p.setBrush(QBrush(wing_grad))
    for sign, wy_off, wh in [(-1, -body_h / 2 + 2, -18), (1, body_h / 2 - 2, 14)]:
        wing = QPainterPath()
        wing.moveTo(ax - 10, ay + wy_off)
        wing.lineTo(ax + 20, ay + wy_off + wh * sign if sign == -1 else ay + wy_off + wh)
        wing.lineTo(ax - 25, ay + wy_off + (wh - 6) * sign if sign == -1 else ay + wy_off + wh - 4)
        wing.closeSubpath()
        p.drawPath(wing)
    # Re-draw top wing properly
    p.setBrush(QBrush(wing_grad))
    wt = QPainterPath()
    wt.moveTo(ax - 10, ay - body_h / 2 + 2)
    wt.lineTo(ax + 20, ay - body_h / 2 - 18)
    wt.lineTo(ax - 25, ay - body_h / 2 - 12)
    wt.closeSubpath()
    p.drawPath(wt)
    # Bottom wing
    p.setBrush(QBrush(WING_BLUE))
    wb = QPainterPath()
    wb.moveTo(ax - 10, ay + body_h / 2 - 2)
    wb.lineTo(ax + 20, ay + body_h / 2 + 14)
    wb.lineTo(ax - 25, ay + body_h / 2 + 10)
    wb.closeSubpath()
    p.drawPath(wb)

    # --- Fuselage ---
    body_grad = QLinearGradient(ax, ay - body_h / 2, ax, ay + body_h / 2)
    body_grad.setColorAt(0.0, BODY_WHITE)
    body_grad.setColorAt(0.7, BODY_GREY)
    p.setBrush(QBrush(body_grad))
    p.setPen(_outline_pen())
    body = QPainterPath()
    body.moveTo(ax + body_w / 2 + 12, ay)
    body.cubicTo(
        ax + body_w / 2 + 12, ay - body_h / 2,
        ax + body_w / 4, ay - body_h / 2,
        ax - body_w / 3, ay - body_h / 2,
    )
    body.lineTo(ax - body_w / 2, ay - body_h / 3)
    body.lineTo(ax - body_w / 2, ay + body_h / 3)
    body.lineTo(ax - body_w / 3, ay + body_h / 2)
    body.cubicTo(
        ax + body_w / 4, ay + body_h / 2,
        ax + body_w / 2 + 12, ay + body_h / 2,
        ax + body_w / 2 + 12, ay,
    )
    body.closeSubpath()
    p.drawPath(body)

    # --- Nose cone (red) ---
    p.setBrush(QBrush(NOSE_RED))
    p.setPen(_outline_pen(1.2))
    nose = QPainterPath()
    nose.moveTo(ax + body_w / 2 + 12, ay)
    nose.cubicTo(
        ax + body_w / 2 + 18, ay - 6,
        ax + body_w / 2 + 22, ay - 3,
        ax + body_w / 2 + 24, ay,
    )
    nose.cubicTo(
        ax + body_w / 2 + 22, ay + 3,
        ax + body_w / 2 + 18, ay + 6,
        ax + body_w / 2 + 12, ay,
    )
    p.drawPath(nose)

    # --- Windows ---
    p.setPen(Qt.NoPen)
    for i in range(5):
        wx = ax - 12 + i * 10
        wy = ay - 3
        p.setBrush(QBrush(WINDOW_CLR))
        p.drawEllipse(QPointF(wx, wy), 3.5, 4)
        p.setBrush(QBrush(WINDOW_HI))
        p.drawEllipse(QPointF(wx - 0.8, wy - 1.2), 1.5, 1.8)

    # --- Propeller (blurred disc) ---
    pcx = ax + body_w / 2 + 24
    p.setBrush(QBrush(QColor(180, 185, 190, 100)))
    p.drawEllipse(QPointF(pcx, ay), 4, 18)
    p.setBrush(QBrush(QColor(160, 165, 170, 160)))
    p.drawEllipse(QPointF(pcx, ay), 2.5, 16)
    p.setBrush(QBrush(QColor(80, 85, 90)))
    p.drawEllipse(QPointF(pcx, ay), 3, 3)


def draw_banner(p: QPainter, ax: float, ay: float, text: str, banner_w: float):
    """Draw the towed banner BEHIND the airplane (to its left, since it flies right)."""
    rope_sx = ax - 50           # rope attaches at the tail (left side)
    rope_sy = ay + 8
    banner_x = rope_sx - banner_w - 15   # banner trails to the left
    banner_y = ay + 15
    banner_h = 50

    # Rope from tail to banner's right edge
    p.setPen(QPen(ROPE_CLR, 2.5, Qt.SolidLine, Qt.RoundCap))
    p.setBrush(Qt.NoBrush)
    rope = QPainterPath()
    rope.moveTo(rope_sx, rope_sy)
    rope.quadTo(rope_sx - 20, rope_sy + 25, banner_x + banner_w, banner_y + banner_h / 2)
    p.drawPath(rope)

    # Banner shape (slight wave)
    bp = QPainterPath()
    bp.moveTo(banner_x, banner_y)
    segs = 5
    for i in range(1, segs + 1):
        bx = banner_x + banner_w * i / segs
        by = banner_y + math.sin(i * 0.8) * 3
        bp.lineTo(bx, by)
    bp.lineTo(banner_x + banner_w, banner_y + banner_h)
    for i in range(segs, 0, -1):
        bx = banner_x + banner_w * (i - 1) / segs
        by = banner_y + banner_h + math.sin(i * 0.8) * 3
        bp.lineTo(bx, by)
    bp.closeSubpath()

    # Shadow
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor(0, 0, 0, 22)))
    p.drawPath(bp.translated(3, 3))

    # Fill + border
    p.setBrush(QBrush(BANNER_BG))
    p.setPen(QPen(BANNER_BRD, 1.8))
    p.drawPath(bp)

    # Text
    p.setPen(TEXT_CLR)
    font = QFont(".AppleSystemUIFont", 15, QFont.Bold)
    p.setFont(font)
    p.drawText(
        QRectF(banner_x + 8, banner_y, banner_w - 16, banner_h),
        Qt.AlignVCenter | Qt.AlignLeft,
        f"✈️  {text}",
    )


def draw_clouds(p: QPainter, ax: float, ay: float):
    """Little exhaust puffs trailing behind the airplane (to its left)."""
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(CLOUD_CLR))
    for dx, dy, r in [(-65, 5, 10), (-80, 2, 7), (-72, 10, 8), (-90, 6, 6)]:
        p.drawEllipse(QPointF(ax + dx, ay + dy), r, r * 0.7)


# ╔═════════════════════════════════════════════════════════════════════════╗
# ║  FLYBY ANIMATION WIDGET                                               ║
# ╚═════════════════════════════════════════════════════════════════════════╝


class FlybyWidget(QWidget):
    """Full-screen-width transparent strip; airplane + banner fly across."""

    def __init__(self, screen_rect, text: str):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.SplashScreen
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_AlwaysStackOnTop)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self.screen_w = screen_rect.width()
        self.resize(self.screen_w, WIDGET_H)
        self.move(screen_rect.x(), screen_rect.y() + 50)

        self.text = text

        # Measure banner width from text
        font = QFont(".AppleSystemUIFont", 15, QFont.Bold)
        fm = QFontMetrics(font)
        self.banner_w = max(fm.horizontalAdvance(f"✈️  {text}") + 40, 260)

        # Load airplane image as-is (already faces the right direction)
        self._airplane_pm = QPixmap()
        img_path = os.path.join(BASE_DIR, "assets", "airplane.png")
        if os.path.exists(img_path):
            pm = QPixmap(img_path)
            if not pm.isNull():
                self._airplane_pm = pm.scaledToHeight(
                    120, Qt.SmoothTransformation
                )
        self._plane_w = self._airplane_pm.width() if not self._airplane_pm.isNull() else 130
        self._plane_h = self._airplane_pm.height() if not self._airplane_pm.isNull() else 80

        # Total width the animation occupies
        self.total_w = self._plane_w + 55 + self.banner_w

        # Start off-screen left (plane faces right, flies L→R)
        self.airplane_x = float(-self.total_w - 60)
        self._done_callback = None

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def fly(self, on_done=None):
        self._done_callback = on_done
        self.airplane_x = float(-self.total_w - 60)
        self.show()
        self.raise_()
        self._timer.start(FLYBY_TICK_MS)
        # Play a chime so the user looks up
        if os.path.exists(FLYBY_SOUND):
            subprocess.Popen(
                ["afplay", FLYBY_SOUND],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

    def _tick(self):
        self.airplane_x += FLYBY_SPEED          # fly left → right
        if self.airplane_x > self.screen_w + 80:
            self._timer.stop()
            self.hide()
            if self._done_callback:
                self._done_callback()
            return
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        ax = self.airplane_x
        ay = 60.0

        # Draw back-to-front: banner → clouds → airplane
        draw_banner(p, ax, ay, self.text, self.banner_w)
        draw_clouds(p, ax, ay)

        if not self._airplane_pm.isNull():
            # Draw the cute watercolour airplane image
            px = int(ax - self._plane_w / 2)
            py = int(ay - self._plane_h / 2)
            p.drawPixmap(px, py, self._airplane_pm)
        else:
            draw_airplane(p, ax, ay)  # fallback to vector


# ╔═════════════════════════════════════════════════════════════════════════╗
# ║  MEETING REMINDER SERVICE                                              ║
# ╚═════════════════════════════════════════════════════════════════════════╝


class MeetingFlybyApp:
    """Background service: poll calendars, trigger flyby animations."""

    def __init__(self):
        self._notified: set[str] = set()
        self._queue: list[Meeting] = []
        self._flyby: FlybyWidget | None = None

        self._screen = QApplication.primaryScreen().availableGeometry()

        # Periodic polling timer
        self._poll_timer = QTimer()
        self._poll_timer.timeout.connect(self._poll)
        self._poll_timer.start(POLL_SECONDS * 1000)

        # First poll after a short delay (let UI settle)
        QTimer.singleShot(3000, self._poll)

        # --- System-tray icon (menu-bar on macOS) ---
        self._tray = QSystemTrayIcon()
        self._tray.setToolTip("Meeting Flyby ✈️")
        # Tiny airplane icon
        px = QPixmap(32, 32)
        px.fill(Qt.transparent)
        tp = QPainter(px)
        tp.setRenderHint(QPainter.Antialiasing)
        tp.setPen(Qt.NoPen)
        tp.setBrush(QBrush(QColor(100, 160, 220)))
        tp.drawEllipse(2, 2, 28, 28)
        tp.setPen(QPen(QColor(255, 255, 255), 2))
        font = QFont(".AppleSystemUIFont", 16)
        tp.setFont(font)
        tp.drawText(QRectF(0, 0, 32, 32), Qt.AlignCenter, "✈")
        tp.end()
        self._tray.setIcon(QIcon(px))

        tray_menu = QMenu()
        tray_menu.addAction("Check now", self._poll)
        tray_menu.addAction("Test flyby", self._test_flyby)
        tray_menu.addSeparator()
        status = "Google Calendar: " + ("✅ configured" if _HAS_GOOGLE and os.path.exists(os.path.join(BASE_DIR, "credentials.json")) else "not configured")
        act = tray_menu.addAction(status)
        act.setEnabled(False)
        tray_menu.addSeparator()
        tray_menu.addAction("Quit", QApplication.quit)
        self._tray.setContextMenu(tray_menu)
        self._tray.show()

        print(
            f"[Flyby] running — polling every {POLL_SECONDS}s, "
            f"reminding {REMIND_AHEAD_MIN} min before meetings. "
            f"Google Calendar: {'YES' if _HAS_GOOGLE else 'NO (install google-api-python-client)'}",
            file=sys.stderr,
            flush=True,
        )

    # ------------------------------------------------------------------

    def _poll(self):
        """Kick off calendar queries on a background thread (don't block UI)."""
        threading.Thread(target=self._poll_bg, daemon=True).start()

    def _poll_bg(self):
        """Background thread: fetch calendar events, then schedule UI work."""
        events = get_macos_events(REMIND_AHEAD_MIN + 2)
        events.extend(get_google_events(REMIND_AHEAD_MIN + 2))
        # Hand results back to the main/UI thread via a single-shot timer
        self._bg_events = events
        QTimer.singleShot(0, self._process_poll_results)

    def _process_poll_results(self):
        """Main-thread: process events gathered by the background poll."""
        now = datetime.now()
        events = getattr(self, "_bg_events", [])

        new_count = 0
        for evt in events:
            if evt.uid in self._notified:
                continue
            mins_until = (evt.start - now).total_seconds() / 60
            if 0 < mins_until <= REMIND_AHEAD_MIN + 0.5:
                self._notified.add(evt.uid)
                self._queue.append(evt)
                new_count += 1

        if new_count:
            print(
                f"[Flyby] {new_count} new meeting(s) queued",
                file=sys.stderr,
                flush=True,
            )

        # Clean old notifications (>1 hour old)
        cutoff = now - timedelta(hours=1)
        self._notified = {
            uid
            for uid in self._notified
            if uid.split("|")[-1] > cutoff.strftime("%Y%m%d%H%M")
        }

        # Trigger flyby if not already animating
        if self._queue and not (self._flyby and self._flyby.isVisible()):
            self._fly_next()

    def _fly_next(self):
        if not self._queue:
            return
        evt = self._queue.pop(0)
        text = evt.banner_text
        print(f"[Flyby] ✈️  {text}", file=sys.stderr, flush=True)
        self._flyby = FlybyWidget(self._screen, text)
        self._flyby.fly(on_done=self._fly_next)

    def _test_flyby(self):
        """Menu action: trigger a test flyby with a fake meeting."""
        test_time = datetime.now() + timedelta(minutes=5)
        test_evt = Meeting("Test Meeting — it works!", test_time, "test")
        self._queue.append(test_evt)
        if not (self._flyby and self._flyby.isVisible()):
            self._fly_next()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # keep running in background
    _reminder = MeetingFlybyApp()

    # --test flag: auto-trigger a test flyby 2 seconds after launch
    if "--test" in sys.argv:
        QTimer.singleShot(2000, _reminder._test_flyby)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
