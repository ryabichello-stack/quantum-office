# Quantum Payouts — пакет для заливки блога в Tilda

Tilda projectid: `14431186` · домен: `quantumpayouts.ru`

## Что сделать

1. Для каждой страницы из `ALL_PAGES.json`:
   - если `exists: true` — открыть редактор `https://tilda.ru/page/?pageid={pageid}&projectid=14431186`
   - блок T123 (`recid`) → **Контент** → заменить весь код содержимым файла `html_file`
   - **Сохранить и закрыть** → **Опубликовать**
   - в Настройках страницы выставить `title`, `description`, `keywords` из JSON
2. Если `exists: false` — создать новую страницу с alias = `slug`, добавить блок T123 (HTML), вставить HTML, опубликовать, прописать SEO.
3. Не использовать слово «массовые» в Title/H1/Description/основных H2/CTA.
4. После всех страниц — переобход URL в Яндекс.Вебмастере.

## Новые страницы (создать)

- `/blog-reestr`
- `/blog-nalogi`
- `/blog-kontrol`
- `/blog-gph`

## Уже live (обновить HTML + SEO)

- `/blog` (хаб)
- `/blog-fizlicam` (уже частично обновлён на проде)
- `/blog-samozanyatye`, `/blog-sbp`, `/blog-1c-api`
- `/blog-lombardy`, `/blog-mfo`, `/blog-trade-in`, `/blog-vtorsyre`
- `/blog-strahovye`, `/blog-selhoz`, `/blog-kuriery`

## Файлы

| Файл | Назначение |
|------|------------|
| `ALL_PAGES.json` | полный манифест: pageid, recid, SEO, путь к HTML |
| `html/*.html` | готовый код блока T123 (вставлять целиком) |
| `manifest.json` | SEO Title/H1/Description |
| `pageids.json` | Tilda IDs |
| `WORDSTAT_SEO.md` | карта кластеров Wordstat |

Подвал во всех HTML выровнен под главную: консультация, контакты, соцсети, меню, заявка, политика, оферта, инструкция.
