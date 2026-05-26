#!/usr/bin/env python3
"""
🐱 Desktop Pet — A tiny cat that lives in your macOS menu bar!

States:
  walk  — strolls across the menu bar
  run   — zooms around with energy
  sleep — takes a cozy nap
  idle  — sits and blinks at you

Install: pip install rumps
Run:     python desktop_pet.py
"""

import rumps
import random


# ---------------------------------------------------------------------------
# Animation frames per state (shown as menu bar title)
# ---------------------------------------------------------------------------
FRAMES = {
    "walk":  ["🐱  ", " 🐱 ", "  🐱", "🐈  "],
    "run":   ["🐱💨 ", "💨🐱 ", " 🐱💨", "🏃🐱"],
    "sleep": ["😴    ", " 💤   ", "😴 z  ", " 💤 z "],
    "idle":  ["🐱", "😺", "🐱", "😼"],
}

# How many seconds each state lasts before auto-transitioning (min, max)
STATE_DURATION = {
    "walk":  (18, 35),
    "run":   (5,  12),
    "sleep": (15, 30),
    "idle":  (6,  14),
}

# Weighted next-state choices (more weight = more likely)
TRANSITIONS = {
    "walk":  ["walk", "walk", "idle", "run", "sleep"],
    "run":   ["walk", "walk", "idle"],
    "sleep": ["sleep", "idle", "idle", "walk"],
    "idle":  ["walk", "walk", "walk", "run", "sleep"],
}

# Animation tick speed in seconds
TICK = 0.35


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
class DesktopPet(rumps.App):

    def __init__(self):
        super().__init__("🐱", quit_button=None)

        self._state    = "idle"
        self._frame    = 0
        self._elapsed  = 0.0
        self._duration = self._random_duration("idle")

        self.menu = [
            rumps.MenuItem("😺   Walk",  callback=lambda _: self._set_state("walk")),
            rumps.MenuItem("💨   Run",   callback=lambda _: self._set_state("run")),
            rumps.MenuItem("😴   Sleep", callback=lambda _: self._set_state("sleep")),
            rumps.MenuItem("😼   Idle",  callback=lambda _: self._set_state("idle")),
            None,
            rumps.MenuItem("Quit", callback=rumps.quit_application),
        ]

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------
    def _random_duration(self, state: str) -> float:
        lo, hi = STATE_DURATION[state]
        return float(random.randint(lo, hi))

    def _set_state(self, state: str):
        self._state    = state
        self._frame    = 0
        self._elapsed  = 0.0
        self._duration = self._random_duration(state)

    # ------------------------------------------------------------------
    # Main tick — fires every TICK seconds
    # ------------------------------------------------------------------
    @rumps.timer(TICK)
    def _tick(self, _):
        frames = FRAMES[self._state]
        self.title = frames[self._frame % len(frames)]
        self._frame   += 1
        self._elapsed += TICK

        # Auto-transition when the current state's time is up
        if self._elapsed >= self._duration:
            next_state = random.choice(TRANSITIONS[self._state])
            self._set_state(next_state)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    DesktopPet().run()
