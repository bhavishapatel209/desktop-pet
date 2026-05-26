# 🐱 Desktop Pet

A **smart floating cat** that lives on your macOS desktop. It walks across the screen, naps, plays, gets curious about your cursor, and even thinks in little speech bubbles.

![macOS](https://img.shields.io/badge/macOS-supported-success)
![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## ✨ Features

- 🐈 Floating, transparent, always-on-top cat — wanders your entire screen
- 🧠 **6 behaviors**: idle, walk, run, sleep, play, curious (follows cursor)
- 💬 Random thoughts shown in speech bubbles ("meow~", "snack?", "purr...")
- 🖱️ **Interactive** — drag with mouse, double-click to react, right-click for menu
- 🔄 Auto state transitions with weighted probabilities
- 🪶 Single Python file, fully customizable

## 🎮 Controls

| Action | Result |
|---|---|
| **Left-click + drag** | Pick up and move the cat |
| **Double-click** | Make the cat react |
| **Right-click** | Open menu (change state / quit) |

## 🚀 Quick Start

> **Requires:** Python 3.8+ on macOS

```bash
# 1. Clone the repo
git clone https://github.com/bhavishapatel209/desktop-pet.git
cd desktop-pet

# 2. Create a virtual environment & install dependencies
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

# 3. Run it
./venv/bin/python desktop_pet.py
```

Your cat will appear at the bottom of your screen and start wandering!

<details>
<summary><b>Can't see the cat? 🔍</b></summary>

The cat has a fully transparent background, so it can be hard to spot at first. Run it in debug mode — the widget will draw a bright red border around itself so you can locate it:

```bash
DESKTOP_PET_DEBUG=1 ./venv/bin/python desktop_pet.py
```

Once you spot it, run again without `DESKTOP_PET_DEBUG=1` for the clean look. You can also bump up `EMOJI_SIZE` in `desktop_pet.py` to make the cat bigger.

</details>

<details>
<summary><b>Why a virtual environment?</b></summary>

Modern macOS (with Homebrew Python) blocks system-wide `pip install` via [PEP 668](https://peps.python.org/pep-0668/) to prevent breaking your system. A virtual environment (`venv/`) keeps the project's dependencies isolated and avoids that error.

Prefer to activate the venv once and just type `python`?

```bash
source venv/bin/activate
python desktop_pet.py
```

</details>

## 🎬 States

| State | What it does | Avg. Duration |
|---|---|---|
| 🐱 Idle | Sits and blinks | ~5 s |
| 😺 Walk | Strolls horizontally | ~10–15 s |
| 💨 Run | Zooms across the screen | ~3–5 s |
| 😴 Sleep | Curls up for a nap | ~10–20 s |
| 😸 Play | Bounces around playfully | ~4–7 s |
| 😼 Curious | Walks toward your cursor | ~4–8 s |

The cat **picks states on its own** with weighted random transitions — but you can override it any time via right-click menu.

## 🛠️ Customization

Open `desktop_pet.py` and edit the top-level constants:

| Constant | Purpose |
|---|---|
| `FRAMES` | Emoji frames per state |
| `SPEEDS` | Movement speed (px/tick) per state |
| `DURATIONS` | How long each state lasts (in ticks) |
| `TRANSITIONS` | Weighted next-state choices |
| `THOUGHTS` | Random speech-bubble lines |
| `EMOJI_SIZE` | How big your cat appears |
| `TICK_MS` | Animation tick rate (lower = smoother) |

Want a dog instead of a cat? Just change the emoji in `FRAMES`. 🐶

## 📦 Make it a Standalone App (Optional)

To run it as a real `.app` that auto-starts at login:

```bash
./venv/bin/pip install py2app
./venv/bin/py2applet --make-setup desktop_pet.py
./venv/bin/python setup.py py2app
```

The packaged `.app` will be in `dist/`. Drag it to `/Applications` and add it to **System Settings → General → Login Items** to auto-start on boot.

## 🧩 How It Works

- Uses **PySide6** (Qt for Python) for a frameless, transparent, always-on-top window
- A `QTimer` ticks every 120 ms — advances frames, moves the pet, manages state
- The pet emoji is rendered with **Apple Color Emoji** and flipped via `QPainter` when it changes direction
- The widget itself is just `WIDGET_W × WIDGET_H` pixels — the rest of your screen stays clickable

## 📄 License

MIT
