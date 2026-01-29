from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    bot_token: str
    owner_id: int
    admin_ids: set[int]
    db_path: str


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is not set")
    return value


def _parse_int(value: str, name: str) -> int:
    try:
        return int(value)
    except ValueError as e:
        raise RuntimeError(f"{name} must be an integer") from e


def get_settings() -> Settings:
    load_dotenv()

    bot_token = _require_env("BOT_TOKEN")
    owner_id = _parse_int(_require_env("OWNER_ID"), "OWNER_ID")

    admin_ids_raw = os.getenv("ADMIN_IDS", "").strip()
    admin_ids: set[int] = set()
    if admin_ids_raw:
        for part in admin_ids_raw.split(","):
            part = part.strip()
            if part:
                admin_ids.add(_parse_int(part, "ADMIN_IDS"))

    admin_ids.add(owner_id)

    db_path = os.getenv("DB_PATH", os.path.join("data", "studio.sqlite3"))
    # Для Amvera используем абсолютный путь
    if db_path.startswith("/app"):
        pass  # Уже абсолютный путь для Amvera
    else:
        # Для локальной разработки
        db_path = os.path.abspath(db_path)

    return Settings(
        bot_token=bot_token,
        owner_id=owner_id,
        admin_ids=admin_ids,
        db_path=db_path,
    )


def get_bot_token() -> str:
    return get_settings().bot_token
