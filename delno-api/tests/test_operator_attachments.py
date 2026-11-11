"""Operator chat attachment normalization."""

from __future__ import annotations

import base64

from app.services.operator_attachments import build_user_content, normalize_attachments


def test_normalize_image_attachment():
    png_1x1 = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    out = normalize_attachments(
        [
            {
                "filename": "shot.png",
                "content_type": "image/png",
                "data_base64": base64.b64encode(png_1x1).decode("ascii"),
            }
        ]
    )
    assert out["ok"] is True
    assert out["items"][0]["kind"] == "image"
    assert len(out["vision_parts"]) == 1
    content = build_user_content("", out)
    assert isinstance(content, list)
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image_url"


def test_normalize_text_file():
    raw = base64.b64encode("привет hermes".encode("utf-8")).decode("ascii")
    out = normalize_attachments(
        [{"filename": "note.txt", "content_type": "text/plain", "data_base64": raw}]
    )
    assert out["ok"] is True
    assert out["items"][0]["kind"] == "file"
    assert "привет" in out["text_context"]
    assert isinstance(build_user_content("прочитай", out), str)
