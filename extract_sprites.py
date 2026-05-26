"""
Helper: Extract individual frames from the downloaded CC0 cat sprite GIFs
into assets/sprites/frames/*.png so the pet app can load them as QPixmap.

Also removes the solid purple background that the source sprites ship with
and replaces it with transparency.

Run once after downloading the source GIFs:
    ./venv/bin/python extract_sprites.py
"""

import os
from PIL import Image

SRC_DIR = "assets/sprites/cat sprite"
OUT_DIR = "assets/sprites/frames"

os.makedirs(OUT_DIR, exist_ok=True)


# The CC0 cat sprite by Shepardskin uses a lavender / dusty-purple background.
# We remove any pixel close to this color (within a small RGB distance).
BG_COLORS = [
    (174, 142, 174),   # lavender body of the sheet
    (152, 124, 154),   # slight darker variant seen on some GIFs
]
BG_TOLERANCE = 28      # how close (in max-channel-diff) counts as background


def _is_bg(r: int, g: int, b: int) -> bool:
    for br, bg_, bb in BG_COLORS:
        if (
            abs(r - br) <= BG_TOLERANCE
            and abs(g - bg_) <= BG_TOLERANCE
            and abs(b - bb) <= BG_TOLERANCE
        ):
            return True
    return False


def remove_background(img: Image.Image) -> Image.Image:
    """Return a new RGBA image with background pixels turned transparent."""
    img = img.convert("RGBA")
    pixels = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            if _is_bg(r, g, b):
                pixels[x, y] = (0, 0, 0, 0)
    return img


# ---------------------------------------------------------------------------
# Recolor: black/grey cat -> orange tabby
# ---------------------------------------------------------------------------
# Gradient used to remap body pixel luminance to an orange palette.
# (deep-shadow → mid-fur → highlight)  — picked to look like a ginger cat
ORANGE_STOPS = [
    (0,    (70,  25,  10)),   # darkest shadow
    (60,   (150, 60,  20)),   # shadow
    (110,  (215, 110, 35)),   # mid orange
    (170,  (245, 160, 70)),   # bright orange
    (220,  (255, 205, 130)),  # highlight
    (255,  (255, 240, 200)),  # whisker / belly highlight
]
# Original sprite is quite dark (most fur ~lum 40–90), so boost luminance
# before mapping so the body lands in the vivid-orange band of the gradient.
LUM_BOOST = 2.4


def _interp(a, b, t: float):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _orange_for_lum(lum: int) -> tuple[int, int, int]:
    for i in range(len(ORANGE_STOPS) - 1):
        l0, c0 = ORANGE_STOPS[i]
        l1, c1 = ORANGE_STOPS[i + 1]
        if l0 <= lum <= l1:
            t = 0.0 if l1 == l0 else (lum - l0) / (l1 - l0)
            return _interp(c0, c1, t)
    return ORANGE_STOPS[-1][1]


def recolor_to_orange(img: Image.Image) -> Image.Image:
    """
    Remap the dark/desaturated cat fur to an orange gradient. Highly saturated
    pixels (the green eyes, the pink ear interior) are preserved so the cat
    keeps its character.
    """
    img = img.convert("RGBA")
    pixels = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            if a == 0:
                continue
            mx, mn = max(r, g, b), min(r, g, b)
            sat = mx - mn
            # Saturated accents (eyes, ear pink) → leave alone
            if sat > 35:
                continue
            # Body pixel — map (boosted) luminance onto the orange gradient
            lum = (r * 30 + g * 59 + b * 11) // 100
            lum = min(255, int(lum * LUM_BOOST))
            nr, ng, nb = _orange_for_lum(lum)
            pixels[x, y] = (nr, ng, nb, a)
    return img


def save_gif_frames(gif_path: str, name_prefix: str):
    """Extract every frame of an animated GIF as <prefix>_<i>.png (bg removed)."""
    img = Image.open(gif_path)
    i = 0
    try:
        while True:
            frame = recolor_to_orange(remove_background(img))
            out_path = os.path.join(OUT_DIR, f"{name_prefix}_{i}.png")
            frame.save(out_path)
            i += 1
            img.seek(img.tell() + 1)
    except EOFError:
        pass
    print(f"  {gif_path:55s} -> {i} frames as {name_prefix}_*.png")


