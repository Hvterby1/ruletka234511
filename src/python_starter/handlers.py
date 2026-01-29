from __future__ import annotations

from datetime import date as date_type

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .config import get_settings
from .db import (
    cancel_booking,
    create_booking_pending,
    get_booking,
    get_day_schedule,
    get_default_schedule,
    has_approved_booking,
    init_db,
    list_available_hours,
    list_pending_bookings,
    list_user_bookings,
    set_booking_status,
    set_day_override,
    set_default_schedule,
    DaySchedule,
)
from .keyboards import MONTHS_RU
from .keyboards import (
    admin_booking_cancel_markup,
    admin_booking_decision_markup,
    admin_day_manage_markup,
    admin_default_manage_markup,
    admin_menu_markup,
    calendar_markup,
    confirm_markup,
    hours_markup,
    main_menu,
    montage_markup,
    my_bookings_markup,
    pick_hour_markup,
    pick_slot_minutes_markup,
    time_range_markup,
)

router = Router()

_wizard_state: dict[int, dict] = {}


def _clear_wizard(user_id: int) -> None:
    _wizard_state.pop(user_id, None)


def _set_wizard(user_id: int, *, step: str, data: dict) -> None:
    _wizard_state[user_id] = {"step": step, "data": data}


def _get_wizard(user_id: int) -> dict | None:
    return _wizard_state.get(user_id)


def _is_admin(user_id: int) -> bool:
    return user_id in get_settings().admin_ids


def _today_ym() -> tuple[int, int]:
    today = date_type.today()
    return today.year, today.month


async def _send_main_menu(message: Message) -> None:
    is_admin = _is_admin(message.from_user.id) if message.from_user else False
    await message.answer(
        "🎙️ Студия подкаста\n\nВыбери действие ниже 👇",
        reply_markup=main_menu(is_admin=is_admin),
    )


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    if not message.from_user:
        return
        
    settings = get_settings()
    await init_db(settings.db_path)
    
    _clear_wizard(message.from_user.id)
    await _send_main_menu(message)


@router.message(F.text == "⚙️ Админка")
async def msg_admin(message: Message) -> None:
    if not message.from_user or not _is_admin(message.from_user.id):
        await message.answer("⛔️ Доступ только для админов")
        return

    settings = get_settings()
    await init_db(settings.db_path)
    await message.answer(
        "⚙️ Админ-панель",
        reply_markup=admin_menu_markup(),
    )


@router.message(F.text == "📅 Записаться")
async def msg_book(message: Message) -> None:
    settings = get_settings()
    await init_db(settings.db_path)
    year, month = _today_ym()
    
    # Собираем статус дней для календаря
    day_status = {}
    for day in range(1, 32):
        try:
            d = f"{year:04d}-{month:02d}-{day:02d}"
            schedule = await get_day_schedule(settings.db_path, d)
            if not schedule.is_open:
                day_status[d] = "full"  # студия закрыта
                continue
                
            available_hours = await list_available_hours(settings.db_path, d)
            all_bookings = await list_user_bookings(settings.db_path, user_id=None)
            # Учитываем только одобренные записи
            day_bookings = [b for b in all_bookings if b.date == d and b.status == "approved"]
            
            if not day_bookings:
                day_status[d] = "free"  # полностью свободен
            else:
                # Проверяем, есть ли свободные часы
                has_free = False
                for hour in available_hours:
                    hour_booked = False
                    for b in day_bookings:
                        if hour >= b.start and hour < b.end:
                            hour_booked = True
                            break
                    if not hour_booked:
                        has_free = True
                        break
                
                if has_free:
                    day_status[d] = "partial"  # частично занят
                else:
                    day_status[d] = "full"  # полностью занят
        except Exception:
            break
    
    await message.answer(
        "📅 Выбери день для записи:",
        reply_markup=calendar_markup(year=year, month=month, mode="user", day_status=day_status),
    )


