from agent_loop import looks_like_stall


def test_stall_detects_search_menu():
    text = (
        "Не нашёл записей.\n\n"
        "Хотите, чтобы я поискал по:\n"
        "- перепискам с mv_mmb@alfabank.ru;\n"
        "- названию/ИНН компании;\n"
        "- примерной дате?\n\n"
        "Укажите вариант — запущу поиск."
    )
    assert looks_like_stall(text) is True


def test_stall_allows_normal_answer():
    text = (
        "По переписке с Альфой первая компания на комплаенс — "
        "ООО «НордСервис-СПб», ИНН 7816718222 (ypartsuf / mv_mmb)."
    )
    assert looks_like_stall(text) is False
