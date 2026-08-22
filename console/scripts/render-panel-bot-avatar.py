#!/usr/bin/env python3
"""Render Quantum Panel bot avatar — circular badge, large orbit mark."""

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
CIRCLE_R = 246  # full circle badge — Telegram crops to circle anyway
WHITE = (245, 248, 255)
SILVER = (168, 178, 196)
DISC_CENTER = (22, 30, 48)
DISC_EDGE = (10, 14, 24)
BG_OUTER = (5, 8, 14)


def _outer_bg() -> Image.Image:
    return Image.new("RGB", (SIZE, SIZE), BG_OUTER)


def _draw_disc(draw: ImageDraw.ImageDraw) -> None:
    """Circular substrate uniting logo + wordmark."""
    x0, y0 = CX - CIRCLE_R, CY - CIRCLE_R
    x1, y1 = CX + CIRCLE_R, CY + CIRCLE_R
    # Soft radial fill (layered rings)
    steps = 24
    for i in range(steps, 0, -1):
        t = i / steps
        r = int(CIRCLE_R * t)
        color = tuple(int(DISC_CENTER[j] * t + DISC_EDGE[j] * (1 - t)) for j in range(3))
        draw.ellipse((CX - r, CY - r, CX + r, CY + r), fill=color)
    # Hairline ring
    draw.ellipse((x0, y0, x1, y1), outline=(255, 255, 255, 36), width=2)
    draw.ellipse((x0 + 3, y0 + 3, x1 - 3, y1 - 3), outline=(255, 255, 255, 12), width=1)


def _logo_glow(draw: ImageDraw.ImageDraw, *, cy: int) -> None:
    draw.ellipse((CX - 132, cy - 100, CX + 132, cy + 100), fill=(72, 118, 255, 22))
    draw.ellipse((CX - 96, cy - 72, CX + 96, cy + 72), fill=(140, 92, 255, 14))


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


def _paste_mark(base: Image.Image, *, mark_px: int, top: int) -> None:
    mark = _white_mark(mark_px)
    x = (SIZE - mark_px) // 2
    layer = base.convert("RGBA")
    layer.paste(mark, (x, top), mark)
    base.paste(layer.convert("RGB"))


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


def _render(
    *,
    mark_px: int,
    mark_top: int,
    quantum_y: int,
    panel_y: int,
    quantum_size: int,
    panel_size: int,
    quantum_tracking: float,
    panel_tracking: float,
    out: Path,
) -> None:
    canvas = _outer_bg().convert("RGBA")
    draw = ImageDraw.Draw(canvas)
    _draw_disc(draw)
    mark_cy = mark_top + mark_px // 2
    _logo_glow(draw, cy=mark_cy)
    _paste_mark(canvas, mark_px=mark_px, top=mark_top)

    draw = ImageDraw.Draw(canvas)
    font_q = ImageFont.truetype(FONT_BOLD, quantum_size)
    font_p = ImageFont.truetype(FONT_LIGHT, panel_size)
    _draw_spaced(draw, "QUANTUM", y=quantum_y, font=font_q, fill=WHITE, tracking=quantum_tracking)
    _draw_spaced(draw, "PANEL", y=panel_y, font=font_p, fill=SILVER, tracking=panel_tracking)

    # Clip to circle so square file = round badge
    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).ellipse(
        (CX - CIRCLE_R, CY - CIRCLE_R, CX + CIRCLE_R, CY + CIRCLE_R),
        fill=255,
    )
    outer = Image.new("RGBA", (SIZE, SIZE), (*BG_OUTER, 255))
    outer.paste(canvas, (0, 0), mask)
    outer.convert("RGB").save(out, optimize=True)


def render_icon() -> None:
    """Telegram avatar — large mark inside circular badge."""
    _render(
        mark_px=268,
        mark_top=44,
        quantum_y=328,
        panel_y=378,
        quantum_size=44,
        panel_size=21,
        quantum_tracking=3.2,
        panel_tracking=13,
        out=OUT_ICON,
    )


def render_lockup() -> None:
    """Same badge, slightly more air around text."""
    _render(
        mark_px=255,
        mark_top=52,
        quantum_y=322,
        panel_y=372,
        quantum_size=42,
        panel_size=20,
        quantum_tracking=3,
        panel_tracking=12,
        out=OUT_LOCKUP,
    )


def main() -> None:
    if not MARK_SRC.is_file():
        raise SystemExit(f"missing brand asset: {MARK_SRC}")
    render_icon()
    render_lockup()
    print(f"wrote {OUT_ICON}")
    print(f"wrote {OUT_LOCKUP}")


if __name__ == "__main__":
    main()
