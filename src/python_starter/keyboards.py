from __future__ import annotations

import calendar
from datetime import date, timedelta

from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from .db import DaySchedule

MONTHS_RU = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]


def main_menu(*, is_admin: bool) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.add(KeyboardButton(text="📅 Записаться"))
    kb.add(KeyboardButton(text="🗓 Мои записи"))
    if is_admin:
        kb.add(KeyboardButton(text="⚙️ Админка"))
    kb.adjust(2)
    return kb.as_markup(resize_keyboard=True)


def _ru_month_title(year: int, month: int) -> str:
    months = [
        "Январь",
        "Февраль",
        "Март",
        "Апрель",
        "Май",
        "Июнь",
        "Июль",
        "Август",
        "Сентябрь",
        "Октябрь",
        "Ноябрь",
        "Декабрь",
    ]
    return f"{months[month - 1]} {year}"


def calendar_markup(*, year: int, month: int, mode: str, day_status: dict[str, str] | None = None) -> InlineKeyboardMarkup:
    cal = calendar.Calendar(firstweekday=0)
    builder = InlineKeyboardBuilder()

    builder.button(text=f"📆 {_ru_month_title(year, month)}", callback_data="noop")

    for wd in ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]:
        builder.button(text=wd, callback_data="noop")

    today = date.today()
    min_date = today + timedelta(days=1) if mode == "user" else date.min
    if day_status is None:
        day_status = {}

    weeks = cal.monthdayscalendar(year, month)
    for week in weeks:
        for day in week:
            if day == 0:
                builder.button(text=" ", callback_data="noop")
            else:
                d = f"{year:04d}-{month:02d}-{day:02d}"
                current = date(year, month, day)
                if mode == "user" and current < min_date:
                    builder.button(text=" ", callback_data="noop")
                else:
                    status = day_status.get(d, "")
                    if mode == "admin_all":
                        # Для админ-календаря всех записей показываем количество записей
                        count = day_status.get(d, 0)
                        text = f"{day}📝{count}" if isinstance(count, int) and count > 0 else str(day)
                    elif status == "free":
                        text = f"{day}✅"
                    elif status == "partial":
                        text = f"{day}⚪"
                    elif status == "full":
                        text = f"{day}❌"
                    else:
                        text = str(day)
                    builder.button(text=text, callback_data=f"day|{mode}|{d}")

    prev_y, prev_m = (year - 1, 12) if month == 1 else (year, month - 1)
    next_y, next_m = (year + 1, 1) if month == 12 else (year, month + 1)

    if mode == "user":
        min_y, min_m = (min_date.year, min_date.month)
        if (prev_y, prev_m) < (min_y, min_m):
            builder.button(text="⬅️", callback_data="noop")
        else:
            builder.button(text="⬅️", callback_data=f"mon|{mode}|{prev_y:04d}-{prev_m:02d}")
    else:
        builder.button(text="⬅️", callback_data=f"mon|{mode}|{prev_y:04d}-{prev_m:02d}")

    builder.button(text="➡️", callback_data=f"mon|{mode}|{next_y:04d}-{next_m:02d}")

    builder.adjust(1, 7, 7, 7, 7, 7, 2)
    return builder.as_markup()


def montage_markup() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🎬 Монтаж нужен (+1000 ₽)", callback_data="mont|yes")
    builder.button(text="🚫 Без монтажа", callback_data="mont|no")
    builder.adjust(1)
    return builder.as_markup()


def admin_all_bookings_markup() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Назад", callback_data="admin_all_calendar|today")
    builder.button(text="🏠 Главное меню", callback_data="main_menu")
    builder.adjust(1)
    return builder.as_markup()


def confirm_markup() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Изменить время", callback_data="conf|change")
    builder.button(text="✅ Подтвердить", callback_data="conf|ok")
    builder.button(text="💬 Комментарий", callback_data="conf|comment")
    builder.adjust(1)
    return builder.as_markup()


def _add_minutes(hhmm: str, minutes: int) -> str:
    hh, mm = (int(x) for x in hhmm.split(":"))
    total = hh * 60 + mm + minutes
    return f"{(total // 60) % 24:02d}:{total % 60:02d}"


