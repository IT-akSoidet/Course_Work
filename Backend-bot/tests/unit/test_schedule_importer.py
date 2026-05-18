from pathlib import Path

import pytest

from app.integrations.schedule_importer import CsvScheduleProvider


def test_csv_provider_loads_slots() -> None:
    provider = CsvScheduleProvider(file_path=Path("data/sample_schedule.csv"))
    slots = provider.load_slots()
    assert len(slots) == 3
    assert slots[0].room_id == 10101
    assert slots[0].starts_at.tzinfo is not None


def test_csv_provider_from_bytes() -> None:
    content = (
        b"room_id,starts_at,ends_at,external_id,comment\n"
        b"10101,2026-06-01 09:00,2026-06-01 10:30,test-1,Demo\n"
    )
    provider = CsvScheduleProvider(content=content)
    slots = provider.load_slots()
    assert len(slots) == 1
    assert slots[0].room_id == 10101
    assert slots[0].comment == "Demo"


def test_csv_provider_requires_columns(tmp_path: Path) -> None:
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text("foo,bar\n1,2\n", encoding="utf-8")
    provider = CsvScheduleProvider(file_path=bad_csv)
    with pytest.raises(ValueError):
        provider.load_slots()


def test_csv_provider_no_source_raises() -> None:
    provider = CsvScheduleProvider()
    with pytest.raises(ValueError):
        provider.load_slots()
