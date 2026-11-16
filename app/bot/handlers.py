from aiogram import Dispatcher, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    BotCommand,
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.security.access import AdminGate

LABELS = {
    "start": "Меню",
    "help": "Инструкция",
    "status": "Состояние",
    "settings": "Настройки поиска",
    "add": "Добавить заказ",
    "jobs": "Заказы",
    "analyze": "Анализ ТЗ",
    "reply": "Черновик отклика",
    "site": "Сайт в ZIP",
    "projects": "Мои сайты",
    "feeds": "Источники",
    "budget": "Лимиты ИИ",
}
HELP = """VibeWorker AI · личный кабинет
1. Введите /add Заголовок и добавьте описание со следующей строки.
2. Откройте /jobs, затем /jobs ID для просмотра ТЗ.
3. Используйте /analyze ID для оценки, /reply ID для черновика или /site ID для ZIP.
4. Скачайте сохранённый сайт командой /projects ID.

Для поиска добавьте публичную ленту через /feeds. Фильтры и уведомления доступны в /settings.
Расход ИИ — /budget, состояние worker — /status. Результаты получает только владелец в этом чате."""


def menu():
    buttons = [
        InlineKeyboardButton(text=label, callback_data=f"menu:{cmd}")
        for cmd, label in LABELS.items()
        if cmd != "start"
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    )


async def dispatch(message, name, args, service):
    if name == "start":
        await message.answer("VibeWorker AI\nВыберите действие.", reply_markup=menu())
        return
    if name == "help":
        result = HELP
    elif name in ("status", "budget"):
        result = await getattr(service, name)()
    elif name in ("settings", "feeds", "add", "jobs", "projects"):
        result = await getattr(service, name)(args)
    else:
        result = await service.generate(name, args)
    if isinstance(result, tuple):
        key, payload = result
        await message.answer_document(
            BufferedInputFile(payload, filename=f"site-{key}.zip"),
            caption=f"Проект #{key}. Копия сохранена в /projects.",
        )
    else:
        # Telegram measures entities in UTF-16. 2000 Unicode scalars always fit.
        markup = None
        if name == "jobs" and args:
            markup = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=LABELS[action], callback_data=f"job:{action}:{args}"
                        )
                        for action in ("analyze", "reply", "site")
                    ]
                ]
            )
        for offset in range(0, len(result), 2000):
            await message.answer(
                result[offset : offset + 2000],
                reply_markup=markup if offset + 2000 >= len(result) else None,
            )


def dispatcher(admin_id):
    dp, router = Dispatcher(), Router()
    gate = AdminGate(admin_id)
    router.message.outer_middleware(gate)
    router.callback_query.outer_middleware(gate)

    @router.message(Command(*LABELS))
    async def on_command(message: Message, command: CommandObject, service):
        await dispatch(message, command.command, (command.args or "").strip(), service)

    @router.callback_query(F.data.in_({f"menu:{k}" for k in LABELS}))
    async def on_button(query: CallbackQuery, service):
        await query.answer()
        await dispatch(query.message, query.data.removeprefix("menu:"), "", service)

    @router.callback_query(F.data.regexp(r"^job:(analyze|reply|site):[0-9]{1,10}$"))
    async def on_job_action(query: CallbackQuery, service):
        await query.answer()
        _, action, key = query.data.split(":")
        await dispatch(query.message, action, key, service)

    dp.include_router(router)
    return dp


def telegram_commands():
    return [BotCommand(command=k, description=v) for k, v in LABELS.items()]
