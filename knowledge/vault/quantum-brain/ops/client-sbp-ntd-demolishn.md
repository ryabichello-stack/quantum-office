---
tenant_id: quantum-labs
visibility: company
classification:
  level: internal
  contains_personal_data: false
channels: [office-assistant]
ai_processing:
  allow_external_embed: true
publication:
  manual_approve: false
source: ops#client-sbp-ntd-demolishn
shard: client-sbp-ntd-demolishn
---

# СБП реквизиты клиентов: НТД и Демолишн

Операционная карточка для офисного ассистента. Источник: банковская переписка / настройки СБП (Тинькофф Business API).  
Не публиковать во voice-public. Не путать с логинами личного кабинета.

## НТД — ООО «Новые технологии демонтажа»

- Краткое имя: **НТД**, НТД демонтаж, Новые технологии демонтажа
- ИНН: `7814754000`
- Тип клиента (client type): `12300` (ООО)
- Client ID (СБП / Tinkoff Business): `a5ab0b10-6068-4192-bcb5-3e7f1ad3ae1a`
- Legal ID: `LB0003108318`

## Демолишн — ООО «Демолишн»

- Краткое имя: **Демолишн**, Demolishn, Demolition
- ИНН: `7804558359`
- Тип клиента (client type): `12300` (ООО)
- Client ID (СБП / Tinkoff Business): `f3122898-8f2d-4d59-83b9-7823bf0c3741`
- Legal ID: `LA0005242966`

## Как отвечать

Если спрашивают Client ID / Legal ID / тип клиента для НТД или Демолишн — отвечать значениями из этой карточки.  
Почта Second Brain хранит те же данные в restricted-зоне; эта карточка — curated office-assistant SoT для голосового и текстового секретаря.
