#!/usr/bin/env python3
"""Quantum Panel bot avatar — approved final lockup.

Orange orbit mark · white QUANTUM · orange PANEL · deep black background.
"""

from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / "static" / "brand"
OUT_ICON = BRAND / "quantum-panel-bot-512.png"
OUT_LOCKUP = BRAND / "quantum-panel-bot-lockup-512.png"
MARK_SRC = BRAND / "logo-square.jpg"

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_LIGHT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

SIZE = 512
WHITE = (255, 255, 255)
ORANGE = (216, 106, 58)  # copper-orange, brand-adjacent
BG = (8, 8, 10)


def _bg() -> Image.Image:
    canvas = Image.new("RGB", (SIZE, SIZE), BG)
    px = canvas.load()
    rng = random.Random(42)
    for y in range(SIZE):
        for x in range(SIZE):
            n = rng.randint(-3, 3)
            v = max(0, min(255, BG[0] + n))
            px[x, y] = (v, v, v + 1)
    return canvas


def _colored_mark(size_px: int, color: tuple[int, int, int]) -> Image.Image:
    src = Image.open(MARK_SRC).convert("L")
    src = src.resize((size_px, size_px), Image.Resampling.LANCZOS)
    out = Image.new("RGBA", (size_px, size_px), (0, 0, 0, 0))
    sp = src.load()
    op = out.load()
    for y in range(size_px):
        for x in range(size_px):
            v = sp[x, y]
            if v > 210:
                continue
            alpha = min(255, int(255 - v * 0.9))
            op[x, y] = (*color, alpha)
    return out


def _paste_mark(canvas: Image.Image, *, mark_px: int, top: int) -> None:
    mark = _colored_mark(mark_px, ORANGE)
    x = (SIZE - mark_px) // 2
    layer = canvas.convert("RGBA")
    layer.paste(mark, (x, top), mark)
    canvas.paste(layer.convert("RGB"))


def _draw_spaced(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    y: int,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int],
    tracking: float,
) -> None:
    chars = list(text)
    widths = [draw.textlength(c, font=font) for c in chars]
    total = sum(widths) + tracking * max(len(chars) - 1, 0)
    x = (SIZE - total) / 2
    for i, ch in enumerate(chars):
        draw.text((x, y), ch, fill=fill, font=font)
        x += widths[i] + tracking


def _draw_lockup(draw: ImageDraw.ImageDraw) -> None:
    font_quantum = ImageFont.truetype(FONT_BOLD, 48)
    font_panel = ImageFont.truetype(FONT_LIGHT, 20)
    _draw_spaced(draw, "QUANTUM", y=348, font=font_quantum, fill=WHITE, tracking=4)
    _draw_spaced(draw, "PANEL", y=404, font=font_panel, fill=ORANGE, tracking=16)


def render_icon() -> None:
    canvas = _bg()
    _paste_mark(canvas, mark_px=240, top=72)
    draw = ImageDraw.Draw(canvas)
    _draw_lockup(draw)
    canvas.save(OUT_ICON, optimize=True)


def render_lockup() -> None:
    import shutil

    shutil.copy2(OUT_ICON, OUT_LOCKUP)


def main() -> None:
    if not MARK_SRC.is_file():
        raise SystemExit(f"missing brand asset: {MARK_SRC}")
    render_icon()
    render_lockup()
    print(f"wrote {OUT_ICON}")


if __name__ == "__main__":
    main()
