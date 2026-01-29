from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime

import aiosqlite


@dataclass(frozen=True)
class DaySchedule:
    is_open: bool
    open_time: str
    close_time: str
    slot_minutes: int


@dataclass(frozen=True)
class Booking:
    id: int
    user_id: int
    chat_id: int
    username: str | None
    full_name: str | None
    date: str
    time: str
    duration_minutes: int
    montage: bool
    comment: str | None
    price_total: int
    status: str
    created_at: str
    approved_by: int | None
    reminder_day_sent: bool
    reminder_hour_sent: bool

    @property
    def start(self) -> str:
        return self.time

    @property
    def end(self) -> str:
        start_minutes = _time_to_minutes(self.time)
        end_minutes = start_minutes + self.duration_minutes
        return _minutes_to_hhmm(end_minutes)


def _ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def _parse_hhmm(value: str) -> tuple[int, int]:
    hh, mm = value.split(":")
    return int(hh), int(mm)


def _time_to_minutes(hhmm: str) -> int:
    hh, mm = _parse_hhmm(hhmm)
    return hh * 60 + mm


def _minutes_to_hhmm(minutes: int) -> str:
    hh = minutes // 60
    mm = minutes % 60
    return f"{hh:02d}:{mm:02d}"


async def init_db(db_path: str) -> None:
    _ensure_parent_dir(db_path)

    async with aiosqlite.connect(db_path) as db:
        # Таблица заблокированных пользователей
        await db.execute(
            "CREATE TABLE IF NOT EXISTS banned_users (user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT, banned_at TEXT, banned_by INTEGER, reason TEXT)"
        )
        
        # Таблица расписания по умолчанию
        await db.execute(
            "CREATE TABLE IF NOT EXISTS default_schedule (id INTEGER PRIMARY KEY, is_open INTEGER NOT NULL, open_time TEXT NOT NULL, close_time TEXT NOT NULL, slot_minutes INTEGER NOT NULL)"
        )
        
        # Таблица исключений по дням
        await db.execute(
            "CREATE TABLE IF NOT EXISTS day_overrides (date TEXT PRIMARY KEY, is_open INTEGER NOT NULL, open_time TEXT, close_time TEXT)"
        )
        
        # Таблица бронирований
        await db.execute(
            "CREATE TABLE IF NOT EXISTS bookings (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, chat_id INTEGER NOT NULL, username TEXT, full_name TEXT, date TEXT NOT NULL, time TEXT NOT NULL, duration_minutes INTEGER NOT NULL, montage INTEGER NOT NULL, comment TEXT, price_total INTEGER NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, approved_by INTEGER, reminder_day_sent INTEGER NOT NULL DEFAULT 0, reminder_hour_sent INTEGER NOT NULL DEFAULT 0)"
        )
        
        # Расписание по умолчанию
        await db.execute(
            "INSERT OR IGNORE INTO default_schedule (id, is_open, open_time, close_time, slot_minutes) VALUES (1, 1, '09:00', '21:00', 60)"
        )
        
        await db.commit()


async def _migrate_bookings(db: aiosqlite.Connection) -> None:
    migrations = [
        ("duration_minutes", "INTEGER NOT NULL DEFAULT 60"),
        ("montage", "INTEGER NOT NULL DEFAULT 0"),
        ("comment", "TEXT"),
        ("price_total", "INTEGER NOT NULL DEFAULT 0"),
    ]

    for name, sql_type in migrations:
        try:
            await db.execute(f"ALTER TABLE bookings ADD COLUMN {name} {sql_type}")
        except aiosqlite.OperationalError:
            continue


async def get_default_schedule(db_path: str) -> DaySchedule:
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT is_open, open_time, close_time, slot_minutes FROM default_schedule WHERE id = 1"
        )
        row = await cur.fetchone()
        if not row:
            raise RuntimeError("default_schedule is not initialized")
        return DaySchedule(bool(row[0]), row[1], row[2], int(row[3]))


