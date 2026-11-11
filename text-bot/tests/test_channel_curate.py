import os

import channel_curate


def test_signature_has_channel_link(monkeypatch):
    monkeypatch.setenv("TELEGRAM_CURATE_CHANNEL_ID", "@epoch_z")
    monkeypatch.setenv("TELEGRAM_CURATE_CHANNEL_LINK", "https://t.me/epoch_z")
    monkeypatch.setenv("TELEGRAM_CURATE_CHANNEL_TITLE", "Заметки эпохи")
    monkeypatch.delenv("TELEGRAM_CURATE_SIGNATURE", raising=False)
    sig = channel_curate.signature()
    assert "📣" in sig
    assert "https://t.me/epoch_z" in sig
    assert "Заметки эпохи" in sig


def test_compose_appends_footer_once(monkeypatch):
    monkeypatch.setenv("TELEGRAM_CURATE_CHANNEL_ID", "@epoch_z")
    monkeypatch.delenv("TELEGRAM_CURATE_SIGNATURE", raising=False)
    html = channel_curate.compose_post_html("<b>Заголовок</b>\n\nТекст")
    assert html.count("📣") == 1
    assert html.startswith("<b>Заголовок</b>")


def test_enabled_requires_channel_token(monkeypatch):
    monkeypatch.setenv("TELEGRAM_CURATE_ENABLED", "true")
    monkeypatch.delenv("TELEGRAM_CHANNEL_BOT_TOKEN", raising=False)
    assert channel_curate.enabled() is False
    monkeypatch.setenv("TELEGRAM_CHANNEL_BOT_TOKEN", "123:abc")
    assert channel_curate.enabled() is True


def test_extract_media_photo_video_document():
    photo_msg = {"photo": [{"file_id": "p1"}, {"file_id": "p2"}]}
    assert channel_curate.extract_media_item(photo_msg) == {"type": "photo", "media": "p2"}
    video_msg = {"video": {"file_id": "v1"}}
    assert channel_curate.extract_media_item(video_msg) == {"type": "video", "media": "v1"}
    doc_msg = {"document": {"file_id": "d1", "mime_type": "application/pdf"}}
    assert channel_curate.extract_media_item(doc_msg) is None
    post = channel_curate.extract_post(doc_msg)
    assert post["document_file_id"] == "d1"
    assert post["media_kind"] == "document"
