from pathlib import Path

import pytest

from app.integrations.schedule_importer import CsvScheduleProvider, REQUIRED_COLUMNS


def test_csv_provider_from_bytes() -> None:
    content = (
        "date,start_time,end_time,subject,subject_type,teacher,group,classroom,building\n"
        "2026-05-25,09:30,11:00,Math,лекция,Иванов,25КНТ-1,101,БП\n"
    ).encode("utf-8")
    provider = CsvScheduleProvider(content=content)
    rows = provider.read_rows()
    assert len(rows) == 1
    assert rows[0]["classroom"] == "101"
    assert rows[0]["building"] == "БП"


def test_csv_provider_requires_columns(tmp_path: Path) -> None:
    bad = tmp_path / "bad.csv"
    bad.write_text("foo,bar\n1,2\n", encoding="utf-8")
    provider = CsvScheduleProvider(file_path=bad)
    with pytest.raises(ValueError):
        provider.read_rows()


def test_csv_provider_no_source_raises() -> None:
    provider = CsvScheduleProvider()
    with pytest.raises(ValueError):
        provider.read_rows()


def test_required_columns_subset() -> None:
    expected = {"date", "start_time", "end_time", "subject", "teacher", "classroom", "building"}
    assert REQUIRED_COLUMNS == expected
