# Quantum Payouts — блог для SEO

Домен: https://quantumpayouts.ru  
Раздел: `/blog`  
Правило: в Title / H1 / Description / основных H2 / CTA **не** использовать «массовые».

Цель: индексируемые статьи-кластеры вокруг выплат физлицам для B2B-аудитории (предприниматели, CEO, CFO). Несколько URL на каждый частотный кластер Wordstat.

Аудитория текстов: руководитель / финдиректор — операционка, контроль, реестр, стык с налогами и 1С. Не B2C-пособия.

## Wordstat → кластеры (частоты сняты 2026-10-08)

| Кластер | Частота | Статьи |
|---------|---------|--------|
| выплаты самозанятым | 21597 | `/blog-samozanyatye`, `/blog-kuriery`, `/blog-1c-api` |
| реестр выплат | 10257 | `/blog-reestr`, `/blog-1c-api`, `/blog-fizlicam` |
| выплаты по ГПХ | 10050 | `/blog-gph`, `/blog-samozanyatye`, `/blog-nalogi` |
| выплаты физическим лицам | 9642 | `/blog-fizlicam`, `/blog-nalogi`, `/blog-reestr`, `/blog-kontrol` |
| выплаты курьерам | 6978 | `/blog-kuriery`, `/blog-samozanyatye` |
| выплаты физлицам | 2668 | `/blog-fizlicam`, `/blog-kontrol` |
| страховые выплаты физлицам | 2467 | `/blog-strahovye` |
| выплаты в пользу физлиц | 2092 | `/blog-fizlicam`, `/blog-nalogi` |
| выплаты из 1С | 1483 | `/blog-1c-api`, `/blog-reestr` |
| сведения о выплатах / вознаграждение | ~1100 | `/blog-nalogi`, `/blog-gph` |
| выплаты по СБП | 359 | `/blog-sbp`, `/blog-fizlicam` |
| выплаты МФО | 222 | `/blog-mfo` |
| ~~массовые выплаты~~ | 787 | **запрещено** в SEO-копирайте |

Исходник частот: артефакт `qp-seo-wordstat/wordstat.json`.

## Карта URL

| URL | Кластер | Коммерческая цель |
|-----|---------|-------------------|
| `/blog` | хаб | все лендинги |
| `/blog-fizlicam` | pillar: выплаты физлицам | `/`, `/sbp`, `/api-1c` |
| `/blog-reestr` | реестр выплат | `/`, `/api-1c` |
| `/blog-nalogi` | налоги, сведения, вознаграждение | `/gph`, `/samozanyatye` |
| `/blog-kontrol` | контроль / статусы / роли | `/` |
| `/blog-samozanyatye` | самозанятые | `/samozanyatye`, `/gph` |
| `/blog-gph` | ГПХ / договор | `/gph` |
| `/blog-sbp` | выплаты по СБП | `/sbp` |
| `/blog-1c-api` | 1С и API | `/api-1c` |
| `/blog-lombardy` | ломбарды / скупка | `/lombardy` |
| `/blog-mfo` | МФО | `/mfo` |
| `/blog-trade-in` | трейд-ин / выкуп авто | `/trade-in` |
| `/blog-vtorsyre` | вторсырьё / металл | `/vtorsyre` |
| `/blog-strahovye` | страховые | `/strahovye` |
| `/blog-selhoz` | сельхоз | `/selhoz` |
| `/blog-kuriery` | курьеры / такси | `/kuriery-taxi` |

Сборка HTML: `python3 docs/seo-qp/blog/scripts/build_articles.py`  
SEO Title/H1/Description — в `manifest.json`.

Обратные ссылки: на парных лендингах T123-полоски (`landing-strips/`). На главной — полоска на `/blog`.

## Формат страницы в Tilda

- Тёмная гамма (`#1c1c1c` / `#2c2c2c` / `#ff6400`)
- Шапка как на главной + T966 (`#submenu:about`)
- HTML-блок T123 на всю ширину
- Порог продукта: **от 5 млн ₽ выплат в месяц**
- Комиссия / скорость в текстах: от 0,4% · от 1 минуты
