# delno-office — брокеры стека DELNO

Изолированные сервисы для `/opt/delno` (Cloud4Box), tools-first коннекторы Hermes.

| Папка | Compose service | Порт |
|-------|-----------------|------|
| `knowledge/` | `knowledge` | 18021 |
| `mail/` | `mail` | 18000 |
| `files/` | `files` | 18015 |
| `calendar/` | `calendar` | 18014 |
| `conference/` | `conference` | 18016 |

Секреты не хранить здесь — только `/opt/delno/.env`.  
Restore: [`docs/DELNO_RESTORE.md`](../docs/DELNO_RESTORE.md).
