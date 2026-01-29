from __future__ import annotations

import asyncio
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot

from .db import Booking, list_bookings_needing_reminders, mark_reminder_sent


def _booking_dt(booking: Booking, tz: str) -> datetime:
    y, m, d = (int(x) for x in booking.date.split("-"))
    hh, mm = (int(x) for x in booking.time.split(":"))
    return datetime(y, m, d, hh, mm, tzinfo=ZoneInfo(tz))


async def _send_day_reminder(bot: Bot, booking: Booking) -> None:
    await bot.send_message(
        booking.chat_id,
        f"📌 Напоминание\n\nСегодня у тебя запись в студию: 🗓 {booking.date} ⏰ {booking.time}\n\nЕсли планы изменились — напиши администратору.",
    )


async def _send_hour_reminder(bot: Bot, booking: Booking) -> None:
    await bot.send_message(
        booking.chat_id,
        f"⏳ Уже скоро!\n\nЧерез час запись в студию: 🗓 {booking.date} ⏰ {booking.time}",
    )


async def _notify_admins(bot: Bot, admin_chat_ids: set[int], text: str) -> None:
    for chat_id in admin_chat_ids:
        try:
            await bot.send_message(chat_id, text)
        except Exception:
            continue


async def reminder_loop(
    *,
    bot: Bot,
    db_path: str,
    tz: str,
    admin_chat_ids: set[int],
    poll_seconds: int = 20,
) -> None:
    zone = ZoneInfo(tz)

    while True:
        now = datetime.now(zone)

        try:
            await _process(
                bot=bot,
                db_path=db_path,
                tz=tz,
                admin_chat_ids=admin_chat_ids,
                now=now,
            )
        except Exception:
            await asyncio.sleep(poll_seconds)
            continue

        await asyncio.sleep(poll_seconds)


async def _process(
    *,
    bot: Bot,
    db_path: str,
    tz: str,
    admin_chat_ids: set[int],
    now: datetime,
) -> None:
    items = await list_bookings_needing_reminders(db_path)

    for booking in items:
        dt = _booking_dt(booking, tz)

        if not booking.reminder_day_sent and dt.date() == now.date():
            send_after = datetime.combine(now.date(), time(9, 0), tzinfo=now.tzinfo)
            if now >= send_after or dt <= now + timedelta(hours=1):
                await _send_day_reminder(bot, booking)
                await _notify_admins(
                    bot,
                    admin_chat_ids,
                    f"📌 Сегодня запись: 👤 {booking.full_name or booking.username or booking.user_id} | 🗓 {booking.date} ⏰ {booking.time}",
                )
                await mark_reminder_sent(db_path, booking_id=booking.id, kind="day")

        if not booking.reminder_hour_sent:
            diff = (dt - now).total_seconds()
            if 0 <= diff <= 3600:
                await _send_hour_reminder(bot, booking)
                await _notify_admins(
                    bot,
                    admin_chat_ids,
                    f"⏳ Через час запись: 👤 {booking.full_name or booking.username or booking.user_id} | 🗓 {booking.date} ⏰ {booking.time}",
                )
                await mark_reminder_sent(db_path, booking_id=booking.id, kind="hour")
