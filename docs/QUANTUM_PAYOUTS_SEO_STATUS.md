# SEO Quantum Payouts — статус (2026-09-11)

## Итог
Ключевые meta/OG для `/`, `/privacy`, `/offer` приведены к целевым формулировкам без «массовые». Главная полностью ок в стандартных Tilda SEO-полях. Для privacy/offer из‑за порчи кириллицы в полях Tilda meta вынесены в HEAD через HTML-entities (`<!-- qp-seo-meta-begin -->`), SEO description/keywords/OG в форме очищены.

## Live (проверено curl)

### Главная `/`
- Title: `Выплаты физическим лицам на карты и по СБП | Quantum Payouts`
- Description: `Сервис выплат физическим лицам для бизнеса: на карты банков РФ и по СБП. Личный кабинет, API и 1С, зачисление от 1 минуты, комиссия от 0,4%.`
- Keywords: выплаты физическим лицам / физлицам / карты / СБП / API / 1С
- OG = Title/Description
- «массовые» в meta нет; LENS&LORE нет; порог «5 млн» в теле сохранён

### `/privacy`
- Title ок
- Description/Keywords/OG через entity HEAD (корректная кириллица после unescape)
- Литеральных `\u04xx` в meta больше нет

### `/offer`
- Title: `Оферта | Quantum Payouts`
- Description/OG через entity HEAD
- LENS&LORE удалён

## Сделано ранее
- Backup page в Tilda: `BACKUP SEO 2026-09-10`
- www→non-www redirect
- Ядро Wordstat (без оптимизации под «массовые»)
- Yandex Webmaster baseline (~3 URL в индексе)
- Согласован порог 5 млн ₽/мес

## Осталось (бэклог on-page)
1. Иерархия H1/H2 на главной (сейчас H2 в HTML = 0, заголовки секций в Zero Block div)
2. FAQ-блок + FAQPage schema
3. Organization/SoftwareApplication JSON-LD
4. Alt у изображений (сейчас пустые)
5. E-E-A-T / trust (реквизиты, оферта-линки уже есть)
6. Цели Метрики
7. Mobile/perf (PSI)
8. Повторный замер Wordstat «выплаты из 1С» (конфликт 1604 vs 0)
9. GSC доступ (часто CAPTCHA с cloud IP)
10. Кластеры будущих посадочных (самозанятые/ГПХ/курьеры/СБП/API/1С) — **без массового создания сейчас**
11. В теле главной ещё встречается продуктовая формулировка «Массовые выплаты самозанятым и по ГПХ» — не в Title/H1/Description; решить отдельно, менять ли копирайт

## Техдолг Tilda
- Кириллица в SEO-полях Tilda через clipboard/type портится (выпадение букв). Рабочий путь: DevTools `setNativeValue` + `\uXXXX` **или** HEAD HTML с numeric entities `&#...;`.
- Сессии Tilda короткоживущие — Save/Publish сразу.
- Не полагаться на agent-отчёты без curl view-source.

## Артефакты
- `/opt/cursor/artifacts/seo-qp/` — baseline, wordstat, webmaster, screens, live-check
- `/tmp/seo-paste/set_via_unicode.js`, `privacy_head_entities.html`, `offer_head_entities.html`
