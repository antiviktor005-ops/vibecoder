import logging
import time
from collections import deque

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message

from app.core.errors import InputError


class AdminGate(BaseMiddleware):
    def __init__(self, admin_id):
        self.admin_id = admin_id
        self.recent = deque()

    async def __call__(self, handler, event, data):
        message = event.message if isinstance(event, CallbackQuery) else event
        if (
            not isinstance(message, Message)
            or not event.from_user
            or event.from_user.id != self.admin_id
            or message.chat.type != "private"
            or message.chat.id != self.admin_id
        ):
            if isinstance(event, CallbackQuery):
                await event.answer()
            return
        now = time.monotonic()
        while self.recent and self.recent[0] <= now - 60:
            self.recent.popleft()
        if len(self.recent) >= 30:
            if isinstance(event, CallbackQuery):
                await event.answer("Лимит 30 действий в минуту.")
            return
        self.recent.append(now)
        try:
            return await handler(event, data)
        except InputError as exc:
            await message.answer(str(exc))
        except Exception as exc:
            logging.getLogger(__name__).error("Ошибка команды (%s)", type(exc).__name__)
            await message.answer("Операция прервана. Проверьте /status и попробуйте ещё раз.")
