# RCA — «Набранный номер недоступен» / «Никого нет в сети» (2026-11-24)

**Для:** Codex, Cursor-агентов, операторов QL/DELNO telephony  
**Прод-хост:** Cloud4Box `161.104.89.123` (Москва) — **не** Beget `5.35.86.62` (СПб, уничтожен)  
**Аккаунт Mango:** `vpbx400348777`, сотрудник SIP `garik` (UI: «Бот Гарик», внут. **12**), DID `+79699665899`  
**Статус на момент фикса:** внешние и внутренние звонки на бота снова доходят до Asterisk/AVA.

Секреты (пароли SIP, API keys, webhook tokens) в этот документ **не** писать.

---

## 1. Симптомы

| Как звонили | Что слышали | Доходил ли INVITE до Asterisk |
|-------------|-------------|-------------------------------|
| Внут. **12** (Бот Гарик) | Бот отвечал | Да (`PJSIP/delno-quantum-labs-…` → Stasis) |
| Городской `+79699665899` | «Номер недоступен» / «Никого нет в сети» | **Нет** (tcpdump на `:5060` — 0 INVITE) |

Ключевой вывод: **AVA и dialplan не были корневой причиной внешних отказов.** Mango не отправлял INVITE на Contact, пока считал SIP/схему «не в сети» или вёл DID не на `garik`.

---

## 2. Как должно работать (канон)

```
PSTN → Mango DID +79699665899
    → схема входящих → сотрудник «Бот Гарик» (ext 12, SIP garik)
    → SIP INVITE на Contact из REGISTER
    → Asterisk endpoint delno-quantum-labs → context from-mango
    → AGI delno_route_call.py → bridge → POST /v1/telephony/inbound/start
    → voice_agent_slug=default → Stasis(asterisk-ai-voice-agent) → ai_engine
```

Инварианты (см. также multi-tenant правила DELNO):

1. **Один Mango-аккаунт → одна PJSIP registration** имени `delno-<tenant-slug>-reg` (здесь `delno-quantum-labs-reg`).
2. Запрещено держать рядом живой legacy `mango-registration` на того же `garik` — двойной INVITE рвёт голос.
3. `line=yes` + `endpoint=delno-quantum-labs` на tenant-reg связывает inbound с этой регистрацией.
4. SSH на прод: `root@161.104.89.123`, ключ в env агента — **`POLYHUB_SSH_KEY`** (не спрашивать у человека повторно).

---

## 3. Почему ломалось (корневые причины)

Несколько независимых слоёв сложились вместе.

### 3.1. 2026-11-23 — намеренное отключение QL SIP

На проде есть бэкап:

`/root/backup-telephony-ql-disable-20261123T173739Z/`

Перед отключением `delno-quantum-labs-reg` был **Registered**. После — **Unregistered**.  
Последний «нормальный» внешний CDR до расследования: **2026-11-22**. С **2026-11-23** внешние звонки на DID могли стабильно не доходить.

Откат: `bash /root/backup-telephony-ql-disable-20261123T173739Z/rollback.sh` (осторожно: сверять conf).

### 3.2. Невалидный `enabled=no` в PJSIP

В `/etc/asterisk/pjsip.conf` на legacy `[mango-registration]` стояло:

```
enabled=no
type=registration
…
```

**Asterisk 20 PJSIP не знает опции `registration.enabled`.**  
В `/var/log/asterisk/messages.log`:

- `Could not find option suitable for category 'mango-registration' named 'enabled'`
- объект registration не создаётся / остаётся мусорный Unregistered в runtime

Та же ошибка всплывала, если `enabled=no` писали в `delno-quantum-labs-reg` (файл `*.prerestore*` от 2026-11-24).

**Правильное отключение legacy:** закомментировать весь блок `[mango-registration]` (или удалить), **не** ставить `enabled=no`.  
Apply-helper на хосте: `/opt/delno/scripts/apply_mango_sip_server.py` / `disable_legacy_shared_registration()` — не должен писать невалидный `enabled=`.

### 3.3. Firewall резал часть IP Mango

Было (узко):

- ALLOW `81.88.86.0/23`, `81.88.88.0/23`
- DENY остальных на `5060:5061`

У Mango встречаются адреса шире (в т.ч. рядом с `81.88.83.x`, `app.mango-office.ru` → `81.88.85.67`).  
INVITE/OPTIONS с «чужого» для старых правил префикса → DROP → снаружи «номер недоступен», на сервере тишина в tcpdump.

### 3.4. Не было IP-identify на Mango → tenant endpoint

`pjsip show identifies` показывал только `ava-test` (127.0.0.1).  
Входящие без `;line=` могли не матчиться на `delno-quantum-labs`.  
Для multi-tenant канон — `line=yes` на reg; плюс запасной `type=identify` на сетки Mango → `delno-quantum-labs`.

### 3.5. Путаница «внутренняя линия vs городской»

Наблюдение оператора (подтверждено CDR 2026-11-24 ~20:36–20:37 UTC+3):

- звонок на **внут. 12** → Mango бьёт прямо в зарегистрированный SIP `garik` → бот отвечает;
- звонок на **DID** → Mango смотрит **схему номера** (часто группа/очередь) → фраза «никого нет в сети», **без** INVITE на Contact.

