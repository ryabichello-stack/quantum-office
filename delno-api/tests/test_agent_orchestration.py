from app.api.v1.operator import _wants_agent_orchestration, _wants_channel_connect_flow


def test_plan_markers_want_agent():
    assert _wants_agent_orchestration(
        "Составь план настройки офиса по шагам и выполни первый реальный шаг"
    )
    assert _wants_agent_orchestration(
        "1) зайди на https://example.com 2) положи в базу знаний 3) предложи скрипт"
    )
    assert _wants_agent_orchestration(
        "посмотри сайт https://acme.ru и импортируй в знания, потом сценарий звонка"
    )


def test_single_intent_not_agent():
    assert not _wants_agent_orchestration("какой баланс?")
    assert not _wants_agent_orchestration("подключи телеграм")


def test_office_setup_not_channel_steal():
    # Bare office setup must not look like telegram-only channel connect.
    assert not _wants_channel_connect_flow("Составь план настройки офиса по шагам")
