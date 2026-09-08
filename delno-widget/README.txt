DELNO Crystal Widget v28 — functional chat prototype

Функциональность:
- активное поле ввода;
- Enter отправляет;
- Shift+Enter переносит строку;
- форма растёт вверх по мере истории;
- видны несколько реплик;
- авто-прокрутка;
- typing indicator;
- ответ -> затем вопрос имени;
- имя сохраняется локально в демо;
- backend adapter уже заложен;
- без backend работает mock-режим;
- light / dark / auto;
- «Работает на DELNO ↗».

Важно:
это UX-прототип. Для production подключить публичный widget gateway,
описанный в INTEGRATION.md. Не подключать браузер напрямую к tenant operator endpoint.
