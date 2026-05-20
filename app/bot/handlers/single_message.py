"""Helpers for the single-message UX: one bot message per chat is edited in place."""
from contextlib import suppress

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, Message


MAIN_MESSAGE_KEY = "main_message_id"


async def edit_or_create_main(
    bot: Bot,
    chat_id: int,
    state: FSMContext,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> int:
    """Edit the chat's main message; if missing or stale, send a fresh one."""
    data = await state.get_data()
    msg_id = data.get(MAIN_MESSAGE_KEY)
    if msg_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=text,
                reply_markup=reply_markup,
            )
            return msg_id
        except TelegramBadRequest:
            pass
    msg = await bot.send_message(chat_id, text, reply_markup=reply_markup)
    await state.update_data({MAIN_MESSAGE_KEY: msg.message_id})
    return msg.message_id


async def clear_state_keep_main(state: FSMContext) -> None:
    """Reset FSM state and data but keep the main_message_id pointer."""
    data = await state.get_data()
    main_id = data.get(MAIN_MESSAGE_KEY)
    await state.clear()
    if main_id is not None:
        await state.update_data({MAIN_MESSAGE_KEY: main_id})


async def remember_main_from_callback(state: FSMContext, message_id: int) -> None:
    """Persist the callback's message id as the main message id."""
    await state.update_data({MAIN_MESSAGE_KEY: message_id})


async def delete_user_message(message: Message) -> None:
    """Best-effort delete of an incoming user message."""
    with suppress(TelegramBadRequest):
        await message.delete()
