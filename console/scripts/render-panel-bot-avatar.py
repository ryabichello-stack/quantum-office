#!/usr/bin/env python3
"""Quantum Panel bot avatar — approved dark lockup + larger mark + soft circle disc.

Base: ef831dc (the version that was «already close»). Only deltas:
  • bigger official orbit mark
  • soft circular substrate (no hard clip)
  • same QUANTUM / PANEL typography
"""

from __future__ import annotations

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
CX = CY = SIZE // 2
BG_TOP = (11, 18, 32)
BG_BOTTOM = (5, 8, 16)
WHITE = (245, 248, 255)
SILVER = (168, 178, 196)


def _dark_canvas() -> Image.Image:
    canvas = Image.new("RGB", (SIZE, SIZE))
    draw = ImageDraw.Draw(canvas)
    for y in range(SIZE):
        t = y / max(SIZE - 1, 1)
        color = tuple(int(BG_TOP[i] * (1 - t) + BG_BOTTOM[i] * t) for i in range(3))
        draw.line([(0, y), (SIZE, y)], fill=color)
    return canvas


def _soft_circle_disc(canvas: Image.Image, *, radius: int) -> Image.Image:
    """Gentle circular substrate — unifies mark + type, keeps approved dark bg."""
    layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    x0, y0 = CX - radius, CY - radius
    x1, y1 = CX + radius, CY + radius
    draw.ellipse((x0, y0, x1, y1), fill=(20, 28, 44, 95))
    draw.ellipse((x0, y0, x1, y1), outline=(255, 255, 255, 28), width=1)
    base = canvas.convert("RGBA")
    return Image.alpha_composite(base, layer).convert("RGB")


def _add_glow(canvas: Image.Image, *, cx: int, cy: int, rx: int, ry: int) -> Image.Image:
    layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=(72, 118, 255, 28))
    draw.ellipse(
        (cx - int(rx * 0.72), cy - int(ry * 0.72), cx + int(rx * 0.72), cy + int(ry * 0.72)),
        fill=(140, 92, 255, 18),
    )
    base = canvas.convert("RGBA")
    return Image.alpha_composite(base, layer).convert("RGB")


def _white_mark(size_px: int) -> Image.Image:
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
            alpha = min(255, int(255 - v * 0.92))
            op[x, y] = (*WHITE, alpha)
    return out


def _paste_mark(canvas: Image.Image, *, mark_px: int, top: int) -> None:
    mark = _white_mark(mark_px)
    x = (SIZE - mark_px) // 2
    base = canvas.convert("RGBA")
    base.paste(mark, (x, top), mark)
    canvas.paste(base.convert("RGB"))


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
    font_quantum = ImageFont.truetype(FONT_BOLD, 46)
    font_panel = ImageFont.truetype(FONT_LIGHT, 22)
    _draw_spaced(draw, "QUANTUM", y=352, font=font_quantum, fill=WHITE, tracking=3.5)
    _draw_spaced(draw, "PANEL", y=408, font=font_panel, fill=SILVER, tracking=14)


def render_icon() -> None:
    canvas = _dark_canvas()
    canvas = _soft_circle_disc(canvas, radius=238)
    mark_px, top = 232, 82
    cy = top + mark_px // 2
    canvas = _add_glow(canvas, cx=SIZE // 2, cy=cy, rx=128, ry=116)
    _paste_mark(canvas, mark_px=mark_px, top=top)
    draw = ImageDraw.Draw(canvas)
    _draw_lockup(draw)
    canvas.save(OUT_ICON, optimize=True)


def render_lockup() -> None:
    """Alias — one canonical avatar."""
    import shutil

    shutil.copy2(OUT_ICON, OUT_LOCKUP)


def main() -> None:
    if not MARK_SRC.is_file():
        raise SystemExit(f"missing brand asset: {MARK_SRC}")
    render_icon()
    render_lockup()
    print(f"wrote {OUT_ICON}")
    print(f"wrote {OUT_LOCKUP}")


if __name__ == "__main__":
    main()
