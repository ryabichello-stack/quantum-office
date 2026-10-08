# Quantum Payouts — блог (live + SEO deep)

Updated: 2026-10-08 UTC  
Tilda projectid `14431186` · счётчик Метрики `104241036`

Раздел запущен, чтобы в поиске появились не только коммерческие лендинги, а индексируемые статьи с перелинковкой для B2B (CEO / CFO / предприниматели).

## SEO deep (Wordstat, 2026-10-08)

Сняты частоты Wordstat → артефакт `qp-seo-wordstat/wordstat.json`.  
Все статьи переписаны глубже под B2B; добавлены gap-URL под кластеры «реестр», «ГПХ», «налоги/сведения», «контроль».  
Сборка: `docs/seo-qp/blog/scripts/build_articles.py` · карта: `docs/seo-qp/blog/WORDSTAT_SEO.md` · `PLAN.md`.

**Публикация в Tilda:** с VM агента `tilda.ru` (QRATOR `178.248.233.147`) недоступен — логин/редактор не открываются. HTML и SEO meta готовы в `docs/seo-qp/blog/html/` + `manifest.json`. Скрипт заливки: `docs/seo-qp/blog/scripts/publish_tilda.py` (нужен доступ к tilda.ru).

### Новые URL (после publish)

| URL | Кластер |
|-----|---------|
| `/blog-reestr` | реестр выплат (10257) |
| `/blog-nalogi` | сведения / НДФЛ / вознаграждение |
| `/blog-kontrol` | контроль статусов и ролей |
| `/blog-gph` | выплаты по ГПХ (10050) |

## Live (уже на сайте, HTTP 200)

| URL | Title / H1 |
|-----|--------|
| https://quantumpayouts.ru/blog | Статьи о выплатах физическим лицам |
| https://quantumpayouts.ru/blog-fizlicam | Выплаты физическим лицам |
| https://quantumpayouts.ru/blog-samozanyatye | Выплаты самозанятым |
| https://quantumpayouts.ru/blog-sbp | Выплаты по СБП |
| https://quantumpayouts.ru/blog-1c-api | Выплаты из 1С и по API |
| https://quantumpayouts.ru/blog-lombardy | Ломбарды и скупка |
| https://quantumpayouts.ru/blog-mfo | МФО |
| https://quantumpayouts.ru/blog-trade-in | Трейд-ин |
| https://quantumpayouts.ru/blog-vtorsyre | Вторсырьё |
| https://quantumpayouts.ru/blog-strahovye | Страховые |
| https://quantumpayouts.ru/blog-selhoz | Сельхоз |
| https://quantumpayouts.ru/blog-kuriery | Курьеры и такси |

Пункт **Блог** в меню «Меню» на главной и лендингах. Тёмная гамма сайта. Шапка блога как на главной + T966.

В Title/H1/Description нет слова «массовые». Порог продукта: от 5 млн ₽ в месяц.