def save_sheet_cells(
    sheet_path: str,
    name_prefix: str,
    cells: list[tuple[int, int, int, int]],
):
    """Extract specific (x, y, w, h) rectangles from a sprite sheet (bg removed)."""
    img = Image.open(sheet_path).convert("RGBA")
    img = remove_background(img)
    for i, (x, y, w, h) in enumerate(cells):
        cell = img.crop((x, y, x + w, y + h))
        out_path = os.path.join(OUT_DIR, f"{name_prefix}_{i}.png")
        cell.save(out_path)
    print(f"  {sheet_path:55s} -> {len(cells)} cells as {name_prefix}_*.png")


def autoslice_row(
    sheet_path: str,
    name_prefix: str,
    y_top: int,
    y_bot: int,
    min_gap: int = 3,
    pad: int = 2,
):
    """
    Auto-detect sprite columns in a sprite-sheet row by scanning for vertical
    gaps (columns with NO opaque pixels in y_top..y_bot). Each contiguous run
    of "opaque" columns becomes one frame.
    """
    img = Image.open(sheet_path).convert("RGBA")
    img = recolor_to_orange(remove_background(img))
    pixels = img.load()
    w, h = img.size
    y_bot = min(y_bot, h)

    # Column occupancy: True if any opaque pixel in the band.
    col_has = [False] * w
    for x in range(w):
        for y in range(y_top, y_bot):
            if pixels[x, y][3] > 16:
                col_has[x] = True
                break

    # Find contiguous runs of occupied columns separated by >= min_gap empties.
    runs: list[tuple[int, int]] = []
    in_run = False
    start = 0
    gap = 0
    for x in range(w):
        if col_has[x]:
            if not in_run:
                in_run = True
                start = x
            gap = 0
        else:
            if in_run:
                gap += 1
                if gap >= min_gap:
                    runs.append((start, x - gap))
                    in_run = False
                    gap = 0
    if in_run:
        runs.append((start, w - 1))

    # Also crop vertically to the band's actual top/bottom of opaque pixels
    # so each frame is tightly bounded.
    saved = 0
    for i, (x0, x1) in enumerate(runs):
        # tight vertical bounds within this column range
        y0, y1 = y_bot, y_top
        for x in range(x0, x1 + 1):
            for y in range(y_top, y_bot):
                if pixels[x, y][3] > 16:
                    if y < y0:
                        y0 = y
                    if y > y1:
                        y1 = y
        if y0 > y1:
            continue
        crop = img.crop(
            (
                max(0, x0 - pad),
                max(0, y0 - pad),
                min(w, x1 + 1 + pad),
                min(h, y1 + 1 + pad),
            )
        )
        out_path = os.path.join(OUT_DIR, f"{name_prefix}_{i}.png")
        crop.save(out_path)
        saved += 1
    print(f"  {sheet_path:55s} -> {saved} auto-cells as {name_prefix}_*.png")


def main():
    print("Extracting cat sprite frames...")

    # --- Walk cycle (6 frames @ 72x60) ---
    save_gif_frames(os.path.join(SRC_DIR, "catwalkx4.gif"), "walk")

    # --- Run cycle (6 frames @ 80x68) ---
    save_gif_frames(os.path.join(SRC_DIR, "catrunx4.gif"), "run")

    # --- Idle / sit / groom poses from sprite sheet ---
    # catspritesx4.gif is 548x200, 3 rows:
    #   row 1 (y=0..66):   5 sitting/idle poses, ~109 px wide each
    #   row 2 (y=66..133): 6 walk frames
    #   row 3 (y=133..200): 6 run frames
    sheet = os.path.join(SRC_DIR, "catspritesx4.gif")

    # Use auto-detection on each row so we don't have to hand-tune cell widths.
    autoslice_row(sheet, "idle", y_top=0,   y_bot=66)
    # (walk and run rows are already extracted from the dedicated GIFs above,
    #  but you can also slice them from the sheet if needed.)

    print("Done.")


if __name__ == "__main__":
    main()
