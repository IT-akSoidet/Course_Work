# Telegram-бот бронирования аудиторий НИУ ВШЭ - Нижний Новгород

Сервис позволяет студентам, преподавателям и администраторам работать с бронированием аудиторий через Telegram.

## Что умеет проект
- Поиск свободных аудиторий по времени и вместимости.
- Создание и отмена бронирования.
- Модерация конфликтных заявок администратором.
- Импорт занятости из CSV (учет расписания пар).
- Защита от двойного бронирования через транзакции и блокировки.

## Стек технологий
- Python 3.11+
- `aiogram` (Telegram-бот)
- `FastAPI` (API-слой)
- `SQLAlchemy` + `Alembic` (модели и миграции)
- PostgreSQL (основная БД)
- Redis (опционально: кэш/временные данные)
- Docker Compose (локальная инфраструктура)

## Структура проекта
- `app/bot/` - Telegram-бот и хендлеры команд.
- `app/api/` - API и роуты FastAPI.
- `app/services/` - бизнес-логика бронирования/модерации.
- `app/db/` - модели, сессии БД, репозитории.
- `app/integrations/` - интеграции (например, импорт расписания).
- `alembic/` - миграции БД.
- `data/` - тестовые/демо-данные (CSV расписания).
- `docs/` - материалы для курсовой и защиты.

## Требования
- Python 3.11 или выше
- Docker Desktop (или Docker Engine + Compose)
- Telegram-бот токен от [@BotFather](https://t.me/BotFather)

## Настройка окружения
1. Создайте `.env` на основе шаблона:
   - Windows PowerShell: `Copy-Item .env.example .env`
2. Заполните переменные в `.env`:
   - `BOT_TOKEN`
   - `POSTGRES_DB`
   - `POSTGRES_USER`
   - `POSTGRES_PASSWORD`
   - `DATABASE_URL`
   - `REDIS_URL`
   - `ADMIN_TELEGRAM_IDS`
   - `APP_ENV`
   - `SCHEDULE_INDEX_URL` (опционально: ссылка на страницу со списком Google Sheets)
   - `SCHEDULE_SHEET_URLS` (опционально: список Google Sheets через запятую)
   - `SCHEDULE_SYNC_INTERVAL_HOURS` (опционально: автосинхронизация, 0 = выключено)

## Запуск проекта (локально)
1. Поднимите инфраструктуру:
   - `docker compose up -d`
2. Установите зависимости Python:
   - `python -m pip install -r requirements.txt`
3. Примените миграции:
   - `python -m alembic upgrade head`
4. Запустите API:
   - `python -m uvicorn app.api.main:app --reload`
5. В отдельном терминале запустите Telegram-бота:
   - `python -m app.bot.main`

## Использование бота
### Основные команды
- `/start` - запуск бота, авторегистрация пользователя и главное меню.
- `/rooms` - пошаговый поиск свободных аудиторий (также поддерживается быстрый формат: `/rooms <YYYY-MM-DD HH:MM>;<YYYY-MM-DD HH:MM>;<min_capacity>`).
- `/book` - пошаговое создание брони (также поддерживается быстрый формат: `/book <room_id>;<YYYY-MM-DD HH:MM>;<YYYY-MM-DD HH:MM>;<purpose>`).
- `/my_bookings` - список активных бронирований.
- `/cancel <booking_id>` - отмена своей брони.
- `/menu` и `/help` - показать меню и подсказки.

### Команды администратора
- `/admin_queue` - очередь заявок на модерацию (`pending`).
- `/approve <booking_id>` - подтвердить заявку.
- `/reject <booking_id>` - отклонить заявку.
- `/import_schedule <path_to_csv>` - импорт расписания занятости из CSV.
- `/sync_schedule [index_url или google_sheet_url ...]` - синхронизация занятости из публичных Google Sheets.
- `/sync_schedule_autofill [index_url или google_sheet_url ...]` - добавить недостающие аудитории в `rooms` и сразу выполнить синхронизацию.

Бот также поддерживает интерфейс кнопками: создание брони, поиск аудиторий, просмотр и отмена броней, модерация заявок администратором в один клик.

## Формат CSV для импорта расписания
Файл должен содержать заголовки:
- `room_id`
- `starts_at`
- `ends_at`
- `external_id` (опционально)
- `comment` (опционально)

Пример: `data/sample_schedule.csv`.

## Импорт из публичных таблиц
- Можно запускать вручную командой `/sync_schedule`.
- Если задан `SCHEDULE_INDEX_URL`, бот пытается извлечь из этой страницы ссылки на `docs.google.com/spreadsheets/...`.
- Также можно задать прямые ссылки через `SCHEDULE_SHEET_URLS` (через запятую).
- Для каждой Google Sheets ссылки используется экспорт CSV (`/export?format=csv&gid=...`), после чего строки нормализуются в интервалы занятости аудиторий.

## Логика бронирования (кратко)
1. Проверяется валидность интервала (`starts_at < ends_at`, не в прошлом).
2. Блокируется аудитория в транзакции (`FOR UPDATE` + advisory lock).
3. Проверяются пересечения:
   - с активными бронированиями;
   - с занятостью из расписания.
4. Если конфликтов нет - заявка `approved`.
5. Если есть конфликт - заявка уходит в `pending` для решения админом.

## Проверка работоспособности
- Запуск тестов:
  - `python -m pytest -q`
- Проверка API health:
  - `GET http://127.0.0.1:8000/health`

## Полезные материалы
- `docs/mvp_scope.md`
- `docs/presentation_outline.md`
- `docs/explanatory_note_outline.md`
- `docs/demo_script.md`
