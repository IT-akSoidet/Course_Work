from pathlib import Path

import pytest

from app.integrations.schedule_importer import CsvScheduleProvider


def test_csv_provider_loads_slots() -> None:
    provider = CsvScheduleProvider(Path("data/sample_schedule.csv"))
    slots = provider.load_slots()
    assert len(slots) == 3
    assert slots[0].room_id == 10101


def test_csv_provider_requires_columns(tmp_path: Path) -> None:
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text("foo,bar\n1,2\n", encoding="utf-8")
    provider = CsvScheduleProvider(bad_csv)
    with pytest.raises(ValueError):
        provider.load_slots()
