# Outreach presentations

По умолчанию в письмах (шаг 1 цепочки) прикрепляется PDF отрасли
или общий Quantum Payouts.

## Слоты по отраслям

Базовые файлы в репозитории:

- `assets/presentations/<pack_id>.pdf` — lombards / mfo / trade_in / gig / scrap

## Загрузка из UI

Вкладка **Кампания** → выбрать отрасль → «Загрузить / обновить PDF».

Загруженные версии хранятся на сервере в:

- `$DATA_DIR/presentations/<pack_id>.pdf` (обычно `/opt/ava-outreach/data/presentations/`)

Приоритет при отправке: **загруженная** → базовая отраслевая → общая колода.

«Сбросить к базовой» удаляет только загруженный override.

Общий файл: `quantum_payouts_presentation_small.pdf`