@router.message(F.text == "🗓 Мои записи")
async def msg_my_bookings(message: Message) -> None:
    settings = get_settings()
    await init_db(settings.db_path)

    user_id = message.from_user.id
    bookings = await list_user_bookings(settings.db_path, user_id)

    items: list[tuple[int, str]] = []
    for b in bookings:
        status = "⏳" if b.status == "pending" else "✅"
        items.append((b.id, f"{status} {b.date} {b.time}"))

    await message.answer(
        "🗓 Твои записи:\n\nНажми, чтобы отменить:",
        reply_markup=my_bookings_markup(items),
    )


@router.message(F.text == "⚙️ Админка")
async def msg_admin(message: Message) -> None:
    if not message.from_user or not _is_admin(message.from_user.id):
        await message.answer("⛔️ Доступ только для админов")
        return

    settings = get_settings()
    await init_db(settings.db_path)
    await message.answer("⚙️ Админ-панель", reply_markup=admin_menu_markup())


@router.callback_query(F.data == "noop")
async def cb_noop(call: CallbackQuery) -> None:
    await call.answer()


@router.callback_query(F.data.startswith("cal|"))
async def cb_calendar_today(call: CallbackQuery) -> None:
    _, mode = call.data.split("|", 1)
    settings = get_settings()
    await init_db(settings.db_path)
    year, month = _today_ym()
    
    # Собираем статус дней
    day_status = {}
    if mode == "admin_all":
        all_bookings = await list_user_bookings(settings.db_path, user_id=None)
        for b in all_bookings:
            if b.date.startswith(f"{year:04d}-{month:02d}"):
                day_status[b.date] = day_status.get(b.date, 0) + 1
    else:
        for day in range(1, 32):
            try:
                d = f"{year:04d}-{month:02d}-{day:02d}"
                schedule = await get_day_schedule(settings.db_path, d)
                if not schedule.is_open:
                    day_status[d] = "full"
                    continue
                    
                available_hours = await list_available_hours(settings.db_path, d)
                all_bookings = await list_user_bookings(settings.db_path, user_id=None)
                day_bookings = [b for b in all_bookings if b.date == d and b.status == "approved"]
                
                if not day_bookings:
                    day_status[d] = "free"
                else:
                    # Проверяем, есть ли свободные часы
                    has_free = False
                    for hour in available_hours:
                        hour_booked = False
                        for b in day_bookings:
                            if hour >= b.start and hour < b.end:
                                hour_booked = True
                                break
                        if not hour_booked:
                            has_free = True
                            break
                    
                    if has_free:
                        day_status[d] = "partial"
                    else:
                        day_status[d] = "full"
            except Exception:
                break
    
    await call.message.edit_reply_markup(reply_markup=calendar_markup(year=year, month=month, mode=mode, day_status=day_status))
    await call.answer()


@router.callback_query(F.data.startswith("mon|"))
async def cb_calendar_month(call: CallbackQuery) -> None:
    _, mode, ym = call.data.split("|", 2)
    year_s, month_s = ym.split("-", 1)
    year = int(year_s)
    month = int(month_s)
    settings = get_settings()
    await init_db(settings.db_path)
    
    # Собираем статус дней
    day_status = {}
    if mode == "admin_all":
        all_bookings = await list_user_bookings(settings.db_path, user_id=None)
        for b in all_bookings:
            if b.date.startswith(f"{year:04d}-{month:02d}"):
                day_status[b.date] = day_status.get(b.date, 0) + 1
    else:
        for day in range(1, 32):
            try:
                d = f"{year:04d}-{month:02d}-{day:02d}"
                schedule = await get_day_schedule(settings.db_path, d)
                if not schedule.is_open:
                    day_status[d] = "full"
                    continue
                    
                available_hours = await list_available_hours(settings.db_path, d)
                all_bookings = await list_user_bookings(settings.db_path, user_id=None)
                day_bookings = [b for b in all_bookings if b.date == d and b.status == "approved"]
                
                if not day_bookings:
                    day_status[d] = "free"
                else:
                    # Проверяем, есть ли свободные часы
                    has_free = False
                    for hour in available_hours:
                        hour_booked = False
                        for b in day_bookings:
                            if hour >= b.start and hour < b.end:
                                hour_booked = True
                                break
                        if not hour_booked:
                            has_free = True
                            break
                    
                    if has_free:
                        day_status[d] = "partial"
                    else:
                        day_status[d] = "full"
            except Exception:
                break
    
    await call.message.edit_reply_markup(reply_markup=calendar_markup(year=year, month=month, mode=mode, day_status=day_status))
    await call.answer()


