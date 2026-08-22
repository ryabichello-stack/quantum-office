#!/usr/bin/env python3
"""Render Quantum Panel bot avatar from official Quantum Labs brand assets."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / "static" / "brand"
OUT_ICON = BRAND / "quantum-panel-bot-512.png"
OUT_LOCKUP = BRAND / "quantum-panel-bot-lockup-512.png"
MARK_SRC = BRAND / "logo-square.jpg"

FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

BG = "#fafbfc"
INK = "#0f1b24"
ACCENT = "#e85a1a"
SIZE = 512


def _paste_mark(canvas: Image.Image, *, mark_px: int, top: int) -> None:
    mark = Image.open(MARK_SRC).convert("RGBA")
    mark = mark.resize((mark_px, mark_px), Image.Resampling.LANCZOS)
    x = (SIZE - mark_px) // 2
    canvas.paste(mark, (x, top), mark)


def _draw_wordmark(draw: ImageDraw.ImageDraw, *, y: int, size: int) -> None:
    font_q = ImageFont.truetype(FONT_REG, size)
    font_p = ImageFont.truetype(FONT_BOLD, size)
    q = "Quantum"
    p = " Panel"
    q_w = draw.textlength(q, font=font_q)
    p_w = draw.textlength(p, font=font_p)
    x = (SIZE - q_w - p_w) / 2
    draw.text((x, y), q, fill=INK, font=font_q)
    draw.text((x + q_w, y), p, fill=ACCENT, font=font_p)


def render_icon() -> None:
    """Avatar with wordmark — readable in Telegram chat list."""
    canvas = Image.new("RGB", (SIZE, SIZE), BG)
    _paste_mark(canvas, mark_px=240, top=72)
    draw = ImageDraw.Draw(canvas)
    _draw_wordmark(draw, y=338, size=38)
    canvas.save(OUT_ICON, optimize=True)


def render_lockup() -> None:
    """Spacious variant for docs / marketing."""
    canvas = Image.new("RGB", (SIZE, SIZE), BG)
    _paste_mark(canvas, mark_px=200, top=96)
    draw = ImageDraw.Draw(canvas)
    _draw_wordmark(draw, y=348, size=32)
    canvas.save(OUT_LOCKUP, optimize=True)


def main() -> None:
    if not MARK_SRC.is_file():
        raise SystemExit(f"missing brand asset: {MARK_SRC}")
    render_icon()
    render_lockup()
    print(f"wrote {OUT_ICON}")
    print(f"wrote {OUT_LOCKUP}")


if __name__ == "__main__":
    main()