async def set_default_schedule(
    db_path: str,
    *,
    is_open: bool,
    open_time: str,
    close_time: str,
    slot_minutes: int,
) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE default_schedule SET is_open = ?, open_time = ?, close_time = ?, slot_minutes = ? WHERE id = 1",
            (1 if is_open else 0, open_time, close_time, slot_minutes),
        )
        await db.commit()


async def get_day_schedule(db_path: str, date: str) -> DaySchedule:
    default = await get_default_schedule(db_path)

    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT is_open, open_time, close_time FROM day_overrides WHERE date = ?",
            (date,),
        )
        row = await cur.fetchone()

    if not row:
        return default

    is_open = bool(row[0])
    open_time = row[1] or default.open_time
    close_time = row[2] or default.close_time
    return DaySchedule(is_open, open_time, close_time, default.slot_minutes)


async def set_day_override(
    db_path: str,
    *,
    date: str,
    is_open: bool,
    open_time: str | None = None,
    close_time: str | None = None,
) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO day_overrides(date, is_open, open_time, close_time) VALUES(?, ?, ?, ?) "
            "ON CONFLICT(date) DO UPDATE SET is_open = excluded.is_open, open_time = excluded.open_time, close_time = excluded.close_time",
            (date, 1 if is_open else 0, open_time, close_time),
        )
        await db.commit()


async def list_available_hours(db_path: str, date: str) -> list[str]:
    schedule = await get_day_schedule(db_path, date)
    if not schedule.is_open:
        return []

    start = _time_to_minutes(schedule.open_time)
    end = _time_to_minutes(schedule.close_time)
    step = schedule.slot_minutes

    if end <= start or step <= 0:
        return []

    hours: list[str] = []
    t = start
    while t + step <= end:
        hours.append(_minutes_to_hhmm(t))
        t += step

    if not hours:
        return []

    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT time FROM bookings WHERE date = ? AND status = 'approved'",
            (date,),
        )
        taken = {row[0] for row in await cur.fetchall()}

    return [h for h in hours if h not in taken]


async def create_booking_pending(
    db_path: str,
    *,
    user_id: int,
    chat_id: int,
    username: str | None,
    full_name: str | None,
    date: str,
    time: str,
    duration_minutes: int,
    montage: bool,
    comment: str | None,
    price_total: int,
) -> int:
    now = datetime.utcnow().isoformat(timespec="seconds")

    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT id FROM bookings WHERE date = ? AND time = ? AND status = 'approved'",
            (date, time),
        )
        row = await cur.fetchone()
        if row:
            raise ValueError("slot already taken")

        cur = await db.execute(
            "INSERT INTO bookings(user_id, chat_id, username, full_name, date, time, duration_minutes, montage, comment, price_total, status, created_at) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
            (
                user_id,
                chat_id,
                username,
                full_name,
                date,
                time,
                duration_minutes,
                1 if montage else 0,
                comment,
                price_total,
                now,
            ),
        )
        await db.commit()
        return int(cur.lastrowid)


async def cancel_booking(db_path: str, *, booking_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "UPDATE bookings SET status = 'cancelled' WHERE id = ? AND user_id = ? AND status IN ('pending', 'approved')",
            (booking_id, user_id),
        )
        await db.commit()
        return cur.rowcount > 0


async def has_approved_booking(db_path: str, *, date: str, time: str) -> bool:
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT 1 FROM bookings WHERE date = ? AND time = ? AND status = 'approved' LIMIT 1",
            (date, time),
        )
        return await cur.fetchone() is not None


async def set_booking_status(
    db_path: str,
    *,
    booking_id: int,
    status: str,
    approved_by: int | None = None,
) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE bookings SET status = ?, approved_by = ? WHERE id = ?",
            (status, approved_by, booking_id),
        )
        await db.commit()


