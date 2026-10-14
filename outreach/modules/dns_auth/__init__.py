"""DNS authentication checks (SPF / DKIM / DMARC). Never invent OK — use UNKNOWN."""

from __future__ import annotations

import logging
import re
import socket
from datetime import datetime, timezone
from typing import Any

from core.registry import AppContext

logger = logging.getLogger("ava-outreach.dns_auth")

try:
    import dns.resolver  # type: ignore

    _HAS_DNSPYTHON = True
except Exception:  # noqa: BLE001
    _HAS_DNSPYTHON = False


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _txt_records(name: str) -> tuple[list[str], str | None]:
    """Return TXT strings and optional error. Uses dnspython when available."""
    if _HAS_DNSPYTHON:
        try:
            answers = dns.resolver.resolve(name, "TXT")
            out: list[str] = []
            for rdata in answers:
                parts = getattr(rdata, "strings", None) or getattr(rdata, "text", None)
                if parts is None:
                    out.append(str(rdata).strip('"'))
                elif isinstance(parts, (list, tuple)):
                    out.append(
                        b"".join(
                            p if isinstance(p, (bytes, bytearray)) else str(p).encode()
                            for p in parts
                        ).decode("utf-8", "ignore")
                    )
                else:
                    out.append(str(parts))
            return out, None
        except Exception as exc:  # noqa: BLE001
            return [], f"{type(exc).__name__}:{exc}"
    # Fallback: dig via subprocess is avoided; use getaddrinfo-less socket + UNKNOWN
    return [], "dnspython_not_installed"


def _mx_records(name: str) -> tuple[list[str], str | None]:
    if _HAS_DNSPYTHON:
        try:
            answers = dns.resolver.resolve(name, "MX")
            return [
                f"{int(r.preference)} {str(r.exchange).rstrip('.')}" for r in answers
            ], None
        except Exception as exc:  # noqa: BLE001
            return [], f"{type(exc).__name__}:{exc}"
    return [], "dnspython_not_installed"


def check_spf(domain: str) -> dict[str, Any]:
    txts, err = _txt_records(domain)
    if err and not txts:
        return {"status": "UNKNOWN", "detail": err, "records": []}
    spf = [t for t in txts if t.lower().startswith("v=spf1")]
    if not spf:
        return {"status": "FAIL", "detail": "no_spf_txt", "records": txts}
    # Presence only — full evaluation against sending IP needs the IP.
    return {"status": "PASS", "detail": "spf_record_present", "records": spf}


def check_dmarc(domain: str) -> dict[str, Any]:
    txts, err = _txt_records(f"_dmarc.{domain}")
    if err and not txts:
        return {"status": "UNKNOWN", "detail": err, "records": []}
    dmarc = [t for t in txts if "v=DMARC1" in t.upper()]
    if not dmarc:
        return {"status": "FAIL", "detail": "no_dmarc_record", "records": []}
    pol = "none"
    m = re.search(r"\bp=([a-zA-Z]+)", dmarc[0])
    if m:
        pol = m.group(1).lower()
    return {
        "status": "PASS" if pol in ("none", "quarantine", "reject") else "WARNING",
        "detail": f"policy={pol}",
        "records": dmarc,
    }


def check_dkim(domain: str, selectors: list[str] | None = None) -> dict[str, Any]:
    selectors = selectors or ["mail", "mailru", "default", "s1", "s2", "google", "selector1"]
    found: list[dict[str, str]] = []
    errors: list[str] = []
    for sel in selectors:
        name = f"{sel}._domainkey.{domain}"
        txts, err = _txt_records(name)
        if err:
            errors.append(f"{sel}:{err}")
            continue
        for t in txts:
            if "v=DKIM1" in t.upper() or "p=" in t:
                found.append({"selector": sel, "record": t[:200]})
    if found:
        return {"status": "PASS", "detail": f"selectors={[f['selector'] for f in found]}", "records": found}
    if errors and not _HAS_DNSPYTHON:
        return {"status": "UNKNOWN", "detail": "dnspython_not_installed", "records": []}
    # Apex TXT sometimes wrongly holds DKIM — note but do not treat as valid selector
    apex, _ = _txt_records(domain)
    apex_dkim = [t for t in apex if "v=DKIM1" in t.upper()]
    if apex_dkim:
        return {
            "status": "WARNING",
            "detail": "dkim_found_on_apex_not_selector — fix selector._domainkey",
            "records": [{"selector": "@", "record": apex_dkim[0][:200]}],
        }
    return {"status": "FAIL", "detail": "no_dkim_selector_found", "records": [], "errors": errors[:5]}


