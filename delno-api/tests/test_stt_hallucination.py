from app.services.stt import _looks_like_silence_hallucination


def test_filters_russian_subtitle_credits():
    assert _looks_like_silence_hallucination(
        "Редактор субтитров А.Синецкая Корректор А.Егорова"
    )


def test_keeps_real_owner_speech():
    assert not _looks_like_silence_hallucination("Открой форму SIP для телефонии")
