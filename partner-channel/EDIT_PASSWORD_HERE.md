# Куда вписать пароль rdv@

Файл с секретами часто **не виден** в дереве файлов Cursor Remote, потому что:
1. начинается с точки (`.env`), и/или
2. он в `.gitignore` (Cursor по умолчанию скрывает gitignored).

## Откройте напрямую

Полный путь (File → Open File / Cmd+P / Ctrl+P):

```
/workspace/partner-channel/smtp.local.env
```

или:

```
/workspace/partner-channel/.env
```

Впишите пароль в строку:

```
MAIL_PASSWORD=ваш_пароль
```

Потом можно поставить:

```
PARTNER_SEND_ENABLED=true
```

## Если файла нет в списке

Settings → поиск `exclude Git Ignore` → выключить **Explorer: Exclude Git Ignore**.

Не коммитьте `smtp.local.env` / `.env` — они в gitignore.