@router.callback_query(F.data.startswith("day|"))
async def cb_day_selected(call: CallbackQuery) -> None:
    _, mode, day = call.data.split("|", 2)
    settings = get_settings()
    await init_db(settings.db_path)

    if mode == "admin":
        if not call.from_user or not _is_admin(call.from_user.id):
            await call.answer("⛔️ Нет доступа", show_alert=True)
            return

        schedule = await get_day_schedule(settings.db_path, day)
        await call.message.edit_text(
            f"🗓 {day}\n\nНастройка дня:",
            reply_markup=admin_day_manage_markup(
                day=day,
                is_open=schedule.is_open,
                open_time=schedule.open_time,
                close_time=schedule.close_time,
            ),
        )
        await call.answer()
        return

    hours = await list_available_hours(settings.db_path, day)
    schedule = await get_day_schedule(settings.db_path, day)
    all_bookings = await list_user_bookings(settings.db_path, user_id=None)
    day_bookings = [b for b in all_bookings if b.date == day and b.status == "approved"]
    
    await call.message.edit_text(
        "⏰ Выбери начало записи:",
        reply_markup=time_range_markup(mode="user", day=day, schedule=schedule, step="start", bookings=day_bookings),
    )
    await call.answer()


@router.callback_query(F.data.startswith("hour|"))
async def cb_hour_selected(call: CallbackQuery) -> None:
    _, mode, day, hhmm = call.data.split("|", 3)
    if mode != "user":
        await call.answer()
        return

    settings = get_settings()
    await init_db(settings.db_path)

    if not call.from_user:
        await call.answer("Ошибка", show_alert=True)
        return

    schedule = await get_day_schedule(settings.db_path, day)
    state = _get_wizard(call.from_user.id)
    if not state or state["step"] not in {"time_start", "time_end"}:
        _set_wizard(call.from_user.id, step="time_start", data={"date": day})
        state = _get_wizard(call.from_user.id)

    if state["step"] == "time_start":
        state["data"]["start"] = hhmm
        _set_wizard(call.from_user.id, step="time_end", data=state["data"])
        
        all_bookings = await list_user_bookings(settings.db_path, user_id=None)
        day_bookings = [b for b in all_bookings if b.date == day and b.status == "approved"]
        
        await call.message.edit_text(
            f"🗓 {day}\n⏰ Начало: {hhmm}\n\nВыбери окончание:",
            reply_markup=time_range_markup(mode="user", day=day, schedule=schedule, step="end", start_time=hhmm, bookings=day_bookings),
        )
        await call.answer()
        return

    if state["step"] == "time_end":
        start = state["data"]["start"]
        if hhmm <= start:
            await call.answer("Окончание должно быть позже начала", show_alert=True)
            return
        
        duration = (int(hhmm[:2]) - int(start[:2])) * 60 + (int(hhmm[3:]) - int(start[3:]))
        
        state["data"]["end"] = hhmm
        state["data"]["duration"] = duration
        _set_wizard(call.from_user.id, step="montage", data=state["data"])
        await call.message.edit_text(
            f"🗓 {day}\n⏰ {start}–{hhmm}\n\nНужен ли монтаж?",
            reply_markup=montage_markup(),
        )
        await call.answer()
        return


