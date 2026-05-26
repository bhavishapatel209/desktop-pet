# 🐱 Desktop Pet

A tiny animated cat that lives in your **macOS menu bar** — walks, runs, sleeps, and idles on its own.

![macOS](https://img.shields.io/badge/macOS-supported-success)
![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## 📺 Preview

![Demo](assets/demo.svg)

> 💡 **Want to add your own screenshot?** Run the app, take a screenshot of your menu bar with `⌘ + Shift + 4`, save it as `assets/screenshot.png`, and reference it here.

## ✨ Features

- 🐈 Animated cat in your menu bar
- 😴 Auto-transitions between **walk**, **run**, **sleep**, and **idle** states
- 🎛️ Manual override via menu click
- 🪶 Lightweight — single Python file, ~80 lines

## 🚀 Quick Start

```bash
# 1. Install dependency
pip install rumps

# 2. Run it
python desktop_pet.py
```

Your cat will appear in the menu bar. Click it to control state or quit.

## 🎬 States

| State | Animation | Avg. Duration |
|---|---|---|
| 😺 Walk | `🐱 → 🐱 → 🐱` | ~25s |
| 💨 Run | `🐱💨 → 💨🐱` | ~8s |
| 😴 Sleep | `😴 → 💤 → 😴 z` | ~22s |
| 😼 Idle | `🐱 → 😺 → 😼` | ~10s |

## 🛠️ Customization

Open `desktop_pet.py` and edit:

- `FRAMES` — animation frames per state
- `STATE_DURATION` — how long each state lasts (in seconds)
- `TRANSITIONS` — weighted next-state probabilities
- `TICK` — animation speed (lower = faster)

## 📦 Make it a Standalone App (Optional)

To run it as a real `.app` that auto-starts at login:

```bash
pip install py2app
py2applet --make-setup desktop_pet.py
python setup.py py2app
```

## 📄 License

MIT
