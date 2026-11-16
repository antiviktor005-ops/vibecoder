import asyncio
import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties

from app.bot.handlers import dispatcher, telegram_commands
from app.config import Config
from app.core.errors import safe_error
from app.db.session import database, prepare_database
from app.integrations.ai import AI
from app.scheduler.search import Search
from app.services.commands import Commands

log = logging.getLogger(__name__)


async def retry(stage, action):
    for attempt in range(5):
        try:
            return await action()
        except Exception as exc:
            log.warning("%s · попытка %d/5 · %s", stage, attempt + 1, safe_error(exc))
            if attempt == 4:
                raise
            await asyncio.sleep(2**attempt)


async def main():
    cfg = Config()
    logging.basicConfig(
        level=cfg.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    # Vendor debug records may contain request URLs, SQL parameters or raw update exceptions.
    for name in ("aiogram", "httpx", "httpcore", "openai", "sqlalchemy", "apscheduler", "asyncio"):
        logger = logging.getLogger(name)
        logger.addHandler(logging.NullHandler())
        logger.propagate = False
    engine, sessions = database(cfg)
    bot = Bot(
        cfg.bot_token.get_secret_value(),
        default=DefaultBotProperties(link_preview_is_disabled=True),
    )
    ai = AI(cfg, sessions)
    search = Search(cfg, sessions, bot)
    dp = dispatcher(cfg.admin_telegram_id)
    try:
        await retry(
            "Подготовка PostgreSQL", lambda: prepare_database(engine, cfg.admin_telegram_id)
        )
        await retry(
            "Telegram deleteWebhook", lambda: bot.delete_webhook(drop_pending_updates=False)
        )
        await retry("Telegram setMyCommands", lambda: bot.set_my_commands(telegram_commands()))
        search.scheduler.start()
        log.info("Worker запущен. Интервал поиска %d мин.", cfg.search_interval_minutes)
        await dp.start_polling(
            bot,
            service=Commands(cfg, sessions, ai, search),
            allowed_updates=dp.resolve_used_update_types(),
            handle_as_tasks=False,
            close_bot_session=False,
        )
    finally:
        await search.close()
        if ai.client:
            await ai.client.close()
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as error:
        logging.error("Worker остановлен (%s)", type(error).__name__)
        raise SystemExit(1) from None
