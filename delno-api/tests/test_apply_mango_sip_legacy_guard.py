"""Pure helpers from apply_mango_sip_server — dual-reg must not survive multi-tenant."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "deploy" / "apply_mango_sip_server.py"


@pytest.fixture(scope="module")
def sip_apply():
    spec = importlib.util.spec_from_file_location("apply_mango_sip_server", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_disable_legacy_section_inserts_enabled_no(sip_apply):
    src = (
        "[transport-udp]\ntype=transport\n\n"
        "[mango-registration]\n"
        "type=registration\n"
        "client_uri=sip:garik@vpbx.example\n"
        "line=yes\n"
        "endpoint=mango-trunk\n\n"
        "[mango-endpoint]\n"
        "type=endpoint\n"
    )
    out, changed = sip_apply._set_pjsip_section_enabled(src, "mango-registration", False)
    assert changed is True
    sec = out.split("[mango-registration]")[1].split("[mango-endpoint]")[0]
    assert "enabled=no" in sec
    assert "type=registration" in sec
    assert "[mango-endpoint]" in out


def test_disable_legacy_flips_enabled_yes(sip_apply):
    src = "[mango-registration]\nenabled=yes\ntype=registration\n"
    out, changed = sip_apply._set_pjsip_section_enabled(src, "mango-registration", False)
    assert changed is True
    assert "enabled=no" in out
    assert "enabled=yes" not in out


def test_already_disabled_is_noop(sip_apply):
    src = "[mango-registration]\nenabled=no\ntype=registration\n"
    out, changed = sip_apply._set_pjsip_section_enabled(src, "mango-registration", False)
    assert changed is False
    assert out == src
