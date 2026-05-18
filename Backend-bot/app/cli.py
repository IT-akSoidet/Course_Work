"""CLI для управления сервисом бронирования ВШЭ.

Использование:
  python -m app.cli import-schedule data/schedule.csv
  python -m app.cli import-schedule data/schedule.csv --no-replace
"""

import argparse
import asyncio
import sys
from pathlib import Path


async def _import_schedule(file_path: str, replace: bool) -> None:
    from app.db.session import SessionLocal
    from app.integrations.hse_csv_importer import import_hse_csv

    path = Path(file_path)
    if not path.exists():
        print(f"Ошибка: файл не найден: {path}", file=sys.stderr)
        sys.exit(1)

    print(f"Импорт расписания из {path}...")
    async with SessionLocal() as session:
        stats = await import_hse_csv(session, path, replace=replace)

    print(
        f"Готово:\n"
        f"  Импортировано слотов: {stats['imported']}\n"
        f"  Пропущено (онлайн):   {stats['skipped_online']}\n"
        f"  Пропущено (неизвест): {stats['skipped_unknown']}\n"
        f"  Ошибок в строках:     {stats['errors']}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Сервис бронирования ВШЭ — CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    import_parser = subparsers.add_parser(
        "import-schedule",
        help="Импортировать расписание из CSV файла ВШЭ",
    )
    import_parser.add_argument("file", help="Путь к CSV файлу расписания")
    import_parser.add_argument(
        "--no-replace",
        dest="replace",
        action="store_false",
        default=True,
        help="Добавить к существующим записям вместо замены",
    )

    args = parser.parse_args()

    if args.command == "import-schedule":
        asyncio.run(_import_schedule(args.file, args.replace))


if __name__ == "__main__":
    main()
