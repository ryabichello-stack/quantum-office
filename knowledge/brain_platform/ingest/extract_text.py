"""Extract searchable text from common office attachment bytes."""

from __future__ import annotations

import csv
import io
import logging
import re
import zipfile
from xml.etree import ElementTree as ET

logger = logging.getLogger("brain.ingest.extract_text")

MAX_CHARS = 40_000

# Connection / onboarding questionnaire markers (RU + EN).
CONNECTION_MARKERS = re.compile(
    r"("
    r"данные\s+для\s+подключения|"
    r"анкета\s+клиента\s+для\s+подключения|"
    r"анкета\s+(для\s+)?прова[йи]дера|"
    r"client\s*id|"
    r"legal\s*id|"
    r"код\s*\(\s*client\s*id\s*\)|"
    r"тип\s+клиента|"
    r"настройки\s+терминал|"
    r"анкета\s+(партн[её]ра|клиента|оуио)|"
    r"подключаемые\s+продукты|"
    r"наименование\s+юл|"
    r"инн\s+юл|"
    r"инн\s+клиента|"
    r"лимит\s+на\s+(сумму|общую\s+сумму)|"
    r"номера?\s+счетов|"
    r"terminal[_ ]?id|"
    r"merchant[_ ]?id"
    r")",
    re.I,
)


def looks_like_connection_data(text: str) -> bool:
    if not text or len(text.strip()) < 40:
        return False
    hits = CONNECTION_MARKERS.findall(text)
    if len(hits) >= 2:
        return True
    if len(hits) >= 1 and bool(
        re.search(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            text,
            re.I,
        )
        or re.search(r"\bL[AB]\d{10,}\b", text)
        or re.search(r"\bИНН\b|\bINN\b|\b\d{10}\b|\b\d{12}\b", text, re.I)
    ):
        return True
    # Filename-driven / short provider questionnaires
    low = text.lower()
    if ("наименование юл" in low or "инн юл" in low) and (
        "подключаемые продукты" in low or "лпр" in low
    ):
        return True
    return False


def extract_text_from_bytes(
    data: bytes,
    *,
    filename: str = "",
    content_type: str = "",
    max_chars: int = MAX_CHARS,
) -> dict[str, str | bool]:
    """Return {text, method, encrypted, error}."""
    name = (filename or "").lower()
    ctype = (content_type or "").lower()
    if not data:
        return {"text": "", "method": "empty", "encrypted": False, "error": ""}

    # Encrypted zip / OLE markers — cannot decrypt without password.
    if data[:2] == b"PK" and _zip_is_encrypted(data):
        return {
            "text": "",
            "method": "encrypted_zip",
            "encrypted": True,
            "error": "password_protected",
        }
    if data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" and b"EncryptedPackage" in data[:4096]:
        return {
            "text": "",
            "method": "encrypted_ole",
            "encrypted": True,
            "error": "password_protected",
        }

    try:
        if name.endswith((".txt", ".csv", ".md", ".json", ".log", ".xml")) or ctype.startswith(
            "text/"
        ):
            text = _decode_text(data)
            if name.endswith(".csv") or "csv" in ctype:
                text = _normalize_csv(text) or text
            return {"text": text[:max_chars], "method": "text", "encrypted": False, "error": ""}

        if name.endswith(".docx") or "wordprocessingml" in ctype:
            return {
                "text": _extract_docx(data)[:max_chars],
                "method": "docx",
                "encrypted": False,
                "error": "",
            }

        if name.endswith(".xlsx") or "spreadsheetml" in ctype:
            return {
                "text": _extract_xlsx(data)[:max_chars],
                "method": "xlsx",
                "encrypted": False,
                "error": "",
            }

        if name.endswith(".pdf") or "pdf" in ctype:
            text, err = _extract_pdf(data)
            return {
                "text": (text or "")[:max_chars],
                "method": "pdf",
                "encrypted": False,
                "error": err,
            }

        if name.endswith((".html", ".htm")) or "html" in ctype:
            raw = _decode_text(data)
            text = re.sub(r"<[^>]+>", " ", raw)
            text = re.sub(r"\s+", " ", text).strip()
            return {"text": text[:max_chars], "method": "html", "encrypted": False, "error": ""}

        # Best-effort: if payload is mostly text
        sample = data[:4000]
        if sample and sum(32 <= b < 127 or b in (9, 10, 13) for b in sample) / max(len(sample), 1) > 0.85:
            return {
                "text": _decode_text(data)[:max_chars],
                "method": "text_guess",
                "encrypted": False,
                "error": "",
            }
    except Exception as exc:  # noqa: BLE001
        logger.warning("extract failed file=%s: %s", filename, exc)
        return {"text": "", "method": "error", "encrypted": False, "error": str(exc)}

    return {
        "text": "",
        "method": "unsupported",
        "encrypted": False,
        "error": f"unsupported:{name or ctype or 'unknown'}",
    }


