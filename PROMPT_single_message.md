# Задача: единое сообщение бота — полная пагинация

## Концепция

Бот работает через ОДНО постоянное сообщение на весь сеанс.
Это сообщение отправляется при /start и больше никогда не создаётся заново.
Всё что происходит дальше — только `edit_message_text` этого сообщения.

Сообщения пользователя (текстовый ввод времени, цели) — сразу удалять через `bot.delete_message()`.

---

## Реализация

### /start — отправить единственное сообщение

```python
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    # Удалить команду /start пользователя
    await message.delete()
    # Отправить ОДНО сообщение — оно будет жить всю сессию
    sent = await message.answer(
        text=main_menu_text(),
        reply_markup=main_menu_kb()
    )
    # Сохранить id этого сообщения глобально для пользователя
    await state.update_data(main_message_id=sent.message_id)
```

### Главное меню (начальное состояние сообщения)

```
👋 Привет! Я помогу найти свободную аудиторию ВШЭ НН.

Выберите действие:
[📝 Новая бронь]
[📋 Мои брони]  [ℹ️ Помощь]
```

### Все кнопки главного меню — редактируют это же сообщение

```python
@router.callback_query(F.data == "new_booking")
async def cb_new_booking(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text(
        text=choose_date_text(),
        reply_markup=choose_date_kb()
    )
    await state.set_state(BookingFlow.choosing_date)
```

### Текстовый ввод пользователя — удалять сразу

```python
@router.message(BookingFlow.entering_start)
async def enter_start_time(message: Message, state: FSMContext, bot: Bot):
    # Удалить сообщение пользователя
    await bot.delete_message(message.chat.id, message.message_id)

    # Валидация
    time = parse_time(message.text)
    if not time:
        data = await state.get_data()
        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=data['main_message_id'],
            text="❌ Неверный формат. Введите время в формате ЧЧ:ММ\n\n" + enter_start_text(data),
            reply_markup=back_cancel_kb()
        )
        return

    await state.update_data(start_time=time)
    data = await state.get_data()
    await bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=data['main_message_id'],
        text=enter_end_text(data),
        reply_markup=back_cancel_kb()
    )
    await state.set_state(BookingFlow.entering_end)
```

### Кнопки главного меню — ReplyKeyboard убрать полностью

Убрать `ReplyKeyboardMarkup` из /start и из всех хендлеров.
Навигация только через InlineKeyboard внутри одного сообщения.
`/book`, `/my_bookings` как текстовые команды оставить для совместимости,
но они тоже должны редактировать главное сообщение, а не создавать новое.

Команды /book, /my_bookings, /help:
```python
@router.message(Command("book"))
async def cmd_book(message: Message, state: FSMContext, bot: Bot):
    await message.delete()  # удалить команду пользователя
    data = await state.get_data()
    main_msg_id = data.get('main_message_id')
    if main_msg_id:
        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=main_msg_id,
            text=choose_date_text(),
            reply_markup=choose_date_kb()
        )
    else:
        # Если вдруг main_message_id потерялся — создать заново
        sent = await message.answer(choose_date_text(), reply_markup=choose_date_kb())
        await state.update_data(main_message_id=sent.message_id)
    await state.set_state(BookingFlow.choosing_date)
```

---

## Полный флоу /book в одном сообщении

```
[Шаг 1] edit → выбор даты
[Шаг 2] edit → сводка свободных аудиторий + выбор кнопкой
[Шаг 3] edit → введите время начала (пользователь пишет → его сообщение удаляется → edit)
[Шаг 4] edit → введите время окончания (то же самое)
[Шаг 5] edit → введите цель (то же самое)
[Шаг 6] edit → ✅ Бронирование создано! + кнопки [❌ Отменить] [🏠 Главное меню]
```

Кнопка «🏠 Главное меню» → edit → главное меню.
Кнопка «❌ Отмена» на любом шаге → edit → главное меню.
Кнопка «🔙 Назад» → edit → предыдущий шаг.

---

## Флоу /my_bookings в одном сообщении

```
[edit → бронь 1 из N] → кнопка ◀️/▶️ → [edit → бронь 2 из N]
                      → кнопка ❌ Отменить → [edit → подтверждение]
                                           → кнопка ✅ Да → [edit → отменено]
                      → кнопка 🏠 → [edit → главное меню]
```

---

## Граничные случаи

- Если пользователь пишет произвольный текст когда нет активного FSM-состояния — удалить его сообщение, ничего не делать (или edit главного сообщения с подсказкой)
- Если `main_message_id` потерялся (бот перезапустился) — при следующем взаимодействии создать новое главное сообщение и сохранить его id
- `callback.answer()` вызывать в начале каждого callback-хендлера чтобы убрать индикатор загрузки

---

## Что НЕ трогать

- BookingService, advisory lock — не трогать
- get_free_windows — не трогать
- /import_schedule — не трогать
- /cancel <id> (текстовая команда) — оставить, но тоже удалять команду пользователя и отвечать через edit
- Модели и миграции — не трогать
