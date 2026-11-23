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


def test_compose_empty_body_footer_only(monkeypatch):
    monkeypatch.setenv("TELEGRAM_CURATE_CHANNEL_ID", "@epoch_z")
    monkeypatch.delenv("TELEGRAM_CURATE_SIGNATURE", raising=False)
    html = channel_curate.compose_post_html("")
    assert html.startswith("📣")
    assert "Заметки эпохи" in html
    assert not html.startswith(" ")


def test_sanitize_strips_junk_block_tags():
    dirty = "<p>Привет</p><br/><div>мир</div><ul><li>раз</li></ul><span>x</span>"
    clean = channel_curate.sanitize_telegram_html(dirty)
    assert "<br" not in clean.lower()
    assert "<p" not in clean.lower()
    assert "<div" not in clean.lower()
    assert "<ul" not in clean.lower()
    assert "<li" not in clean.lower()
    assert "<span" not in clean.lower()
    assert "Привет" in clean
    assert "мир" in clean


def test_sanitize_strips_ul_wrapper_like_epoch_bug():
    dirty = (
        "НАТО призывает готовиться\n\n"
        "<ul>\n"
        "• Война может затронуть разные сферы жизни\n"
        "• Важно, чтобы все были готовы к вызовам\n"
        "</ul>\n\n"
        "В условиях нестабильности готовность — ключ к безопасности."
    )
    clean = channel_curate.sanitize_telegram_html(dirty)
    assert "<ul" not in clean.lower()
    assert "</ul>" not in clean.lower()
    assert "НАТО" in clean


def test_sanitize_keeps_safe_tags():
    src = '<b>Заголовок</b>\n\nТекст с <i>акцентом</i> и <a href="https://t.me/epoch_z">ссылкой</a>'
    clean = channel_curate.sanitize_telegram_html(src)
    assert "<b>Заголовок</b>" in clean
    assert "<i>акцентом</i>" in clean
    assert 'href="https://t.me/epoch_z"' in clean


def test_prepare_body_media_only_no_invent(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    out = channel_curate.prepare_body(
        source="",
        source_html="",
        openai_api_key="sk-test",
        model="gpt-4.1-mini",
        has_media=True,
    )
    assert out == ""


def test_prepare_body_without_key_keeps_source_html():
    out = channel_curate.prepare_body(
        source="Сырой текст",
        source_html="<b>Сырой текст</b>",
        openai_api_key="",
        model="gpt-4.1-mini",
        has_media=False,
    )
    assert out == "<b>Сырой текст</b>"


def test_rewrite_mode_off_passthrough(monkeypatch):
    monkeypatch.setenv("TELEGRAM_CURATE_REWRITE_MODE", "off")
    out = channel_curate.prepare_body(
        source="Живая новость с перчинкой",
        source_html="<b>Живая новость с перчинкой</b>",
        openai_api_key="sk-test",
        model="gpt-4.1-mini",
        has_media=False,
    )
    assert out == "<b>Живая новость с перчинкой</b>"


def test_default_mode_is_off_no_llm(monkeypatch):
    monkeypatch.delenv("TELEGRAM_CURATE_REWRITE_MODE", raising=False)
    assert channel_curate.rewrite_mode() == "off"
    out = channel_curate.prepare_body(
        source="Оригинал со смаком",
        source_html="",
        openai_api_key="sk-test",
        model="gpt-4.1-mini",
        has_media=False,
    )
    assert "Оригинал со смаком" in out


def test_rewrite_is_faithful_rejects_ul_and_invented_bullets():
    src = "Генсек НАТО призвал готовиться к войне на заседании в Берлине."
    bad = (
        "НАТО призывает готовиться к возможной войне\n\n"
        "<ul>\n• Война может затронуть разные сферы жизни\n"
        "• Важно, чтобы все были готовы к вызовам\n</ul>\n\n"
        "В условиях нестабильности готовность — ключ к безопасности."
    )
    assert channel_curate.rewrite_is_faithful(src, bad) is False
    assert channel_curate.rewrite_is_faithful(src, src) is True


def test_strip_foreign_cta_keeps_news():
    src = "Важная новость про рынок.\n\nПодписывайтесь на наш канал\nhttps://t.me/other_channel"
    out = channel_curate.strip_foreign_cta(src)
    assert "Важная новость" in out
    assert "Подписывайтесь" not in out
    assert "other_channel" not in out


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


def test_entities_to_html_bold():
    text = "Hello"
    entities = [{"type": "bold", "offset": 0, "length": 5}]
    html = channel_curate.entities_to_html(text, entities)
    assert html == "<b>Hello</b>"


def test_extract_post_keeps_caption_entities():
    msg = {
        "caption": "Новость",
        "caption_entities": [{"type": "bold", "offset": 0, "length": 7}],
        "photo": [{"file_id": "p1"}],
    }
    post = channel_curate.extract_post(msg)
    assert post["text"] == "Новость"
    assert post["text_html"] == "<b>Новость</b>"
