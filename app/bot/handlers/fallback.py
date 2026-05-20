"""Catch-all router: delete any stray user message that no other handler claimed."""
from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot.handlers.single_message import delete_user_message

router = Router()


@router.message()
async def fallback_message(message: Message, state: FSMContext) -> None:
    if await state.get_state() is not None:
        return
    await delete_user_message(message)
