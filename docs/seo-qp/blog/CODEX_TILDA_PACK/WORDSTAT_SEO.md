# Quantum Payouts — Wordstat SEO (2026-10-08)

Источник: Яндекс Wordstat, table view → `/opt/cursor/artifacts/qp-seo-wordstat/wordstat.json`.

## Принципы

- Аудитория: предприниматели, CEO, CFO — B2B-тон, операционка и контроль.
- В Title / H1 / Description / основных H2 / CTA **нет** слова «массовые» (частота 787, но запрет продукта).
- На каждый крупный кластер — **несколько статей**, не один URL.
- Порог продукта в текстах: от 5 млн ₽ выплат в месяц.

## Покрытие кластеров

| Запрос | Freq | URL |
|--------|------|-----|
| выплаты самозанятым | 21597 | `/blog-samozanyatye`, `/blog-kuriery`, `/blog-1c-api` |
| реестр выплат | 10257 | `/blog-reestr` (new), `/blog-1c-api`, `/blog-fizlicam` |
| выплаты по ГПХ | 10050 | `/blog-gph` (new), `/blog-samozanyatye`, `/blog-nalogi` |
| выплаты физическим лицам | 9642 | `/blog-fizlicam`, `/blog-nalogi`, `/blog-reestr`, `/blog-kontrol` |
| выплаты курьерам | 6978 | `/blog-kuriery`, `/blog-samozanyatye` |
| выплаты физлицам | 2668 | `/blog-fizlicam`, `/blog-kontrol` |
| страховые выплаты физическим лицам | 2467 | `/blog-strahovye` |
| выплаты в пользу физических лиц | 2092 | `/blog-fizlicam`, `/blog-nalogi` |
| выплаты из 1С | 1483 | `/blog-1c-api`, `/blog-reestr` |
| сведения о выплатах физическим лицам | 1121 | `/blog-nalogi` (new) |
| выплата вознаграждения физическому лицу | 1114 | `/blog-nalogi`, `/blog-gph` |
| выплаты по СБП | 359 | `/blog-sbp`, `/blog-fizlicam` |
| выплаты МФО | 222 | `/blog-mfo` |
| выплата займа физическому лицу | 324 | `/blog-mfo` |

## Новые статьи (gap)

1. `/blog-reestr` — реестр выплат  
2. `/blog-nalogi` — налоги, сведения, вознаграждение  
3. `/blog-kontrol` — контроль статусов и ролей для CEO/CFO  
4. `/blog-gph` — выделенный кластер ГПХ (отдельно от самозанятых)

## Сборка

```bash
python3 docs/seo-qp/blog/scripts/build_articles.py
# HTML → docs/seo-qp/blog/html/
# SEO meta → docs/seo-qp/blog/manifest.json
python3 docs/seo-qp/blog/scripts/publish_tilda.py  # требует доступ к tilda.ru
```
