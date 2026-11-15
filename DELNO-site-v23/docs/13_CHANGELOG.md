# DELNO — CHANGELOG

## 2026-10-13 — Проверка качества сайта после отказа Startpack
Исправлена ссылка MAX, возвращавшая 404; обновлено описание действующих каналов на первом экране. Добавлены отдельные метаданные правовых страниц, ссылка на реквизиты в подвале и инструкция по проверке открытых каналов на странице «С чего начать». Удалено упоминание устаревшего staging-адреса из правовых страниц. После публикации проверены 38 страниц sitemap, 38 внутренних ссылок, якоря и 26 локальных файлов. Сквозная проверка телефонии, календаря и CRM остаётся отдельной задачей.

## 2026-10-13 — Проверяемость компании для каталогов
После отказа Startpack реквизиты правообладателя (ИП, ИНН и город) выведены в видимый подвал основного сайта; подробные реквизиты уже есть в правовых документах. Основные внутренние ссылки и публичные страницы проверены. Сайт собран и развернут на `dlno.ru`; актуальный исходный код синхронизирован с `/opt/delno/site`. Startpack не назвал конкретную причину отказа, поэтому возраст домена, отсутствие отзывов и проверяемость функций остаются отдельными вопросами.

## 2026-10-12 — Google crawl readiness
Removed invented modification timestamps and unused frequency/priority hints from the public sitemap. Article entries now use their recorded publication dates; undated static pages omit `lastmod`. Added optional Google Search Console HTML verification metadata support through `NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION`. Verified the new image on a separate port and switched the public ingress; the previous container remains available for rollback. Search Console ownership and sitemap submission still require access to the owner's Google account.

## 2026-10-12 — Google Search Console
Added `https://dlno.ru/` as a URL-prefix property in the owner's Google Search Console and verified ownership with a persistent HTML file. Submitted `/sitemap.xml`; Google acknowledged the submission, while its initial processing report showed zero discovered pages and an inability to process the sitemap. The XML is publicly accessible and contains 38 URLs, so processing status requires follow-up.
URL inspection confirmed the homepage is already indexed. The `/blog` URL was unknown to Google and was added to its priority crawl queue.

## 2026-09-01 (evening)
- Deployed site export v23 to https://a.47z.ru/delno/ (Docker, nginx subpath, systemd `delno-site`).
- Integrated Cursor Knowledge Base into `DELNO-site-v23/docs/` and `AGENTS.md`.
- Lead delivery pending: `TELEGRAM_CHAT_ID` on prod.

## 2026-09-01
- Consolidated current product, architecture, site, AI operator, multi-tenant, channels, supervisor, monetization, marketplace, CRM, booking and long-term strategy into one Cursor-ready knowledge base.
- Current milestone explicitly set to Phase 1: finish the selling website.
- Added Cursor repository rules and architecture guardrails.


## 2026-10-09 — Main site correctness
Fixed six header/footer links to use mainPath without doubled slashes. Lead submit handler retains the form before await, preserves server validation messages, and only shows success after reset. Regression checks reproduce the prior success-path failure and verify success, validation, and network failures. Visual/browser checks remain pending.

## 2026-10-09 — SEO metadata
Added individual title, description and self-canonical metadata for the blog, its articles and help page. Removed `/v3` from the sitemap. Pricing was reviewed but not changed.

## 2026-10-09 — Booking content launch
Published `/solutions/booking` with a client-side missed-inquiry calculator, expanded the four existing blog posts with practical tables, and added four articles on lost inquiries, no-shows, response timing, and booking status. Added navigation and sitemap links. Verified the published pages, canonical URLs, and Metrika counter on `dlno.ru`; the previous site container is retained for rollback.

## 2026-10-09 — Lead conversion tracking
Added a `delno_lead_success` Yandex Metrika event after a successful lead API response and created the matching goal in Metrika. Verified the new client bundle is live. Submitted 11 changed and new URLs to Yandex Webmaster reindexing; its sitemap remains queued for processing.

## 2026-10-09 — Archive indexing
Marked the archived `/v3` landing noindex with canonical `/`, while keeping its URL accessible for review. Verified the public HTML and sitemap.

## 2026-10-10 — Traffic-first marketing site
Removed standalone demo sections and demo calls to action while preserving the floating assistant. Reframed the main page and lead form around scenario selection and pilot enquiries, added a salon landing page and two search-focused guides, linked them in the sitemap, and added Metrika events for form open and start. Historical `/v2`, `/v3`, and `/v4` pages redirect to the public marketing pages so old demo content is not served. Kept existing prices as pilot discussion anchors pending cost validation.
Added a buyer guide to online booking, placed current articles first in the blog, and linked related articles into topic paths.

## 2026-10-10 — Search-led blog expansion
Added 20 practical articles for lost inquiries, booking, channels, industry workflows, vendor choice and pilot economics, taking the public blog from 11 to 31 posts. Each new guide has a distinct operational question, a table or checklist, and topic-specific FAQ. Grouped the blog by reader task, added contextual article links and a user-editable missed-slot margin calculator. The content describes what a business should validate; it does not imply an unbuilt product is available or expose internal project names.

## 2026-10-10 — Clear public calls to action
Removed the internal term “pilot” from navigation, lead buttons, the form, marketing-page copy, metadata and structured FAQ answers. The header now leads to “Оставить заявку”; the separate help page is “С чего начать”. Informational articles may still discuss testing and unit economics where that is the topic.