def check_mx(domain: str) -> dict[str, Any]:
    mx, err = _mx_records(domain)
    if err and not mx:
        return {"status": "UNKNOWN", "detail": err, "records": []}
    if not mx:
        return {"status": "FAIL", "detail": "no_mx", "records": []}
    return {"status": "PASS", "detail": "mx_present", "records": mx}


def check_dnsbl_domain(domain: str) -> dict[str, Any]:
    """Best-effort Spamhaus DBL. Open resolvers often get 127.255.255.254 → UNKNOWN."""
    qname = f"{domain}.dbl.spamhaus.org"
    try:
        infos = socket.getaddrinfo(qname, None, socket.AF_INET)
        ips = sorted({i[4][0] for i in infos})
    except socket.gaierror:
        return {
            "status": "PASS",
            "detail": "not_listed_or_nxdomain",
            "ips": [],
            "note": "NXDOMAIN typically means not listed; confirm via Spamhaus UI if critical",
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": "UNKNOWN", "detail": f"{type(exc).__name__}:{exc}", "ips": []}
    if any(ip.startswith("127.255.255.") for ip in ips):
        return {
            "status": "UNKNOWN",
            "detail": "spamhaus_policy_or_resolver_blocked",
            "ips": ips,
            "note": "Do not treat as clean listing; query from open resolver is refused",
        }
    if any(ip.startswith("127.0.1.") for ip in ips):
        return {"status": "FAIL", "detail": "listed_on_spamhaus_dbl", "ips": ips}
    return {"status": "UNKNOWN", "detail": "unexpected_response", "ips": ips}


def audit_domain(domain: str) -> dict[str, Any]:
    d = (domain or "").strip().lower()
    spf = check_spf(d)
    dkim = check_dkim(d)
    dmarc = check_dmarc(d)
    mx = check_mx(d)
    dbl = check_dnsbl_domain(d)
    return {
        "ok": True,
        "domain": d,
        "checked_at": _utc_now(),
        "dnspython": _HAS_DNSPYTHON,
        "spf": spf,
        "dkim": dkim,
        "dmarc": dmarc,
        "mx": mx,
        "dnsbl_spamhaus_dbl": dbl,
        "summary": {
            "spf": spf["status"],
            "dkim": dkim["status"],
            "dmarc": dmarc["status"],
            "mx": mx["status"],
            "dnsbl": dbl["status"],
        },
    }


class DnsAuthModule:
    name = "dns_auth"
    version = "1.0.0"

    def __init__(self) -> None:
        self._last: dict[str, Any] | None = None

    def init_db(self) -> None:
        return None

    def on_startup(self, ctx: AppContext) -> None:
        ctx.extras["dns_auth"] = self
        logger.info("dns_auth ready dnspython=%s", _HAS_DNSPYTHON)

    def on_shutdown(self) -> None:
        return None

    def health(self) -> dict[str, Any]:
        return {"ok": True, "dnspython": _HAS_DNSPYTHON, "last": self._last}

    def register_routes(self, router: Any) -> None:
        @router.get("/audit")
        def audit(domain: str = "quantumlabs.ru") -> dict[str, Any]:
            self._last = audit_domain(domain)
            # Mirror statuses onto matching sending accounts (never invent PASS).
            try:
                from modules.sending_accounts import SendingAccountsStore

                store = SendingAccountsStore()
                summary = self._last.get("summary") or {}
                for acc in store.list_accounts():
                    if (acc.get("domain") or "").lower() != domain.lower():
                        continue
                    store.upsert_account(
                        acc["account_id"],
                        spf_status=summary.get("spf", "UNKNOWN"),
                        dkim_status=summary.get("dkim", "UNKNOWN"),
                        dmarc_status=summary.get("dmarc", "UNKNOWN"),
                        last_checked_at=self._last.get("checked_at"),
                    )
            except Exception:  # noqa: BLE001
                logger.debug("mirror dns statuses failed", exc_info=True)
            return self._last