def time_range_markup(*, mode: str, day: str, schedule: DaySchedule, step: str, start_time: str | None = None, bookings: list | None = None) -> InlineKeyboardMarkup:
    """Клавиатура для выбора начала/окончания временного диапазона."""
    builder = InlineKeyboardBuilder()
    open_h = int(schedule.open_time[:2])
    close_h = int(schedule.close_time[:2])
    
    if bookings is None:
        bookings = []
    
    # Показываем часы от open до close
    for h in range(open_h, close_h + 1):
        hhmm = f"{h:02d}:00"
        if step == "end" and start_time and hhmm <= start_time:
            continue  # не показываем время раньше или равное началу
        
        # Проверяем, пересекается ли этот час с существующими записями
        is_booked = False
        for b in bookings:
            # Проверяем пересечение интервалов
            if (hhmm >= b.start and hhmm < b.end) or (hhmm < b.end and b.start < f"{h+1:02d}:00"):
                is_booked = True
                break
        
        if is_booked:
            text = f"{hhmm}❌"
        else:
            text = f"{hhmm}✅"
            
        builder.button(
            text=text,
            callback_data=f"hour|{mode}|{day}|{hhmm}",
        )
    builder.adjust(4)
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"day|{mode}|{day}"))
    return builder.as_markup()


def hours_markup(*, mode: str, day: str, hours: list[str], slot_minutes: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=f"🗓 {day}", callback_data="noop")

    if not hours:
        builder.button(text="😔 Нет свободных слотов", callback_data="noop")
    else:
        for h in hours:
            end = _add_minutes(h, slot_minutes)
            builder.button(text=f"⏰ {h}–{end}", callback_data=f"hour|{mode}|{day}|{h}")

    builder.button(text="⬅️ Назад", callback_data=f"cal|{mode}")
    builder.adjust(1, 2)
    return builder.as_markup()


def admin_booking_decision_markup(*, booking_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Одобрить", callback_data=f"appr|ok|{booking_id}")
    builder.button(text="❌ Отклонить", callback_data=f"appr|no|{booking_id}")
    builder.adjust(2)
    return builder.as_markup()


def admin_banned_markup() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Назад", callback_data="admin_menu")
    builder.adjust(1)
    return builder.as_markup()


def admin_unban_markup(*, user_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔓 Разблокировать", callback_data=f"unban|{user_id}")
    builder.button(text="⬅️ Назад", callback_data="admin_banned")
    builder.adjust(1)
    return builder.as_markup()


def admin_booking_cancel_markup(*, booking_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отменить запись", callback_data=f"cancel_booking|{booking_id}")
    builder.button(text="⬅️ Назад", callback_data="admin_all")
    builder.adjust(1)
    return builder.as_markup()


def admin_menu_markup() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 Все записи", callback_data="admin|all")
    builder.button(text="✅ Заявки", callback_data="admin|pending")
    builder.button(text="📆 Календарь", callback_data="admin|calendar")
    builder.button(text="⏰ Часы (по умолчанию)", callback_data="admin|default")
    builder.adjust(1)
    return builder.as_markup()


def admin_default_manage_markup(
    *,
    is_open: bool,
    open_time: str,
    close_time: str,
    slot_minutes: int,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    status = "🟢 Открыто" if is_open else "🔴 Закрыто"
    builder.button(text=f"{status}", callback_data="def|toggle")
    builder.button(text=f"🕙 Открытие: {open_time}", callback_data="def|open")
    builder.button(text=f"🕗 Закрытие: {close_time}", callback_data="def|close")
    builder.button(text=f"⏱ Слот: {slot_minutes} мин", callback_data="def|slot")
    builder.adjust(1)
    return builder.as_markup()


def pick_slot_minutes_markup() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="30 мин", callback_data="defslot|30")
    builder.button(text="60 мин", callback_data="defslot|60")
    builder.button(text="90 мин", callback_data="defslot|90")
    builder.button(text="⬅️ Назад", callback_data="admin|default")
    builder.adjust(3, 1)
    return builder.as_markup()


def admin_day_manage_markup(*, day: str, is_open: bool, open_time: str, close_time: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    status = "🟢 Открыто" if is_open else "🔴 Закрыто"
    builder.button(text=f"{status}", callback_data=f"admday|toggle|{day}")
    builder.button(text=f"🕙 Открытие: {open_time}", callback_data=f"admday|open|{day}")
    builder.button(text=f"🕗 Закрытие: {close_time}", callback_data=f"admday|close|{day}")
    builder.button(text="⬅️ Назад", callback_data="admin|calendar")
    builder.adjust(1)
    return builder.as_markup()


def pick_hour_markup(*, action: str, day: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=f"⏰ Выбери час ({action})", callback_data="noop")
    for h in range(0, 24):
        builder.button(text=f"{h:02d}:00", callback_data=f"sethour|{action}|{day}|{h:02d}:00")
    builder.button(text="⬅️ Назад", callback_data=f"day|admin|{day}")
    builder.adjust(1, 6, 6, 6, 6, 1)
    return builder.as_markup()


def my_bookings_markup(items: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if not items:
        builder.button(text="😔 Пока нет записей", callback_data="noop")
    else:
        for booking_id, title in items:
            builder.button(text=f"❌ Отменить {title}", callback_data=f"cancel|{booking_id}")
    builder.adjust(1)
    return builder.as_markup()
