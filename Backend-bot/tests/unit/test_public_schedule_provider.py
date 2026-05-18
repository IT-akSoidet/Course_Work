from datetime import datetime

from app.core.config import MOSCOW_TZ
from app.integrations.schedule_importer import (
    PublicGoogleSheetsScheduleProvider,
    extract_building_code,
    extract_google_sheets_urls,
    google_sheet_export_csv_url,
    room_lookup_key,
)


def test_extract_google_sheet_urls_from_encoded_text() -> None:
    encoded = (
        "https%3A%2F%2Fdocs.google.com%2Fspreadsheets%2Fd%2Fabc123XYZ%2Fedit%3Fgid%3D42"
    )
    urls = extract_google_sheets_urls(encoded)
    assert "https://docs.google.com/spreadsheets/d/abc123XYZ/edit?gid=42" in urls


def test_google_sheet_export_csv_url_with_gid() -> None:
    url = "https://docs.google.com/spreadsheets/d/testSheetId/edit?gid=2047065589#gid=2047065589"
    assert (
        google_sheet_export_csv_url(url)
        == "https://docs.google.com/spreadsheets/d/testSheetId/export?format=csv&gid=2047065589"
    )


def test_public_google_sheets_provider_parses_basic_rows() -> None:
    csv_text = "\n".join(
        [
            ',,,,"БАКАЛАВРИАТ - 3 курс, 4 модуль (01.04. - 08.04.)"',
            ",День,Время,,I ПОТОК",
            ",,,,23КНТ-1,Ауд.,Корпус",
            ",понедельник,09:30-10:50,,Теория организации - лекция - Михейкин В.Б.,226,Л",
        ]
    )
    provider = PublicGoogleSheetsScheduleProvider(
        room_lookup={room_lookup_key("Л", "226"): 700226},
        sheet_urls=["https://docs.google.com/spreadsheets/d/testSheetId/edit?gid=0"],
    )
    slots = provider._parse_sheet_csv(
        sheet_url="https://docs.google.com/spreadsheets/d/testSheetId/edit?gid=0",
        csv_text=csv_text,
    )
    assert len(slots) > 0
    assert slots[0].room_id == 700226
    assert slots[0].starts_at.tzinfo == MOSCOW_TZ
    assert slots[0].starts_at.time() == datetime(2026, 1, 1, 9, 30).time()


def test_public_google_sheets_provider_discovers_all_sheet_tabs() -> None:
    provider = PublicGoogleSheetsScheduleProvider(
        room_lookup={},
        sheet_urls=["https://docs.google.com/spreadsheets/d/testSheetId/edit?gid=2047065589"],
    )

    def fake_download(url: str) -> str:
        if url.endswith("/htmlview"):
            return (
                '<a href="/spreadsheets/d/testSheetId/edit?gid=101#gid=101">1 курс</a>'
                '<a href="/spreadsheets/d/testSheetId/edit?gid=202#gid=202">2 курс</a>'
                '<a href="/spreadsheets/d/testSheetId/edit?gid=303#gid=303">3 курс</a>'
            )
        raise AssertionError(f"Unexpected URL: {url}")

    provider._download_text = fake_download  # type: ignore[assignment]
    resolved = provider._resolve_sheet_urls()
    assert resolved == [
        "https://docs.google.com/spreadsheets/d/testSheetId/edit?gid=101#gid=101",
        "https://docs.google.com/spreadsheets/d/testSheetId/edit?gid=202#gid=202",
        "https://docs.google.com/spreadsheets/d/testSheetId/edit?gid=303#gid=303",
    ]


def test_building_and_room_normalization_for_hse_format() -> None:
    assert extract_building_code("БП") == "Б"
    assert extract_building_code("корпус на ул. Б.Печёрской, 25/12") == "Б"
    assert extract_building_code("корпус на ул. Костина, 2Б ") == "К"
    assert extract_building_code("корпус на ул. Львовской, 1В") == "Л"
    assert extract_building_code("корпус на ул. Родионова, 136") == "Р"
    assert extract_building_code("корпус на Сормовском ш., 30") == "С"
    assert PublicGoogleSheetsScheduleProvider._normalize_room("20721.04 в 303") == "207"


def test_public_google_sheets_provider_saves_debug_csv(tmp_path) -> None:
    provider = PublicGoogleSheetsScheduleProvider(
        room_lookup={},
        sheet_urls=["https://docs.google.com/spreadsheets/d/testSheetId/edit?gid=42"],
        debug_csv_dir=tmp_path,
    )

    saved_path = provider._save_debug_csv(
        sheet_url="https://docs.google.com/spreadsheets/d/testSheetId/edit?gid=42",
        csv_text="23КНТ-1,Ауд.,Корпус\n",
    )

    assert saved_path == tmp_path / "testSheetId_42.csv"
    assert saved_path.read_text(encoding="utf-8") == "23КНТ-1,Ауд.,Корпус\n"


def test_public_google_sheets_provider_downloads_debug_csv_files(tmp_path) -> None:
    provider = PublicGoogleSheetsScheduleProvider(
        room_lookup={},
        sheet_urls=["https://docs.google.com/spreadsheets/d/testSheetId/edit?gid=42"],
        debug_csv_dir=tmp_path,
    )

    provider._discover_sheet_gids = lambda sheet_id: ["42"]  # type: ignore[method-assign]
    provider._download_text = lambda url: "23КНТ-1,Ауд.,Корпус\n"  # type: ignore[method-assign]

    saved_paths = provider.download_csv_files()

    assert saved_paths == [tmp_path / "testSheetId_42.csv"]
    assert saved_paths[0].read_text(encoding="utf-8") == "23КНТ-1,Ауд.,Корпус\n"
