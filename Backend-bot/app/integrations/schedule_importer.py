from __future__ import annotations

import csv
import io
import logging
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Protocol

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import MOSCOW_TZ
from app.db.models import RoomUnavailability


logger = logging.getLogger(__name__)


@dataclass
class ScheduleSlot:
    room_id: int
    starts_at: datetime
    ends_at: datetime
    source_external_id: str | None = None
    comment: str | None = None


class ScheduleProvider(Protocol):
    def load_slots(self) -> list[ScheduleSlot]: ...


def _parse_dt(raw: str, primary: str = "%Y-%m-%d %H:%M") -> datetime:
    value = raw.strip()
    for fmt in (primary, "%d.%m.%Y %H:%M"):
        try:
            naive = datetime.strptime(value, fmt)
            return naive.replace(tzinfo=MOSCOW_TZ)
        except ValueError:
            continue
    raise ValueError(f"Неверный формат даты: {value}")


def _rows_to_slots(reader: csv.DictReader) -> list[ScheduleSlot]:
    required = {"room_id", "starts_at", "ends_at"}
    if not required.issubset(set(reader.fieldnames or [])):
        raise ValueError("CSV должен содержать колонки: room_id, starts_at, ends_at.")
    slots: list[ScheduleSlot] = []
    for row in reader:
        slots.append(
            ScheduleSlot(
                room_id=int(row["room_id"].strip()),
                starts_at=_parse_dt(row["starts_at"]),
                ends_at=_parse_dt(row["ends_at"]),
                source_external_id=(row.get("external_id") or "").strip() or None,
                comment=(row.get("comment") or "").strip() or None,
            )
        )
    return slots


