"""Unit tests for operator DIY intent matchers (no DB)."""

from app.api.v1.operator import (
    _wants_billing_summary,
    _wants_calls_list,
    _wants_files_cloud_status,
    _wants_get_knowledge,
    _wants_hermes_capabilities,
    _wants_office_health,
    _wants_phones_list,
)


def test_wants_phones_list():
    assert _wants_phones_list("перечисли мои телефонные номера")
    assert _wants_phones_list("покажи номера")
    assert _wants_phones_list("phones.list")
    assert not _wants_phones_list("создай конференцию")


def test_wants_calls_list():
    assert _wants_calls_list("покажи последние звонки")
    assert _wants_calls_list("история звонков")
    assert _wants_calls_list("calls.list")
    assert not _wants_calls_list("позвони клиенту")
    assert not _wants_calls_list("перечисли мои телефонные номера")


def test_wants_billing_summary():
    assert _wants_billing_summary("покажи баланс биллинга")
    assert _wants_billing_summary("billing.summary")
    assert _wants_billing_summary("сколько токенов осталось")
    assert not _wants_billing_summary("перечисли номера")


def test_wants_office_health_includes_sip_reg():
    assert _wants_office_health("статус офиса")
    assert _wants_office_health("проверь регистрацию SIP")
    assert _wants_office_health("проверь sip")


def test_wants_get_knowledge():
    assert _wants_get_knowledge("кратко что в базе знаний про DELNO")
    assert _wants_get_knowledge("найди в базе знаний про компанию")
    assert _wants_get_knowledge("get_knowledge query=компания")
    assert not _wants_get_knowledge("перечисли номера")


def test_wants_hermes_capabilities():
    assert _wants_hermes_capabilities("вызови hermes.capabilities и кратко перечисли готовые коннекторы")
    assert _wants_hermes_capabilities("что подключено")
    assert _wants_hermes_capabilities("какие инструменты доступны")
    assert not _wants_hermes_capabilities("нарисуй логотип")


def test_wants_files_cloud_status():
    assert _wants_files_cloud_status("какие облака подключены")
    assert _wants_files_cloud_status("files.cloud_status")
    assert _wants_files_cloud_status("статус облаков")
    assert not _wants_files_cloud_status("подключи яндекс диск")
    assert not _wants_files_cloud_status("перечисли номера")


def test_credential_form_yandex_connect_in_conduct():
    from app.api.v1.operator import _credential_form_kind_from_message

    assert _credential_form_kind_from_message("подключи яндекс диск") == "files_yadisk"
    assert _credential_form_kind_from_message("настрой Google Drive") == "files_gdrive"
    assert _credential_form_kind_from_message("какие облака подключены") is None
    assert _credential_form_kind_from_message(
        "какие облака подключены", setup_next_id="files"
    ) is None