@router.callback_query(F.data.startswith("mont|"))
async def cb_montage(call: CallbackQuery) -> None:
    if not call.from_user:
        await call.answer("Ошибка", show_alert=True)
        return

    _, yes_no = call.data.split("|", 1)
    montage = yes_no == "yes"
    state = _get_wizard(call.from_user.id)
    if not state or state["step"] != "montage":
        await call.answer("Сессия устарела. Начни заново.", show_alert=True)
        return

    data = state["data"]
    data["montage"] = montage
    price = 3000 * (data["duration"] // 60) + (1000 if montage else 0)
    data["price"] = price
    _set_wizard(call.from_user.id, step="confirm", data=data)

    montage_txt = "Да (+1000 ₽)" if montage else "Нет"
    await call.message.edit_text(
        f"📋 Проверь данные:\n\n"
        f"🗓 Дата: {data['date']}\n"
        f"⏰ Время: {data['start']}–{data['end']}\n"
        f"🎬 Монтаж: {montage_txt}\n"
        f"💰 Итого: {price} ₽\n\n"
        f"Выбери действие:",
        reply_markup=confirm_markup(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("conf|"))
async def cb_confirm(call: CallbackQuery) -> None:
    if not call.from_user:
        await call.answer("Ошибка", show_alert=True)
        return

    _, action = call.data.split("|", 1)
    state = _get_wizard(call.from_user.id)
    if not state or state["step"] != "confirm":
        await call.answer("Сессия устарела. Начни заново.", show_alert=True)
        return

    data = state["data"]

    if action == "ok":
        settings = get_settings()
        await init_db(settings.db_path)
        
        # Создаем запись сразу
        booking_id = await create_booking_pending(
            settings.db_path,
            user_id=call.from_user.id,
            chat_id=call.message.chat.id,
            username=call.from_user.username,
            full_name=call.from_user.full_name,
            date=data["date"],
            time=data["start"],
            duration_minutes=data["duration"],
            montage=data["montage"],
            comment=data.get("comment", ""),
            price_total=data["price"],
        )

        montage_txt = "Да" if data["montage"] else "Нет"
        await call.message.edit_text(
            f"✅ Заявка отправлена!\n\n"
            f"🗓 {data['date']}\n"
            f"⏰ {data['start']}–{data['end']}\n"
            f"🎬 Монтаж: {montage_txt}\n"
            f"💰 Итого: {data['price']} ₽\n"
            f"⏳ Статус: ожидает подтверждения администратора.",
        )

        text = (
            "🆕 Новая заявка на запись\n\n"
            f"👤 {call.from_user.full_name} (@{call.from_user.username})\n"
            f"🗓 {data['date']}\n"
            f"⏰ {data['start']}–{data['end']}\n"
            f"🎬 Монтаж: {montage_txt}\n"
            f"💰 Итого: {data['price']} ₽\n"
            f"💬 Комментарий: {data.get('comment', '—')}\n"
            f"🆔 Booking ID: {booking_id}"
        )

        for admin_id in settings.admin_ids:
            try:
                await call.bot.send_message(admin_id, text, reply_markup=admin_booking_decision_markup(booking_id=booking_id))
            except Exception:
                continue

        await call.answer("Отправлено на подтверждение ✅")
        _clear_wizard(call.from_user.id)
        return

    if action == "change":
        _set_wizard(call.from_user.id, step="time_start", data={"date": data["date"]})
        await call.message.edit_text(
            f"🗓 {data['date']}\n\n⏰ Выбери новое начало записи:",
            reply_markup=time_range_markup(mode="user", day=data["date"], schedule=await get_day_schedule(settings.db_path, data["date"]), step="start"),
        )
        await call.answer()
        return

    if action == "comment":
        _set_wizard(call.from_user.id, step="comment", data=data)
        await call.message.edit_text(
            f"🗓 {data['date']}\n⏰ {data['start']}–{data['end']}\n\n💬 Напиши комментарий к записи:",
        )
        await call.answer()
        return


@router.message(F.text)
async def msg_comment(message: Message) -> None:
    if not message.from_user:
        return

    state = _get_wizard(message.from_user.id)
    if not state or state["step"] != "confirm":
        return

    data = state["data"]
    data["comment"] = message.text
    _set_wizard(message.from_user.id, step="confirm", data=data)

    montage_txt = "Да (+1000 ₽)" if data["montage"] else "Нет"
    await message.answer(
        f"📋 Проверь данные:\n\n"
        f"🗓 Дата: {data['date']}\n"
        f"⏰ Время: {data['start']}–{data['end']}\n"
        f"🎬 Монтаж: {montage_txt}\n"
        f"💰 Итого: {data['price']} ₽\n"
        f"💬 Комментарий: {data.get('comment', '—')}\n\n"
        f"Выбери действие:",
        reply_markup=confirm_markup(),
    )


@router.callback_query(F.data.startswith("cancel|"))
async def cb_cancel(call: CallbackQuery) -> None:
    if not call.from_user:
        await call.answer("Ошибка", show_alert=True)
        return

    _, booking_id_s = call.data.split("|", 1)
    booking_id = int(booking_id_s)

    settings = get_settings()
    await init_db(settings.db_path)

    booking = await get_booking(settings.db_path, booking_id)
    ok = await cancel_booking(settings.db_path, booking_id=booking_id, user_id=call.from_user.id)
    if not ok:
        await call.answer("Не удалось отменить", show_alert=True)
        return

    await call.message.edit_text("❌ Запись отменена")
    await call.answer("Отменено")

    if booking and booking.status == "approved":
        for admin_id in settings.admin_ids:
            try:
                await call.bot.send_message(
                    admin_id,
                    f"❌ Пользователь отменил запись\n\n👤 {booking.full_name or booking.username or booking.user_id}\n🗓 {booking.date} ⏰ {booking.time}",
                )
            except Exception:
                continue


@router.callback_query(F.data.startswith("admin|"))
async def cb_admin_menu(call: CallbackQuery) -> None:
    if not call.from_user or not _is_admin(call.from_user.id):
        await call.answer("⛔️ Нет доступа", show_alert=True)
        return

    settings = get_settings()
    await init_db(settings.db_path)

    _, action = call.data.split("|", 1)
    if action == "all":
        settings = get_settings()
        await init_db(settings.db_path)
        
        all_bookings = await list_user_bookings(settings.db_path, user_id=None)
        if not all_bookings:
            await call.message.edit_text("📅 Все записи\n\nНет записей в системе.", reply_markup=admin_menu_markup())
            await call.answer()
            return
        
        # Группируем по датам
        by_date = {}
        for b in all_bookings:
            if b.date not in by_date:
                by_date[b.date] = []
            by_date[b.date].append(b)
        
        lines = ["📅 Все записи:"]
        for date_str in sorted(by_date.keys()):
            lines.append(f"\n🗓 {date_str}")
            for b in by_date[date_str]:
                status_icon = {"approved": "✅", "pending": "⏳", "rejected": "❌"}.get(b.status, "❓")
                comment = f" 💬 {b.comment}" if b.comment else ""
                cancel_btn = f" [❌ Отменить]" if b.status == "approved" else ""
                lines.append(
                    f"{status_icon} {b.start}–{b.end} | {b.full_name} (@{b.username}) | {b.price_total}₽{comment}{cancel_btn}"
                )
        
        # Создаем кнопки для отмены одобренных записей
        builder = InlineKeyboardBuilder()
        for date_str in sorted(by_date.keys()):
            for b in by_date[date_str]:
                if b.status == "approved":
                    builder.button(text=f"❌ {b.full_name} ({b.start})", callback_data=f"cancel_booking|{b.id}")
        builder.button(text="⬅️ Назад", callback_data="admin_menu")
        builder.adjust(1)
        
        await call.message.edit_text("\n".join(lines), reply_markup=builder.as_markup())
        await call.answer()
        return

    if action == "pending":
        items = await list_pending_bookings(settings.db_path)
        if not items:
            await call.message.edit_text("✅ Нет заявок", reply_markup=admin_menu_markup())
            await call.answer()
            return

        await call.message.edit_text(f"✅ Заявки: {len(items)} шт.\n\nЯ отправлю их отдельными сообщениями.")
        for b in items:
            title = f"🆕 Заявка\n\n👤 {b.full_name or b.username or b.user_id}\n🗓 {b.date} ⏰ {b.time}\n🆔 {b.id}"
            await call.bot.send_message(call.from_user.id, title, reply_markup=admin_booking_decision_markup(booking_id=b.id))
        await call.answer()
        return

    if action == "calendar":
        settings = get_settings()
        await init_db(settings.db_path)
        year, month = _today_ym()
        
        # Собираем статус дней для админ-календаря
        day_status = {}
        for day in range(1, 32):
            try:
                d = f"{year:04d}-{month:02d}-{day:02d}"
                schedule = await get_day_schedule(settings.db_path, d)
                if not schedule.is_open:
                    day_status[d] = "full"  # студия закрыта
                    continue
                    
                available_hours = await list_available_hours(settings.db_path, d)
                all_bookings = await list_user_bookings(settings.db_path, user_id=None)
                day_bookings = [b for b in all_bookings if b.date == d and b.status == "approved"]
                
                if not day_bookings:
                    day_status[d] = "free"  # полностью свободен
                else:
                    # Проверяем, есть ли свободные часы
                    has_free = False
                    for hour in available_hours:
                        hour_booked = False
                        for b in day_bookings:
                            if hour >= b.start and hour < b.end:
                                hour_booked = True
                                break
                        if not hour_booked:
                            has_free = True
                            break
                    
                    if has_free:
                        day_status[d] = "partial"  # частично занят
                    else:
                        day_status[d] = "full"  # полностью занят
            except Exception:
                break
        
        await call.message.edit_text(
            "📆 Управление календарём: выбери день",
            reply_markup=calendar_markup(year=year, month=month, mode="admin", day_status=day_status),
        )
        await call.answer()
        return

    if action == "default":
        sch = await get_default_schedule(settings.db_path)
        await call.message.edit_text(
            "⏰ Часы по умолчанию (на все дни):",
            reply_markup=admin_default_manage_markup(
                is_open=sch.is_open,
                open_time=sch.open_time,
                close_time=sch.close_time,
                slot_minutes=sch.slot_minutes,
            ),
        )
        await call.answer()
        return

    await call.answer()


@router.callback_query(F.data.startswith("cancel_booking|"))
async def cb_cancel_booking_admin(call: CallbackQuery) -> None:
    if not call.from_user or not _is_admin(call.from_user.id):
        await call.answer("⛔️ Нет доступа", show_alert=True)
        return

    _, booking_id_s = call.data.split("|", 1)
    booking_id = int(booking_id_s)
    settings = get_settings()
    await init_db(settings.db_path)

    booking = await get_booking(settings.db_path, booking_id)
    if not booking:
        await call.answer("Запись не найдена", show_alert=True)
        return

    ok = await cancel_booking(settings.db_path, booking_id=booking_id, user_id=booking.user_id)
    if not ok:
        await call.answer("Не удалось отменить", show_alert=True)
        return

    # Уведомляем пользователя
    try:
        await call.bot.send_message(
            booking.chat_id,
            f"❌ Ваша запись отменена администратором\n\n🗓 {booking.date} ⏰ {booking.start}–{booking.end}"
        )
    except Exception:
        pass

    await call.answer("Запись отменена ✅")
    await call.message.edit_text(f"❌ Запись {booking.full_name} отменена")


@router.callback_query(F.data.startswith("appr|"))
async def cb_approve(call: CallbackQuery) -> None:
    if not call.from_user or not _is_admin(call.from_user.id):
        await call.answer("⛔️ Нет доступа", show_alert=True)
        return

    _, decision, booking_id_s = call.data.split("|", 2)
    booking_id = int(booking_id_s)
    settings = get_settings()
    await init_db(settings.db_path)

    booking = await get_booking(settings.db_path, booking_id)
    if not booking or booking.status != "pending":
        await call.answer("Заявка уже обработана", show_alert=True)
        return

    if decision == "ok":
        taken = await has_approved_booking(settings.db_path, date=booking.date, time=booking.time)
        if taken:
            await set_booking_status(settings.db_path, booking_id=booking_id, status="rejected", approved_by=call.from_user.id)
            await call.bot.send_message(booking.chat_id, f"❌ Увы, слот уже занят: 🗓 {booking.date} ⏰ {booking.time}")
            await call.message.edit_text("❌ Отклонено (слот уже занят)")
            await call.answer()
            return

        await set_booking_status(settings.db_path, booking_id=booking_id, status="approved", approved_by=call.from_user.id)
        await call.bot.send_message(
            booking.chat_id,
            f"✅ Запись подтверждена!\n\n🎙️ Ждём тебя в студии\n🗓 {booking.date}\n⏰ {booking.time}",
        )

        for admin_id in settings.admin_ids:
            try:
                await call.bot.send_message(
                    admin_id,
                    f"✅ Заявка одобрена\n\n👤 {booking.full_name or booking.username or booking.user_id}\n🗓 {booking.date} ⏰ {booking.time}",
                )
            except Exception:
                continue

        await call.message.edit_text("✅ Одобрено")
        await call.answer("Одобрено")
        return

    await set_booking_status(settings.db_path, booking_id=booking_id, status="rejected", approved_by=call.from_user.id)
    await call.bot.send_message(booking.chat_id, f"❌ Заявка отклонена\n\n🗓 {booking.date} ⏰ {booking.time}")
    await call.message.edit_text("❌ Отклонено")
    await call.answer("Отклонено")


@router.callback_query(F.data.startswith("admday|"))
async def cb_admin_day_manage(call: CallbackQuery) -> None:
    if not call.from_user or not _is_admin(call.from_user.id):
        await call.answer("⛔️ Нет доступа", show_alert=True)
        return

    _, action, day = call.data.split("|", 2)
    settings = get_settings()
    await init_db(settings.db_path)

    schedule = await get_day_schedule(settings.db_path, day)
    if action == "toggle":
        await set_day_override(
            settings.db_path,
            date=day,
            is_open=not schedule.is_open,
            open_time=schedule.open_time,
            close_time=schedule.close_time,
        )
        schedule = await get_day_schedule(settings.db_path, day)

        await call.message.edit_reply_markup(
            reply_markup=admin_day_manage_markup(
                day=day,
                is_open=schedule.is_open,
                open_time=schedule.open_time,
                close_time=schedule.close_time,
            )
        )
        await call.answer("Обновлено")
        return

    if action in {"open", "close"}:
        await call.message.edit_text(
            f"⏰ Выбор времени для {day}",
            reply_markup=pick_hour_markup(action=action, day=day),
        )
        await call.answer()
        return

    await call.answer()


@router.callback_query(F.data.startswith("sethour|"))
async def cb_sethour(call: CallbackQuery) -> None:
    if not call.from_user or not _is_admin(call.from_user.id):
        await call.answer("⛔️ Нет доступа", show_alert=True)
        return

    _, action, day, hhmm = call.data.split("|", 3)
    settings = get_settings()
    await init_db(settings.db_path)

    if day == "default" and action in {"defopen", "defclose"}:
        sch = await get_default_schedule(settings.db_path)
        if action == "defopen":
            await set_default_schedule(
                settings.db_path,
                is_open=sch.is_open,
                open_time=hhmm,
                close_time=sch.close_time,
                slot_minutes=sch.slot_minutes,
            )
        else:
            await set_default_schedule(
                settings.db_path,
                is_open=sch.is_open,
                open_time=sch.open_time,
                close_time=hhmm,
                slot_minutes=sch.slot_minutes,
            )

        sch = await get_default_schedule(settings.db_path)
        await call.message.edit_text(
            "⏰ Часы по умолчанию (на все дни):",
            reply_markup=admin_default_manage_markup(
                is_open=sch.is_open,
                open_time=sch.open_time,
                close_time=sch.close_time,
                slot_minutes=sch.slot_minutes,
            ),
        )
        await call.answer("Сохранено")
        return

    schedule = await get_day_schedule(settings.db_path, day)
    if action == "open":
        await set_day_override(
            settings.db_path,
            date=day,
            is_open=schedule.is_open,
            open_time=hhmm,
            close_time=schedule.close_time,
        )
    elif action == "close":
        await set_day_override(
            settings.db_path,
            date=day,
            is_open=schedule.is_open,
            open_time=schedule.open_time,
            close_time=hhmm,
        )

    schedule = await get_day_schedule(settings.db_path, day)
    await call.message.edit_text(
        f"🗓 {day}\n\nНастройка дня:",
        reply_markup=admin_day_manage_markup(
            day=day,
            is_open=schedule.is_open,
            open_time=schedule.open_time,
            close_time=schedule.close_time,
        ),
    )
    await call.answer("Сохранено")


@router.callback_query(F.data.startswith("def|"))
async def cb_default_schedule(call: CallbackQuery) -> None:
    if not call.from_user or not _is_admin(call.from_user.id):
        await call.answer("⛔️ Нет доступа", show_alert=True)
        return

    settings = get_settings()
    await init_db(settings.db_path)
    _, action = call.data.split("|", 1)

    sch = await get_default_schedule(settings.db_path)

    if action == "toggle":
        await set_default_schedule(
            settings.db_path,
            is_open=not sch.is_open,
            open_time=sch.open_time,
            close_time=sch.close_time,
            slot_minutes=sch.slot_minutes,
        )
        sch = await get_default_schedule(settings.db_path)
        await call.message.edit_reply_markup(
            reply_markup=admin_default_manage_markup(
                is_open=sch.is_open,
                open_time=sch.open_time,
                close_time=sch.close_time,
                slot_minutes=sch.slot_minutes,
            )
        )
        await call.answer("Обновлено")
        return

    if action in {"open", "close"}:
        await call.message.edit_text(
            "⏰ Выбери час:",
            reply_markup=pick_hour_markup(action=f"def{action}", day="default"),
        )
        await call.answer()
        return

    if action == "slot":
        await call.message.edit_text("⏱ Длительность слота:", reply_markup=pick_slot_minutes_markup())
        await call.answer()
        return

    await call.answer()


@router.callback_query(F.data.startswith("defslot|"))
async def cb_default_slot(call: CallbackQuery) -> None:
    if not call.from_user or not _is_admin(call.from_user.id):
        await call.answer("⛔️ Нет доступа", show_alert=True)
        return

    _, minutes_s = call.data.split("|", 1)
    minutes = int(minutes_s)
    settings = get_settings()
    await init_db(settings.db_path)
    sch = await get_default_schedule(settings.db_path)
    await set_default_schedule(
        settings.db_path,
        is_open=sch.is_open,
        open_time=sch.open_time,
        close_time=sch.close_time,
        slot_minutes=minutes,
    )
    sch = await get_default_schedule(settings.db_path)
    await call.message.edit_text(
        "⏰ Часы по умолчанию (на все дни):",
        reply_markup=admin_default_manage_markup(
            is_open=sch.is_open,
            open_time=sch.open_time,
            close_time=sch.close_time,
            slot_minutes=sch.slot_minutes,
        ),
    )
    await call.answer("Сохранено")