class CsvScheduleProvider:
    """Load schedule from a CSV file on disk or from raw bytes (Telegram upload)."""

    def __init__(
        self,
        file_path: str | Path | None = None,
        content: bytes | None = None,
        dt_format: str = "%Y-%m-%d %H:%M",
    ) -> None:
        self.file_path = Path(file_path) if file_path else None
        self.content = content
        self.dt_format = dt_format

    def load_slots(self) -> list[ScheduleSlot]:
        if self.content is not None:
            text_content = self.content.decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(text_content))
            return _rows_to_slots(reader)
        if self.file_path is not None:
            with self.file_path.open("r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                return _rows_to_slots(reader)
        raise ValueError("Укажите file_path или content.")


class ScheduleImporter:
    def __init__(self, session: AsyncSession, provider: ScheduleProvider) -> None:
        self.session = session
        self.provider = provider

    async def import_schedule(self, source: str = "schedule_csv", replace_source: bool = True) -> int:
        slots = self.provider.load_slots()
        valid = [s for s in slots if s.starts_at < s.ends_at]

        seen: dict[tuple[int, datetime, datetime], ScheduleSlot] = {}
        for slot in valid:
            seen[(slot.room_id, slot.starts_at, slot.ends_at)] = slot
        final = list(seen.values())

        if self.session.in_transaction():
            await self._apply(final, source, replace_source)
            return len(final)

        async with self.session.begin():
            await self._apply(final, source, replace_source)
        return len(final)

    async def _apply(self, slots: list[ScheduleSlot], source: str, replace: bool) -> None:
        if replace:
            await self.session.execute(
                delete(RoomUnavailability).where(RoomUnavailability.source == source)
            )
        self.session.add_all(
            [
                RoomUnavailability(
                    room_id=s.room_id,
                    starts_at=s.starts_at,
                    ends_at=s.ends_at,
                    source=source,
                    source_external_id=s.source_external_id,
                    comment=s.comment,
                )
                for s in slots
            ]
        )
        await self.session.flush()


GOOGLE_SHEETS_URL_RE = re.compile(
    r"https?://docs\.google\.com/spreadsheets/d/[A-Za-z0-9_-]+(?:/[^\s\"'<>]*)?"
)
MODULE_RANGE_RE = re.compile(r"\((\d{2}\.\d{2})\.\s*-\s*(\d{2}\.\d{2})\.\)")
TIME_RANGE_RE = re.compile(r"^\s*(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})\s*$")
WEEKDAY_RU = {
    "понедельник": 0,
    "вторник": 1,
    "среда": 2,
    "четверг": 3,
    "пятница": 4,
    "суббота": 5,
    "воскресенье": 6,
}
DATE_IN_TEXT_RE = re.compile(r"(\d{2}\.\d{2})(?:\.\d{4})?")
ROOM_CODE_RE = re.compile(r"(?<!\d)(\d{2,5})(?!\d)")
GROUP_RE = re.compile(r"^\d{2}[А-ЯA-Z][А-ЯA-Z0-9-]+$", re.IGNORECASE)
SHEET_ID_RE = re.compile(r"/spreadsheets/d/([A-Za-z0-9_-]+)")
GID_RE = re.compile(r"[?#&]gid=(\d+)")


def extract_google_sheets_urls(raw_text: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()

    def _collect(text: str) -> None:
        for match in GOOGLE_SHEETS_URL_RE.findall(text):
            normalized = match.rstrip(").,;\"'")
            if normalized not in seen:
                seen.add(normalized)
                urls.append(normalized)

    _collect(raw_text)
    decoded_once = urllib.parse.unquote(raw_text)
    _collect(decoded_once)
    decoded_twice = urllib.parse.unquote(decoded_once)
    _collect(decoded_twice)
    return urls


def google_sheet_export_csv_url(sheet_url: str) -> str:
    parsed = urllib.parse.urlparse(sheet_url.strip())
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 3 or parts[0] != "spreadsheets" or parts[1] != "d":
        raise ValueError(f"Некорректная ссылка Google Sheets: {sheet_url}")
    sheet_id = parts[2]
    qs = urllib.parse.parse_qs(parsed.query)
    fragment_qs = urllib.parse.parse_qs(parsed.fragment.lstrip("#"))
    gid = (
        (qs.get("gid") or [None])[0]
        or (fragment_qs.get("gid") or [None])[0]
        or "0"
    )
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"


def google_sheet_identity(sheet_url: str) -> tuple[str, str]:
    parsed = urllib.parse.urlparse(sheet_url.strip())
    match = SHEET_ID_RE.search(parsed.path)
    if not match:
        raise ValueError(f"Некорректная ссылка Google Sheets: {sheet_url}")
    sheet_id = match.group(1)
    qs = urllib.parse.parse_qs(parsed.query)
    fragment_qs = urllib.parse.parse_qs(parsed.fragment.lstrip("#"))
    gid = (
        (qs.get("gid") or [None])[0]
        or (fragment_qs.get("gid") or [None])[0]
        or "0"
    )
    return sheet_id, str(gid)


def compose_google_sheet_url(sheet_id: str, gid: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit?gid={gid}#gid={gid}"


def room_lookup_key(building_code: str, room_name: str) -> str:
    normalized_room = "".join(ch for ch in room_name.strip() if ch.isalnum())
    return f"{building_code.upper()}:{normalized_room.upper()}"


def extract_building_code(building_name: str) -> str:
    up = building_name.upper().replace("Ё", "Е")
    normalized = "".join(ch for ch in up if ch.isalnum())
    logger.debug("Normalize building name: raw=%r normalized=%r", building_name, normalized)
    alias_exact = {
        "БП": "Б",
        "Б": "Б",
        "К": "К",
        "Л": "Л",
        "Р": "Р",
        "С": "С",
    }
    if normalized in alias_exact:
        code = alias_exact[normalized]
        logger.debug("Building code matched exact alias: raw=%r code=%s", building_name, code)
        return code

    alias_contains = {
        "БПЕЧЕР": "Б",
        "КОСТИН": "К",
        "ЛЬВОВ": "Л",
        "РОДИОН": "Р",
        "СОРМОВ": "С",
    }
    for token, code in alias_contains.items():
        if token in normalized:
            logger.debug(
                "Building code matched partial alias: raw=%r token=%s code=%s",
                building_name,
                token,
                code,
            )
            return code

    marker = "КОРПУС "
    idx = up.find(marker)
    if idx != -1:
        tail = up[idx + len(marker):].strip()
        if tail:
            code = tail[0]
            logger.debug("Building code extracted after marker: raw=%r code=%s", building_name, code)
            return code
    for ch in up:
        if "А" <= ch <= "Я":
            logger.debug("Building code extracted from first Cyrillic letter: raw=%r code=%s", building_name, ch)
            return ch
    logger.debug("Building code was not detected: raw=%r", building_name)
    return ""


def build_room_lookup(rooms: list[object]) -> dict[str, int]:
    lookup: dict[str, int] = {}
    for room in rooms:
        room_id = getattr(room, "id")
        room_name = getattr(room, "name")
        building = getattr(room, "building", None)
        building_name = getattr(building, "name", "")
        building_address = getattr(building, "address", "")
        codes = {
            extract_building_code(str(building_name)),
            extract_building_code(str(building_address)),
        }
        for building_code in codes:
            if not building_code:
                continue
            lookup[room_lookup_key(building_code, str(room_name))] = int(room_id)
    return lookup


class PublicGoogleSheetsScheduleProvider:
    """
    Load occupancy slots from public Google Sheets referenced by an index page.

    The parser is tailored for HSE timetable tables where rows contain:
    weekday, time range, repeated blocks of "<group>, <room>, <building>".
    """

    def __init__(
        self,
        room_lookup: dict[str, int],
        index_url: str | None = None,
        sheet_urls: list[str] | None = None,
        timeout_seconds: int = 20,
        debug_csv_dir: str | Path | None = None,
    ) -> None:
        self.room_lookup = room_lookup
        self.index_url = index_url
        self.sheet_urls = sheet_urls or []
        self.timeout_seconds = timeout_seconds
        self.debug_csv_dir = Path(debug_csv_dir) if debug_csv_dir else None
        self.missing_room_pairs: dict[tuple[str, str], int] = {}
        self.stats: dict[str, int] = {
            "sheet_urls_total": 0,
            "rows_processed": 0,
            "rows_skipped_unknown_room": 0,
            "rows_skipped_online_or_empty": 0,
        }

    def load_slots(self) -> list[ScheduleSlot]:
        resolved_urls = self._resolve_sheet_urls()
        self.stats["sheet_urls_total"] = len(resolved_urls)
        if not resolved_urls:
            raise ValueError("Не удалось найти ссылки на Google Sheets.")

        all_slots: list[ScheduleSlot] = []
        for sheet_url in resolved_urls:
            csv_url = google_sheet_export_csv_url(sheet_url)
            logger.info("Downloading Google Sheets CSV: sheet_url=%s csv_url=%s", sheet_url, csv_url)
            csv_text = self._download_text(csv_url)
            logger.info("Downloaded Google Sheets CSV into memory: sheet_url=%s bytes=%s", sheet_url, len(csv_text))
            self._save_debug_csv(sheet_url=sheet_url, csv_text=csv_text)
            all_slots.extend(self._parse_sheet_csv(sheet_url=sheet_url, csv_text=csv_text))
        logger.info("Loaded schedule slots from Google Sheets: sheets=%s slots=%s", len(resolved_urls), len(all_slots))
        return all_slots

    def download_csv_files(self) -> list[Path]:
        if self.debug_csv_dir is None:
            raise ValueError("Укажите debug_csv_dir, чтобы сохранить CSV на диск.")

        resolved_urls = self._resolve_sheet_urls()
        if not resolved_urls:
            raise ValueError("Не удалось найти ссылки на Google Sheets.")

        saved_paths: list[Path] = []
        for sheet_url in resolved_urls:
            csv_url = google_sheet_export_csv_url(sheet_url)
            logger.info("Downloading Google Sheets CSV for debugging: sheet_url=%s csv_url=%s", sheet_url, csv_url)
            csv_text = self._download_text(csv_url)
            saved_path = self._save_debug_csv(sheet_url=sheet_url, csv_text=csv_text)
            if saved_path is not None:
                saved_paths.append(saved_path)
        logger.info("Saved Google Sheets CSV files for debugging: files=%s", len(saved_paths))
        return saved_paths

    def _resolve_sheet_urls(self) -> list[str]:
        urls = list(dict.fromkeys(self.sheet_urls))
        if self.index_url:
            index_html = self._download_text(self.index_url)
            urls.extend(extract_google_sheets_urls(index_html))

        expanded: list[str] = []
        seen: set[str] = set()
        for url in list(dict.fromkeys(urls)):
            if "docs.google.com/spreadsheets/" not in url:
                continue
            try:
                sheet_id, fallback_gid = google_sheet_identity(url)
            except ValueError:
                continue
            gids = self._discover_sheet_gids(sheet_id) or [fallback_gid]
            for gid in gids:
                normalized = compose_google_sheet_url(sheet_id, gid)
                if normalized not in seen:
                    seen.add(normalized)
                    expanded.append(normalized)
        return expanded

    def _discover_sheet_gids(self, sheet_id: str) -> list[str]:
        try:
            html = self._download_text(
                f"https://docs.google.com/spreadsheets/d/{sheet_id}/htmlview"
            )
        except OSError:
            return []

        gids = GID_RE.findall(html)
        unique_gids = sorted(set(gids), key=int)
        return unique_gids

    def _download_text(self, url: str) -> str:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "text/html,text/csv,*/*",
            },
        )
        with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
            data = resp.read()
            charset = resp.headers.get_content_charset() or "utf-8"
        return data.decode(charset, errors="replace")

    def _save_debug_csv(self, sheet_url: str, csv_text: str) -> Path | None:
        if self.debug_csv_dir is None:
            return None

        sheet_id, gid = google_sheet_identity(sheet_url)
        output_path = self.debug_csv_dir / f"{sheet_id}_{gid}.csv"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(csv_text, encoding="utf-8")
        logger.info("Saved Google Sheets CSV for debugging: path=%s", output_path)
        return output_path

    def _parse_sheet_csv(self, sheet_url: str, csv_text: str) -> list[ScheduleSlot]:
        rows = list(csv.reader(io.StringIO(csv_text)))
        if not rows:
            logger.warning("Google Sheets CSV is empty: sheet_url=%s", sheet_url)
            return []

        module_start, module_end = self._detect_module_dates(rows)
        group_columns = self._detect_group_columns(rows)
        if not group_columns:
            logger.warning("No group columns detected in Google Sheets CSV: sheet_url=%s rows=%s", sheet_url, len(rows))
            return []
        logger.info(
            "Parsing Google Sheets CSV: sheet_url=%s rows=%s module_start=%s module_end=%s group_columns=%s",
            sheet_url,
            len(rows),
            module_start,
            module_end,
            group_columns,
        )

        slots: list[ScheduleSlot] = []
        current_weekday: int | None = None

        for row_idx, row in enumerate(rows):
            day_name = (row[1].strip().lower() if len(row) > 1 else "")
            if day_name in WEEKDAY_RU:
                current_weekday = WEEKDAY_RU[day_name]

            if current_weekday is None or len(row) < 3:
                continue

            time_match = TIME_RANGE_RE.match((row[2] or "").strip())
            if not time_match:
                continue
            start_time, end_time = time_match.group(1), time_match.group(2)

            for col in group_columns:
                self.stats["rows_processed"] += 1
                subject = row[col].strip() if col < len(row) else ""
                room_raw = row[col + 1].strip() if col + 1 < len(row) else ""
                building_raw = row[col + 2].strip() if col + 2 < len(row) else ""
                group_name = self._group_name_for_column(rows, row_idx, col)

                if not subject or not room_raw or not building_raw:
                    self.stats["rows_skipped_online_or_empty"] += 1
                    continue
                if room_raw == "-" or "online" in building_raw.lower() or "online" in room_raw.lower():
                    self.stats["rows_skipped_online_or_empty"] += 1
                    continue

                room_number = self._normalize_room(room_raw)
                building_code = self._normalize_building_code(building_raw)
                if not room_number or not building_code:
                    self.stats["rows_skipped_unknown_room"] += 1
                    continue

                room_id = self.room_lookup.get(room_lookup_key(building_code, room_number))
                if room_id is None:
                    self.stats["rows_skipped_unknown_room"] += 1
                    key = (building_code, room_number)
                    self.missing_room_pairs[key] = self.missing_room_pairs.get(key, 0) + 1
                    continue

                target_dates = self._resolve_dates_for_row(
                    text=subject,
                    weekday=current_weekday,
                    module_start=module_start,
                    module_end=module_end,
                )
                for target_date in target_dates:
                    starts_at = self._compose_dt(target_date, start_time)
                    ends_at = self._compose_dt(target_date, end_time)
                    if ends_at <= starts_at:
                        ends_at += timedelta(days=1)
                    slots.append(
                        ScheduleSlot(
                            room_id=room_id,
                            starts_at=starts_at,
                            ends_at=ends_at,
                            source_external_id=f"{sheet_url}#{row_idx}:{col}",
                            comment=f"{group_name} | {subject}".strip(" |"),
                        )
                    )
        logger.info("Parsed Google Sheets CSV: sheet_url=%s slots=%s", sheet_url, len(slots))
        return slots

    @staticmethod
    def _group_name_for_column(rows: list[list[str]], row_idx: int, col_idx: int) -> str:
        for probe in range(max(0, row_idx - 8), row_idx):
            row = rows[probe]
            if col_idx < len(row):
                cell = row[col_idx].strip()
                if GROUP_RE.match(cell):
                    return cell
        return ""

    @staticmethod
    def _normalize_building_code(raw: str) -> str:
        return extract_building_code(raw)

    @staticmethod
    def _normalize_room(raw: str) -> str:
        text = raw.strip()
        if not text:
            return ""

        upper = text.upper()
        if "ONLINE" in upper:
            return ""

        # In values like "20721.04 в 303" keep primary room before date note.
        date_match = DATE_IN_TEXT_RE.search(text)
        if date_match:
            text = text[: date_match.start()]

        compact = (
            text.replace(",", " ")
            .replace(";", " ")
            .replace("/", " ")
            .replace("\n", " ")
        )
        match = re.search(r"(?<!\d)(\d{2,4})(?!\d)", compact)
        if match:
            return match.group(1)
        return ""

    @staticmethod
    def _detect_group_columns(rows: list[list[str]]) -> list[int]:
        group_cols: list[int] = []
        for row in rows[:20]:
            for idx, cell in enumerate(row):
                if GROUP_RE.match(cell.strip()):
                    group_cols.append(idx)
        return sorted(set(group_cols))

    @staticmethod
    def _detect_module_dates(rows: list[list[str]]) -> tuple[date, date]:
        current_year = datetime.now(tz=MOSCOW_TZ).year
        for row in rows[:10]:
            text = " ".join(c for c in row if c).strip()
            match = MODULE_RANGE_RE.search(text)
            if not match:
                continue
            start = datetime.strptime(f"{match.group(1)}.{current_year}", "%d.%m.%Y").date()
            end = datetime.strptime(f"{match.group(2)}.{current_year}", "%d.%m.%Y").date()
            if end < start:
                end = end.replace(year=end.year + 1)
            return start, end

        # fallback: nearest 16 weeks from today
        start = datetime.now(tz=MOSCOW_TZ).date()
        return start, start + timedelta(days=7 * 16)

    @staticmethod
    def _resolve_dates_for_row(
        text: str,
        weekday: int,
        module_start: date,
        module_end: date,
    ) -> list[date]:
        explicit: list[date] = []
        year = module_start.year
        for token in DATE_IN_TEXT_RE.findall(text):
            try:
                d = datetime.strptime(f"{token}.{year}", "%d.%m.%Y").date()
            except ValueError:
                continue
            if module_start <= d <= module_end:
                explicit.append(d)
        if explicit:
            return sorted(set(explicit))

        dates: list[date] = []
        cursor = module_start
        while cursor <= module_end:
            if cursor.weekday() == weekday:
                dates.append(cursor)
            cursor += timedelta(days=1)
        return dates

    @staticmethod
    def _compose_dt(d: date, hhmm: str) -> datetime:
        hour, minute = map(int, hhmm.split(":"))
        return datetime(d.year, d.month, d.day, hour, minute, tzinfo=MOSCOW_TZ)

    def top_missing_room_pairs(self, limit: int = 100) -> list[tuple[str, str, int]]:
        ranked = sorted(self.missing_room_pairs.items(), key=lambda item: item[1], reverse=True)
        return [(building, room, count) for (building, room), count in ranked[:limit]]