async def mark_reminder_sent(db_path: str, *, booking_id: int, kind: str) -> None:
    field = "reminder_day_sent" if kind == "day" else "reminder_hour_sent"
    async with aiosqlite.connect(db_path) as db:
        await db.execute(f"UPDATE bookings SET {field} = 1 WHERE id = ?", (booking_id,))
        await db.commit()


def _row_to_booking(row: tuple) -> Booking:
    return Booking(
        id=int(row[0]),
        user_id=int(row[1]),
        chat_id=int(row[2]),
        username=row[3],
        full_name=row[4],
        date=row[5],
        time=row[6],
        duration_minutes=int(row[7]),
        montage=bool(row[8]),
        comment=row[9],
        price_total=int(row[10]),
        status=row[11],
        created_at=row[12],
        approved_by=row[13],
        reminder_day_sent=bool(row[14]),
        reminder_hour_sent=bool(row[15]),
    )


async def get_booking(db_path: str, booking_id: int) -> Booking | None:
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT id, user_id, chat_id, username, full_name, date, time, duration_minutes, montage, comment, price_total, status, created_at, approved_by, reminder_day_sent, reminder_hour_sent "
            "FROM bookings WHERE id = ?",
            (booking_id,),
        )
        row = await cur.fetchone()
        return _row_to_booking(row) if row else None


async def list_user_bookings(db_path: str, user_id: int | None = None) -> list[Booking]:
    async with aiosqlite.connect(db_path) as db:
        if user_id is None:
            # Получаем все записи (без временных блокировок)
            cur = await db.execute(
                "SELECT id, user_id, chat_id, username, full_name, date, time, duration_minutes, montage, comment, price_total, status, created_at, approved_by, reminder_day_sent, reminder_hour_sent "
                "FROM bookings WHERE status IN ('pending', 'approved') ORDER BY date, time"
            )
        else:
            # Получаем записи конкретного пользователя
            cur = await db.execute(
                "SELECT id, user_id, chat_id, username, full_name, date, time, duration_minutes, montage, comment, price_total, status, created_at, approved_by, reminder_day_sent, reminder_hour_sent "
                "FROM bookings WHERE user_id = ? AND status IN ('pending', 'approved') ORDER BY date, time",
                (user_id,),
            )
        rows = await cur.fetchall()
        return [_row_to_booking(r) for r in rows]


async def list_pending_bookings(db_path: str) -> list[Booking]:
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT id, user_id, chat_id, username, full_name, date, time, duration_minutes, montage, comment, price_total, status, created_at, approved_by, reminder_day_sent, reminder_hour_sent "
            "FROM bookings WHERE status = 'pending' ORDER BY created_at",
        )
        rows = await cur.fetchall()
        return [_row_to_booking(r) for r in rows]


async def create_temp_lock(db_path: str, *, user_id: int, date: str, start_time: str, end_time: str) -> bool:
    """Создает временную блокировку слота. Возвращает True если успешно."""
    async with aiosqlite.connect(db_path) as db:
        try:
            # Проверяем, нет ли уже блокировки или записи на этот слот
            cur = await db.execute(
                """
                SELECT COUNT(*) FROM bookings 
                WHERE date = ? AND status IN ('pending', 'approved') AND (
                    (time <= ? AND datetime(time, '+' || duration_minutes || ' minutes') > ?) OR
                    (time < ? AND datetime(time, '+' || duration_minutes || ' minutes') >= ?) OR
                    (time >= ? AND datetime(time, '+' || duration_minutes || ' minutes') <= ?)
                )
                """,
                (date, start_time, start_time, end_time, end_time, start_time, end_time)
            )
            count = (await cur.fetchone())[0]
            
            if count > 0:
                return False  # Слот уже занят
            
            # Создаем временную блокировку
            await db.execute(
                """
                INSERT INTO bookings (
                    user_id, chat_id, username, full_name, date, time, duration_minutes,
                    montage, comment, price_total, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'temp_locked', datetime('now'))
                """,
                (user_id, user_id, None, None, date, start_time, 
                 int((int(end_time[:2]) - int(start_time[:2])) * 60 + (int(end_time[3:]) - int(start_time[3:]))),
                 False, None, 0)
            )
            await db.commit()
            return True
        except Exception:
            return False


