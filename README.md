# Telegram-бот бронирования аудиторий НИУ ВШЭ — Нижний Новгород

Бот для студентов и преподавателей кампуса, который помогает найти свободную
аудиторию и оформить бронь в несколько нажатий. Весь интерфейс работает через
**одно постоянное сообщение** в чате: бот его редактирует на каждом шаге, а
пользовательские команды и ввод автоматически удаляются.

## Возможности

- 📝 Бронирование по шагам: дата → аудитория → начало → конец → цель.
- 📋 Просмотр своих активных броней с кольцевой пагинацией ◀️/▶️.
- ❌ Отмена своей брони из карточки или командой `/cancel <id>`.
- 🕐 Расчёт свободных окон с учётом существующих броней и расписания пар.
- 🛡 Защита от двойного бронирования через транзакцию + PostgreSQL advisory lock.
- 📥 Импорт расписания занятости из CSV (доступно администраторам).

## Стек

- Python 3.11+
- `aiogram` 3.x — Telegram-бот
- `FastAPI` — health-эндпоинт сервиса
- `SQLAlchemy` 2.x (async) + `Alembic` — модели и миграции
- PostgreSQL 16 — основная БД
- Docker Compose — локальная инфраструктура

## Структура проекта

```
app/
├── bot/
│   ├── handlers/
│   │   ├── start.py          # /start, /help, навигация
│   │   ├── booking.py        # /book, /my_bookings, /cancel, FSM
│   │   ├── admin.py          # /import_schedule
│   │   ├── fallback.py       # удаление "мусорного" текста
│   │   └── single_message.py # утилиты единого сообщения
│   ├── ui.py                 # inline-клавиатуры и форматирование
│   ├── parsers.py            # парсинг даты/времени
│   └── main.py               # точка входа бота
├── api/                      # FastAPI (health)
├── services/
│   ├── booking_service.py    # создание/отмена брони + advisory lock
│   └── free_slots.py         # расчёт свободных окон
├── db/
│   ├── models.py             # ORM-модели
│   ├── repositories/         # доступ к данным
│   └── session.py
├── integrations/
│   └── schedule_importer.py  # импорт CSV
└── core/                     # конфиг и логирование
alembic/                      # миграции
data/                         # примеры CSV-расписания
tests/                        # unit-тесты
```

## Настройка окружения

1. Скопируйте шаблон переменных окружения:
   ```bash
   cp .env.example .env
   ```
2. Заполните `.env`:
   - `BOT_TOKEN` — токен из [@BotFather](https://t.me/BotFather)
   - `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` — параметры контейнера Postgres
   - `DATABASE_URL` — строка подключения SQLAlchemy (по умолчанию совпадает с docker-compose)
   - `ADMIN_TELEGRAM_IDS` — список Telegram-id администраторов через запятую
   - `APP_ENV` — `dev` / `prod`

## Локальный запуск

```bash
# 1. Поднять PostgreSQL
docker compose up -d

# 2. Установить зависимости (рекомендуется в venv)
python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Применить миграции
python -m alembic upgrade head

# 4. (опционально) загрузить демо-расписание
#    через бот-команду /import_schedule с прикреплённым data/sample_schedule.csv

# 5. Запустить бота
python -m app.bot.main

# 6. (опционально) Запустить API health
python -m uvicorn app.api.main:app --reload
```

## Команды бота

| Команда | Описание |
| --- | --- |
| `/start` | Главное меню с кнопками «Новая бронь», «Мои брони», «Помощь» |
| `/book` | Запуск пошагового создания брони |
| `/my_bookings` | Список ваших активных броней с пагинацией |
| `/cancel <id>` | Отмена брони по её номеру |
| `/help` | Справка по командам |
| `/import_schedule` | (админ) Импорт CSV-расписания, файл прикладывается к сообщению |

Вся навигация ведётся inline-кнопками внутри **одного** сообщения бота;
любые ваши сообщения с командами или вводом времени/цели удаляются автоматически.

## Формат CSV для импорта расписания

Колонки (порядок строгий):

```
date,start_time,end_time,subject,subject_type,teacher,group,classroom,building
```

Пример строки:

```
2026-05-25,09:30,11:00,Математический анализ,лекция,Иванов И.И.,25КНТ-1,101,БП
```

Строки с `building=online` или `classroom=online` пропускаются.
Пример файла: [`data/sample_schedule.csv`](data/sample_schedule.csv).

## Логика бронирования

1. Пользователь выбирает дату → бот показывает аудитории со свободными окнами.
2. После выбора аудитории показываются её свободные интервалы (с учётом
   существующих броней и пар по расписанию).
3. Пользователь вводит время начала и окончания — оба значения валидируются
   по выбранному окну, нельзя выйти за его границы.
4. На запись цели создаётся бронь:
   - открывается транзакция;
   - берётся PostgreSQL advisory lock на `room_id`;
   - повторно проверяются конфликты с бронями и расписанием;
   - если конфликтов нет — бронь сохраняется, иначе пользователь получает
     понятное сообщение об ошибке.

## Тесты

```bash
python -m pytest -q
```

Покрывают парсеры, расчёт свободных окон и импортёр расписания.

## Полезные материалы

- [`docs/mvp_scope.md`](docs/mvp_scope.md)
- [`docs/presentation_outline.md`](docs/presentation_outline.md)
- [`docs/explanatory_note_outline.md`](docs/explanatory_note_outline.md)
- [`docs/demo_script.md`](docs/demo_script.md)
