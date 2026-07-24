# Sheets campaign — обзвон «НомераКлиентов»

Таблица: https://docs.google.com/spreadsheets/d/1xjr7vtz56ro9WD8lTIBj3uGliSSN3mh2KHZFJPdLGXE

Вкладки: **НомераКлиентов**, **НомераКлиентов Архив**  
Итог пишется в **Пометки Клиента** (+ транскрипт / статус).

Сервис: `ava-sheets-campaign` `:8018`  
Telegram tools: `preview_payouts_campaign`, `start_payouts_campaign`, `payouts_campaign_status`, `stop_payouts_campaign`

На каждый звонок: Second Brain + **запись на консультацию** (calendar `:8014`) +
Телемост (`:8016` внутри create) + welcome-письмо на email клиента.
Если интересно, но слот не взяли — пометка «перезвонить лично».

**Перед боевым прогоном:** выдать Google Service Account Editor на таблицу
(`GOOGLE_SERVICE_ACCOUNT_FILE`), иначе итоги копятся локально до `flush-writebacks`.

Старт осторожно: `POST /api/campaign/start {"max_calls": 3}`.