async def remove_temp_lock(db_path: str, *, user_id: int, date: str, start_time: str) -> None:
    """Удаляет временную блокировку."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "DELETE FROM bookings WHERE user_id = ? AND date = ? AND time = ? AND status = 'temp_locked'",
            (user_id, date, start_time)
        )
        await db.commit()


async def convert_temp_to_pending(db_path: str, *, user_id: int, date: str, start_time: str, 
                                chat_id: int, username: str, full_name: str, montage: bool, 
                                comment: str, price_total: int) -> int | None:
    """Преобразует временную блокировку в полноценную заявку. Возвращает ID записи."""
    async with aiosqlite.connect(db_path) as db:
        # Находим временную блокировку
        cur = await db.execute(
            "SELECT id, duration_minutes FROM bookings WHERE user_id = ? AND date = ? AND time = ? AND status = 'temp_locked'",
            (user_id, date, start_time)
        )
        row = await cur.fetchone()
        if not row:
            return None
        
        booking_id, duration = row
        
        # Обновляем запись
        await db.execute(
            """
            UPDATE bookings SET 
                chat_id = ?, username = ?, full_name = ?, montage = ?, comment = ?, 
                price_total = ?, status = 'pending', created_at = datetime('now')
            WHERE id = ?
            """,
            (chat_id, username, full_name, montage, comment, price_total, booking_id)
        )
        await db.commit()
        return booking_id


async def cleanup_expired_locks(db_path: str) -> None:
    """Удаляет просроченные блокировки (старше 10 минут)."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "DELETE FROM bookings WHERE status = 'temp_locked' AND datetime(created_at, '+10 minutes') < datetime('now')"
        )
        await db.commit()


async def ban_user(db_path: str, *, user_id: int, username: str, full_name: str, banned_by: int, reason: str) -> None:
    """Блокирует пользователя."""
    from datetime import datetime
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO banned_users (user_id, username, full_name, banned_by, reason, banned_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, username, full_name, banned_by, reason, datetime.now().isoformat())
        )
        await db.commit()


async def unban_user(db_path: str, *, user_id: int) -> None:
    """Разблокирует пользователя."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("DELETE FROM banned_users WHERE user_id = ?", (user_id,))
        await db.commit()


async def is_user_banned(db_path: str, *, user_id: int) -> bool:
    """Проверяет, заблокирован ли пользователь."""
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute("SELECT COUNT(*) FROM banned_users WHERE user_id = ?", (user_id,))
        count = (await cur.fetchone())[0]
        return count > 0


async def list_banned_users(db_path: str) -> list[dict]:
    """Возвращает список заблокированных пользователей."""
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT user_id, username, full_name, banned_at, banned_by, reason FROM banned_users ORDER BY banned_at DESC"
        )
        rows = await cur.fetchall()
        return [
            {
                "user_id": row[0],
                "username": row[1],
                "full_name": row[2],
                "banned_at": row[3],
                "banned_by": row[4],
                "reason": row[5],
            }
            for row in rows
        ]


async def list_bookings_needing_reminders(db_path: str) -> list[Booking]:
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT id, user_id, chat_id, username, full_name, date, time, duration_minutes, montage, comment, price_total, status, created_at, approved_by, reminder_day_sent, reminder_hour_sent "
            "FROM bookings WHERE status = 'approved' AND (reminder_day_sent = 0 OR reminder_hour_sent = 0)",
        )
        rows = await cur.fetchall()
        return [_row_to_booking(r) for r in rows]
