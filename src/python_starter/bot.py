from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher

from .config import get_settings
from .db import init_db
from .handlers import router


async def run_bot() -> None:
    settings = get_settings()
    await init_db(settings.db_path)

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()
    dp.include_router(router)

    await dp.start_polling(bot)


def main() -> int:
    asyncio.run(run_bot())
    return 0
