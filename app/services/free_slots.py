from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import MOSCOW_TZ
from app.db.models import Booking, Room, ScheduleSlot
from app.db.repositories.room_repo import RoomRepository

WORK_DAY_START = time(8, 0)
WORK_DAY_END = time(21, 0)
MIN_WINDOW_MINUTES = 30


@dataclass(frozen=True)
class FreeWindow:
    start: time
    end: time

    def contains(self, t: time) -> bool:
        return self.start <= t < self.end

    def covers(self, start: time, end: time) -> bool:
        return self.start <= start and end <= self.end


def _minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def compute_free_windows(busy: list[tuple[time, time]]) -> list[FreeWindow]:
    """Compute free windows inside the work day given a list of busy intervals.

    Busy intervals are merged; gaps shorter than MIN_WINDOW_MINUTES are dropped.
    """
    clipped: list[tuple[time, time]] = []
    for start, end in busy:
        s = max(start, WORK_DAY_START)
        e = min(end, WORK_DAY_END)
        if s < e:
            clipped.append((s, e))

    clipped.sort()
    merged: list[tuple[time, time]] = []
    for s, e in clipped:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))

    free: list[tuple[time, time]] = []
    cursor = WORK_DAY_START
    for s, e in merged:
        if s > cursor:
            free.append((cursor, s))
        if e > cursor:
            cursor = e
    if cursor < WORK_DAY_END:
        free.append((cursor, WORK_DAY_END))

    return [
        FreeWindow(start=s, end=e)
        for s, e in free
        if _minutes(e) - _minutes(s) >= MIN_WINDOW_MINUTES
    ]


def _clip_dt_to_date(dt: datetime, on_date: date) -> time:
    if dt.tzinfo is not None:
        dt = dt.astimezone(MOSCOW_TZ)
    if dt.date() < on_date:
        return time(0, 0)
    if dt.date() > on_date:
        return time(23, 59, 59)
    return dt.replace(tzinfo=None).time()


async def _busy_per_room_on_date(
    session: AsyncSession, on_date: date,
) -> dict[int, list[tuple[time, time]]]:
    day_start = datetime.combine(on_date, time(0, 0), tzinfo=MOSCOW_TZ)
    day_end = day_start + timedelta(days=1)

    slots_q = select(
        ScheduleSlot.room_id, ScheduleSlot.starts_at, ScheduleSlot.ends_at,
    ).where(ScheduleSlot.date == on_date)
    bookings_q = select(
        Booking.room_id, Booking.starts_at, Booking.ends_at,
    ).where(
        Booking.is_active.is_(True),
        Booking.starts_at < day_end,
        Booking.ends_at > day_start,
    )

    busy: dict[int, list[tuple[time, time]]] = {}
    for q in (slots_q, bookings_q):
        rows = (await session.execute(q)).all()
        for room_id, starts_at, ends_at in rows:
            s_t = _clip_dt_to_date(starts_at, on_date)
            e_t = _clip_dt_to_date(ends_at, on_date)
            busy.setdefault(room_id, []).append((s_t, e_t))
    return busy


async def get_free_windows(
    session: AsyncSession, room_id: int, on_date: date,
) -> list[FreeWindow]:
    """Free windows of a single room on a given date."""
    busy = await _busy_per_room_on_date(session, on_date)
    return compute_free_windows(busy.get(room_id, []))


async def list_rooms_with_windows(
    session: AsyncSession, on_date: date,
) -> list[tuple[Room, list[FreeWindow]]]:
    """All active rooms that have at least one free window on the date."""
    rooms = await RoomRepository(session).get_all_active()
    busy = await _busy_per_room_on_date(session, on_date)
    result: list[tuple[Room, list[FreeWindow]]] = []
    for room in rooms:
        windows = compute_free_windows(busy.get(room.id, []))
        if windows:
            result.append((room, windows))
    return result


def find_window_for(windows: list[FreeWindow], start: time, end: time) -> FreeWindow | None:
    for w in windows:
        if w.covers(start, end):
            return w
    return None


def format_windows(windows: list[FreeWindow]) -> str:
    return ", ".join(f"{w.start.strftime('%H:%M')}–{w.end.strftime('%H:%M')}" for w in windows)