def _decode_text(data: bytes) -> str:
    for enc in ("utf-8", "cp1251", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _normalize_csv(text: str) -> str:
    try:
        reader = csv.reader(io.StringIO(text))
        rows = ["; ".join(cell.strip() for cell in row if cell and cell.strip()) for row in reader]
        return "\n".join(r for r in rows if r)
    except Exception:
        return text


def _zip_is_encrypted(data: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for info in zf.infolist():
                if info.flag_bits & 0x1:
                    return True
    except Exception:
        return False
    return False


def _extract_docx(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        xml = zf.read("word/document.xml")
    root = ET.fromstring(xml)
    texts: list[str] = []
    for node in root.iter():
        if node.tag.endswith("}t") and node.text:
            texts.append(node.text)
        elif node.tag.endswith("}tab"):
            texts.append("\t")
        elif node.tag.endswith("}br") or node.tag.endswith("}cr"):
            texts.append("\n")
        elif node.tag.endswith("}p"):
            texts.append("\n")
    return re.sub(r"\n{3,}", "\n\n", "".join(texts)).strip()


def _extract_xlsx(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in root:
                parts = [t.text or "" for t in si.iter() if t.tag.endswith("}t")]
                shared.append("".join(parts))
        lines: list[str] = []
        sheet_names = sorted(
            n for n in zf.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")
        )
        for sheet in sheet_names[:8]:
            root = ET.fromstring(zf.read(sheet))
            rows_out: list[str] = []
            for row in root.iter():
                if not row.tag.endswith("}row"):
                    continue
                cells: list[str] = []
                for c in row:
                    if not c.tag.endswith("}c"):
                        continue
                    cell_type = c.attrib.get("t")
                    v = None
                    for child in c:
                        if child.tag.endswith("}v"):
                            v = child.text
                            break
                    if v is None:
                        continue
                    if cell_type == "s":
                        try:
                            cells.append(shared[int(v)])
                        except Exception:
                            cells.append(v)
                    else:
                        cells.append(v)
                if cells:
                    rows_out.append(" | ".join(cells))
            if rows_out:
                lines.append(f"## {sheet.split('/')[-1]}")
                lines.extend(rows_out[:2000])
        return "\n".join(lines).strip()


def _extract_pdf(data: bytes) -> tuple[str, str]:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:
        try:
            from PyPDF2 import PdfReader  # type: ignore
        except Exception as exc:  # noqa: BLE001
            return "", f"pdf_lib_missing:{exc}"

    try:
        reader = PdfReader(io.BytesIO(data))
        if getattr(reader, "is_encrypted", False):
            try:
                reader.decrypt("")
            except Exception:
                return "", "password_protected"
        parts: list[str] = []
        for page in reader.pages[:40]:
            parts.append(page.extract_text() or "")
        return "\n".join(parts).strip(), ""
    except Exception as exc:  # noqa: BLE001
        return "", str(exc)
