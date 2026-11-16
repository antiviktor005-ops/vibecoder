from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.types import Update

from app.bot.handlers import LABELS, dispatcher


@pytest.fixture
async def telegram(cfg, service):
    session = AiohttpSession()
    session.make_request = AsyncMock(return_value=True)
    bot = Bot(cfg.bot_token.get_secret_value(), session=session)
    dp = dispatcher(cfg.admin_telegram_id)

    async def send(command, *, user=None, group=False, button=False):
        uid = cfg.admin_telegram_id if user is None else user
        sender = {"id": uid, "first_name": "Тест", "is_bot": False}
        message = {
            "message_id": 1,
            "date": 1720000000,
            "from": sender,
            "text": command,
            "chat": {"id": -1000 if group else uid, "type": "group" if group else "private"},
        }
        payload = {"message": message}
        if button:
            payload = {
                "callback_query": {
                    "id": "42",
                    "from": sender,
                    "message": message,
                    "chat_instance": "1",
                    "data": command if command.startswith("job:") else "menu:" + command,
                }
            }
        update = Update.model_validate({"update_id": 1, **payload}, context={"bot": bot})
        session.make_request.reset_mock()
        await dp.feed_update(bot, update, service=service)
        return [call.args[1] for call in session.make_request.await_args_list]

    yield send
    await bot.session.close()


@pytest.mark.parametrize("name", list(LABELS))
async def test_every_command(telegram, name):
    calls = await telegram("/" + name)
    assert calls[-1].__api_method__ == "sendMessage"
    assert calls[-1].text and "Операция прервана" not in calls[-1].text


@pytest.mark.parametrize("group,uid", [(True, 9876), (False, 123)])
async def test_access_every_route(telegram, group, uid):
    for cmd in LABELS:
        assert await telegram("/" + cmd, user=uid, group=group) == []
        calls = await telegram(cmd, user=uid, group=group, button=True)
        assert [c.__api_method__ for c in calls] == ["answerCallbackQuery"]


async def test_menu_and_invalid_job(telegram):
    assert (await telegram("/start"))[-1].reply_markup.inline_keyboard
    assert (await telegram("jobs", button=True))[-1].text.startswith("Заказов")
    assert "Добавлен" in (await telegram("/add Лендинг\nНужна главная"))[-1].text
    assert "Нужна главная" in (await telegram("/jobs 1"))[-1].text
    assert "не найден" in (await telegram("/jobs 999"))[-1].text
    assert "целое" in (await telegram("/jobs bad"))[-1].text


async def test_rate_limit(telegram):
    for _ in range(30):
        assert await telegram("/help")
    assert await telegram("/help") == []


async def test_job_button(telegram):
    await telegram("/add Новый сайт")
    card = (await telegram("/jobs 1"))[-1]
    button = card.reply_markup.inline_keyboard[0][0]
    assert button.callback_data == "job:analyze:1"
    assert "ИИ выключен" in (await telegram(button.callback_data, button=True))[-1].text
    denied = await telegram(button.callback_data, button=True, user=123)
    assert [m.__api_method__ for m in denied] == ["answerCallbackQuery"]
