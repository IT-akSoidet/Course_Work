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
- `/start` - приветствие и справка.
- `/rooms <YYYY-MM-DD HH:MM>;<YYYY-MM-DD HH:MM>;<min_capacity>` - поиск свободных аудиторий.
- `/book <room_id>;<YYYY-MM-DD HH:MM>;<YYYY-MM-DD HH:MM>;<purpose>` - создать бронь.
- `/my_bookings` - список активных бронирований.
- `/cancel <booking_id>` - отмена своей брони.

### Команды администратора
- `/admin_queue` - очередь заявок на модерацию (`pending`).
- `/approve <booking_id>` - подтвердить заявку.
- `/reject <booking_id>` - отклонить заявку.
- `/import_schedule <path_to_csv>` - импорт расписания занятости из CSV.

## Формат CSV для импорта расписания
Файл должен содержать заголовки:
- `room_id`
- `starts_at`
- `ends_at`
- `external_id` (опционально)
- `comment` (опционально)

Пример: `data/sample_schedule.csv`.

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
