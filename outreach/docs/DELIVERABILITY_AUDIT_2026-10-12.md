# Deliverability Audit & Readiness — 2026-10-12

## 1. Detected problems

| # | Finding | Severity | Status |
|---|---------|----------|--------|
| 1 | Cold marketing sent from corporate `office@quantumlabs.ru` (protected brand domain) | Critical | **Mitigated in code** — marketing gate blocks protected domains |
| 2 | Yandex `554 5.7.1` spam reject on 2026-10-12 (oneshot + campaign) | High | Classifier = `policy` (not hard); ISP cool-down; no global pause on single event |
| 3 | **DMARC missing** for `quantumlabs.ru` (`_dmarc` empty) | High | Manual DNS required (not changed without approval) |
| 4 | DKIM public key appears on **apex TXT**, not only `selector._domainkey` | Medium | WARNING in DNS audit; verify Mail.ru Business selector |
| 5 | SPF `redirect=_spf.mail.ru` present | OK | Present; full alignment vs sending IP not auto-proven |
| 6 | Spamhaus DBL query returns `127.255.255.254` from this environment | Unknown | Treated as **UNKNOWN** (open-resolver policy), not PASS |
| 7 | Soft-bounce `retry=True` never requeues outbox | Medium | Documented; no blind retry of policy/554 |
| 8 | Consent not previously required for CBR-sourced lombards | Legal/compliance | `MARKETING_REQUIRE_CONSENT=true` by default |
| 9 | Oneshot lacked HTTPS List-Unsubscribe | Medium | Fixed — oneshot now sets unsub URL + RFC 8058 header when token available |

## 2. DNS snapshot (automated, 2026-10-12)

| Check | Result |
|-------|--------|
| SPF | PASS (record present: `v=spf1 redirect=_spf.mail.ru`) |
| DKIM | WARNING / needs selector confirmation (apex DKIM TXT seen; check Mail.ru selector) |
| DMARC | **FAIL** — no `_dmarc.quantumlabs.ru` |
| MX | PASS — `0 emx.mail.ru` |
| Spamhaus DBL | **UNKNOWN** — resolver policy response |

PTR/rDNS of Mail.ru egress IPs: not asserted from this host (shared provider infrastructure). Do not claim PASS.

## 3. Code modules added / changed

**New**

- `modules/sending_accounts/` — registry, protected domains, marketing gate, incidents
- `modules/delivery_errors/` — idempotent Delivery Error Analyzer
- `modules/dns_auth/` — SPF/DKIM/DMARC/DNSBL audit API (`UNKNOWN` when unsure)
- `modules/reputation_guard/` — campaign pause thresholds (no domain rotation)
- UI tab **Email Health**
- Tests: `test_deliverability_tz.py`, existing `test_policy_no_global_pause.py`

**Changed**

- `sender.py` — marketing gate + consent gate; oneshot unsubscribe URL
- `modules/deliverability/` — wire analyzer + reputation on bounce; policy no global pause
- `modules/policy/` — consent fields + marketing consent API
- `reply_watcher.py` — pass message_id into bounce handler
- `main.py` — register modules; status payload
- `.env.example`, `CHANGELOG.md`

## 4. Manual actions required (owner)

1. **Do not** re-enable `MARKETING_ALLOW_PROTECTED_DOMAIN` on prod.
2. Add DMARC (after approval), example:
   ```txt
   _dmarc.quantumlabs.ru. TXT "v=DMARC1; p=none; rua=mailto:rdv@47z.ru; fo=1"
   ```
3. In Mail.ru for Business: confirm DKIM selector for `quantumlabs.ru` and that outbound messages show `dkim=pass`.
4. Register [Yandex Postmaster](https://postmaster.yandex.ru/) for `quantumlabs.ru`.
5. Provision a **separate marketing domain** (e.g. `mail.quantumlabs.ru` or new brand domain) — DNS kit below — then create Sending Account with `marketing_allowed=1`, `health_status=ACTIVE`, `enabled=1` via API.
6. Backfill `consent_status=granted` only where documented consent/evidence exists; keep others out of auto marketing.
7. Optionally set `OPEN_TRACKING_ENABLED=false` while recovering Yandex reputation.

## 5. DNS kit for future marketing domain (template)

After domain `SEND.example` is chosen (not auto-purchased):

```txt
; SPF — adjust include: for chosen ESP
SEND.example.  TXT "v=spf1 include:_spf.PROVIDER.example -all"

; DKIM — selector from ESP
s1._domainkey.SEND.example.  TXT "v=DKIM1; k=rsa; p=..."

; DMARC
_dmarc.SEND.example.  TXT "v=DMARC1; p=quarantine; rua=mailto:rdv@47z.ru; fo=1"

; MX for inbound replies (if receiving on same domain)
SEND.example.  MX 10 mx.PROVIDER.example.
```

Then:

```http
POST /api/modules/sending_accounts/accounts
{
  "account_id": "mkt-1",
  "domain": "SEND.example",
  "email": "hello@SEND.example",
  "provider": "PROVIDER",
  "sending_type": "marketing",
  "enabled": true,
  "marketing_allowed": true,
  "health_status": "CONFIGURATION_ERROR"
}
```

Run DNS audit until SPF/DKIM/DMARC = PASS, then set `health_status=ACTIVE`. Marketing send stays off until ACTIVE.

## 6. Infrastructure readiness

| Area | Ready? |
|------|--------|
| Corporate mailbox remains `office@` for transactional/ops | Yes |
| Cold marketing from `quantumlabs.ru` blocked | Yes (code) |
| 554/policy classification + ISP cool-down | Yes |
| Idempotent delivery error log | Yes |
| Consent gate for marketing | Yes (default on) |
| Email Health UI | Yes |
| Dedicated marketing SMTP live | **No** — awaiting domain/ESP |
| DMARC on corporate domain | **No** — awaiting DNS change approval |

## 7. Remaining risks

- Shared Mail.ru IP reputation still affects any future sends from `office@`.
- Until marketing account is ACTIVE, Play will refuse cold batches (by design).
- Consent backfill is operational work; empty consent = no auto ads.
- Soft-bounce retry queue not implemented (safer than silent re-spam).
- Google/Mail Postmaster API integrations not wired (show UNKNOWN until credentials exist).
- PTR of provider IPs not under Quantum Labs control.
