"""Tests for attachment text extraction + connection-data detection."""

import io
import zipfile

from brain_platform.ingest.extract_text import (
    extract_text_from_bytes,
    looks_like_connection_data,
)


def _docx_bytes(text: str) -> bytes:
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body>
</w:document>"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types></Types>")
        zf.writestr("word/document.xml", document_xml)
    return buf.getvalue()


def test_extract_docx_and_detect_connection():
    payload = _docx_bytes(
        "Данные для подключения Client ID a5ab0b10-6068-4192-bcb5-3e7f1ad3ae1a "
        "Legal ID LB0003108318 ИНН 7814754000"
    )
    out = extract_text_from_bytes(payload, filename="anketa.docx")
    assert out["method"] == "docx"
    assert "Client ID" in out["text"]
    assert looks_like_connection_data(out["text"]) is True


def test_plain_text_csv_extract():
    data = "field;value\nClient ID;abc\nLegal ID;LA0001\n".encode("utf-8")
    out = extract_text_from_bytes(data, filename="settings.csv")
    assert "Client ID" in out["text"]


def test_looks_like_provider_anketa():
    text = (
        "Наименование ЮЛ\nООО «Новые технологии демонтажа»\n"
        "ИНН ЮЛ\n7814754000\nФИО ЛПР и должность\nИванов\n"
        "Подключаемые продукты\nвыплаты\n"
    )
    assert looks_like_connection_data(text) is True


def test_looks_like_connection_negative():
    assert looks_like_connection_data("просто встретимся завтра") is False