Это **не** баг AVA. Чинится в кабинете Mango:  
**Номера → `+79699665899` → входящие → только «Бот Гарик» (12)**, не группа «все сотрудники».

Красный «!» у «Бот Гарик» в UI = Mango считает SIP offline для маршрутизации DID, даже если Asterisk уже `Registered` (рассинхрон UI / схема / краткий Unregistered после reload).

### 3.6. Ложные гипотезы (отбросить)

| Гипотеза | Факт |
|----------|------|
| Прод = СПб Beget `5.35.86.62` | Хост мёртв (SSH/SIP timeout). Боевой стек на **Москве C4B**. |
| Сломан `ai_engine` / ARI | `ari_connected: true`, внутренние звонки в Stasis OK. |
| Нет SSH-ключа у агента | Ключ есть: env **`POLYHUB_SSH_KEY`**. |
| Нужен quantum-office MCP | Для этой RCA не обязателен; диагностика — SSH + tcpdump + `pjsip show registrations`. |

---

## 4. Что сделано на проде 2026-11-24 (Москва)

Все правки на `161.104.89.123`. Бэкап pjsip:  
`/etc/asterisk/pjsip.conf.bak.telephony-*`.

1. **SSH** через `POLYHUB_SSH_KEY` → `root@161.104.89.123`.
2. **Legacy `mango-registration`:** блок целиком закомментирован (вместо `enabled=no`). После `module reload res_pjsip.so` в CLI осталась **одна** reg: `delno-quantum-labs-reg`.
3. **UFW SIP:** ALLOW `81.88.80.0/20` udp/tcp `5060:5061`, затем DENY rest; порядок ALLOW **перед** DENY.
4. **`[mango-identify]`** → `endpoint=delno-quantum-labs`, `match=81.88.80.0/20` (+ прежние /23).
5. **`local_net`** на `transport-udp` (loopback + RFC1918), чтобы Contact в REGISTER оставался `garik@161.104.89.123:5060`.
6. **Принудительный REGISTER** до стабильного `Registered` + `200 OK` с `Contact: …;expires=…`.
7. **Проверки:**  
   - `asterisk -rx "pjsip show registrations"` → одна строка, Registered;  
   - `database get quantum inbound_line` → `on`;  
   - dry-run bridge → `voice_agent_slug=default`;  
   - внутренний звонок на 12 → CDR/Stasis;  
   - после починки схемы DID / стабилизации reg — внешние тоже.

**Не** менять без нужды: `/root/ava` docker `ai_engine`, dialplan `from-mango` (уже AGI + Stasis), пароли в git.

---

## 5. Чеклист, если снова «недоступен»

```bash
# На C4B:
asterisk -rx "pjsip show registrations"
# Ожидание: ТОЛЬКО delno-quantum-labs-reg → Registered

asterisk -rx "database get quantum inbound_line"   # on
curl -sS http://127.0.0.1:15000/health             # ari_connected true

# Живой звонок снаружи:
timeout 60 tcpdump -ni ens3 -s0 -w /tmp/sip.pcap 'udp port 5060'
# Если INVITE нет — проблема в Mango (схема DID / красный ! у Бота Гарика).
# Если INVITE есть, а Busy — смотреть AGI / voice_agent_slug / AstDB.
```

В Mango UI:

1. «Бот Гарик» — нет красного «!»; приём на SIP, Активен.  
2. Номер `7 969 966-58-99` → входящие **только на внут. 12**, не группа.  
3. Логин SIP совпадает с tenant conf: `400348777/garik` (пароль только в vault/pjsip на хосте).

Запрещено снова:

- писать `enabled=no` в `type=registration`;
- поднимать второй REGISTER того же `garik` (`mango-registration`);
- сужать UFW обратно до одного /23 без проверки актуальных IP Mango;
- SSH на `5.35.86.62` как на «прод».

---

## 6. Файлы на хосте (ориентир)

| Путь | Назначение |
|------|------------|
| `/etc/asterisk/pjsip.conf` | transport, mango-auth, mango-endpoint, legacy reg **закомментирован**, identify |
| `/etc/asterisk/pjsip.d/delno-tenant-quantum-labs.conf` | tenant auth/endpoint/reg (`delno-quantum-labs-reg`) |
| `/etc/asterisk/extensions.conf` | `[from-mango]` → AGI → Stasis |
| `/usr/local/bin/delno_route_call.py` | AGI |
| `/usr/local/bin/asterisk_delno_bridge.sh` | → `http://127.0.0.1:18020` telephony API |
| `/opt/delno/scripts/apply_mango_sip_server.py` | apply helper (systemd `delno-sip-apply`) |
| `/root/ava` + docker `ai_engine` | голосовой движок |

---

## 7. Одной фразой для агента

**Внешний «номер недоступен» при живом внутреннем 12 = Mango не шлёт INVITE на DID (схема/группа/«SIP offline» в UI) либо хост отбрасывает SIP; на C4B держать ровно одну `delno-quantum-labs-reg`, без `enabled=no` на registration, UFW `81.88.80.0/20` на 5060, identify→`delno-quantum-labs`; ключ SSH — `POLYHUB_SSH_KEY`.**
