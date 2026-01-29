# python-starter

## Быстрый старт (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -e ".[dev]"

# ВАЖНО: setx сохраняет переменные для НОВЫХ терминалов
setx BOT_TOKEN "<YOUR_TELEGRAM_BOT_TOKEN>"
setx OWNER_ID "<YOUR_TELEGRAM_USER_ID>"
setx ADMIN_IDS "<ADMIN_ID_1>,<ADMIN_ID_2>"

python -m python_starter
pytest
ruff check .
ruff format .
```

## Запуск

- Через модуль:

```powershell
python -m python_starter
```

- Через установленную команду:

```powershell
python-starter
```

## Переменные окружения

- **BOT_TOKEN**: токен бота из @BotFather
- **OWNER_ID**: твой Telegram user id (можно узнать через @userinfobot)
- **ADMIN_IDS**: дополнительные админы через запятую (owner добавляется автоматически)
- **TZ**: таймзона, по умолчанию `Europe/Moscow`
- **DB_PATH**: путь к SQLite, по умолчанию `data/studio.sqlite3`

Можно также создать файл `.env` рядом с `pyproject.toml`:

```env
BOT_TOKEN=123456:ABCDEF
OWNER_ID=123456789
ADMIN_IDS=111111111,222222222
TZ=Europe/Moscow
# DB_PATH=data/studio.sqlite3
```

## Как пользоваться

- **Пользователь**: `📅 Записаться` → выбрать день → выбрать время → заявка уйдёт на подтверждение
- **Админ**: `⚙️ Админка`
  - `✅ Заявки` — одобрить/отклонить
  - `📆 Календарь` — открыть/закрыть день и настроить часы
  - `⏰ Часы (по умолчанию)` — настройки для всех дней
