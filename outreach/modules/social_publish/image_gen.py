"""Branded social card images — SVG (no extra deps)."""

from __future__ import annotations

import html
import re
from pathlib import Path


def _slug(text: str, max_len: int = 48) -> str:
    t = re.sub(r"[^\w\s-]", "", (text or "").strip(), flags=re.UNICODE)
    t = re.sub(r"\s+", "-", t).strip("-").lower()
    return (t or "card")[:max_len]


def render_social_card_svg(
    *,
    title: str,
    subtitle: str = "",
    brand: str = "Quantum Labs",
    accent: str = "#0d8f7a",
) -> str:
    title_esc = html.escape((title or "Post")[:120])
    sub_esc = html.escape((subtitle or "")[:280])
    brand_esc = html.escape(brand)
    lines: list[str] = []
    if sub_esc:
        words = sub_esc.split()
        line = ""
        for w in words:
            chunk = (line + " " + w).strip()
            if len(chunk) > 42:
                lines.append(line)
                line = w
            else:
                line = chunk
        if line:
            lines.append(line)
    sub_lines = "\n".join(
        f'  <text x="56" y="{200 + i * 34}" class="sub" fill="#d8e6f0" '
        f'font-family="Manrope, Arial, sans-serif" font-size="30">{html.escape(ln)}</text>'
        for i, ln in enumerate(lines[:6])
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1080" viewBox="0 0 1080 1080">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#0b1f2a"/>
      <stop offset="100%" stop-color="#123d4f"/>
    </linearGradient>
  </defs>
  <rect width="1080" height="1080" fill="url(#bg)"/>
  <rect x="48" y="48" width="984" height="984" rx="32" fill="none" stroke="{accent}" stroke-width="3" opacity="0.45"/>
  <text x="56" y="120" fill="{accent}" font-family="Manrope, Arial, sans-serif" font-size="28" font-weight="600">{brand_esc}</text>
  <text x="56" y="168" fill="#ffffff" font-family="Manrope, Arial, sans-serif" font-size="52" font-weight="700">{title_esc}</text>
{sub_lines}
  <text x="56" y="1020" fill="#9fb3c8" font-family="Manrope, Arial, sans-serif" font-size="22">APPROVAL_REQUIRED</text>
</svg>
"""


def write_social_card(
    out_dir: Path,
    *,
    post_id: str,
    title: str,
    subtitle: str = "",
    variant: str = "square",
) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{post_id[:8]}-{_slug(title)}-{variant}.svg"
    path = out_dir / fname
    svg = render_social_card_svg(title=title, subtitle=subtitle)
    path.write_text(svg, encoding="utf-8")
    return {
        "variant": variant,
        "path": str(path),
        "filename": fname,
        "mime": "image/svg+xml",
    }
