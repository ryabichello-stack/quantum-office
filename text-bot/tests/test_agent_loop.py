from agent_loop import looks_like_legitimate_clarify, looks_like_stall


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
    assert looks_like_legitimate_clarify(text) is False


def test_stall_allows_normal_answer():
    text = (
        "По переписке с Альфой первая компания на комплаенс — "
        "ООО «НордСервис-СПб», ИНН 7816718222 (ypartsuf / mv_mmb)."
    )
    assert looks_like_stall(text) is False


def test_allows_concrete_clarify_question():
    text = (
        "В почте несколько компаний с похожим названием. "
        "Уточни ИНН или полное юрлицо — добью поиск."
    )
    assert looks_like_legitimate_clarify(text) is True
    assert looks_like_stall(text) is False


def test_allows_disambiguation_of_found_people():
    text = (
        "Нашёл двух Юлий: Парцуф Юлия Львовна и Юлия Смирнова. "
        "Кого из них имеешь в виду?"
    )
    assert looks_like_legitimate_clarify(text) is True
    assert looks_like_stall(text) is False
