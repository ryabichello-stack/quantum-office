"""LLM editorial angle for flywheel."""

from __future__ import annotations

from unittest.mock import patch

from modules.content_flywheel.llm_angle import enrich_editorial_angle, llm_angle_enabled


def json_dumps(obj: dict) -> str:
    import json

    return json.dumps(obj)


def json_bytes(obj: dict) -> bytes:
    import json

    return json.dumps(obj).encode()


def test_llm_angle_disabled_by_default():
    with patch.dict("os.environ", {"FLYWHEEL_LLM_ANGLE": "false"}, clear=False):
        out = enrich_editorial_angle(
            title="Test",
            body="Body",
            analysis={"theme_tier": "medium", "theme_score": 0.5},
            tenant_id="default",
        )
    assert out["llm_angle"]["enabled"] is False


def test_llm_angle_mocked():
    analysis = {"theme_tier": "high", "theme_score": 0.8, "theme_labels": ["Рост"]}
    with patch.dict(
        "os.environ",
        {"FLYWHEEL_LLM_ANGLE": "true", "OPENAI_API_KEY": "sk-test"},
        clear=False,
    ):
        with patch("modules.content_flywheel.llm_angle.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__.return_value.read.return_value = json_bytes(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json_dumps(
                                    {
                                        "hook": "С точки зрения B2B SaaS рост ARR — ключевой сигнал.",
                                        "headline": "SaaS растёт",
                                        "relevance": "Важно для продуктовых команд.",
                                    }
                                )
                            }
                        }
                    ]
                }
            )
            out = enrich_editorial_angle(
                title="SaaS market up",
                body="ARR growth continues.",
                analysis=analysis,
                tenant_id="default",
            )
    assert out["llm_angle"]["used"] is True
    assert "SaaS" in out["editorial_hook"]


def test_llm_angle_enabled_flag():
    with patch.dict("os.environ", {"FLYWHEEL_LLM_ANGLE": "1"}, clear=False):
        assert llm_angle_enabled() is True
