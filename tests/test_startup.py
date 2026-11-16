import asyncio

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.errors import safe_error
from app.db.models import Preferences
from app.db.session import bootstrap, prepare_database


async def test_start_with_empty_database_and_restart(pg_engine, cfg):
    factory = async_sessionmaker(pg_engine)
    with pytest.raises(ProgrammingError) as missing:
        await bootstrap(factory, cfg.admin_telegram_id)
    assert "42P01" in safe_error(missing.value)
    await asyncio.gather(*(prepare_database(pg_engine, cfg.admin_telegram_id) for _ in range(2)))
    async with factory.begin() as db:
        (await db.get(Preferences, cfg.admin_telegram_id)).keywords = "лендинг"
    await prepare_database(pg_engine, cfg.admin_telegram_id)
    async with factory() as db:
        assert await db.scalar(text("SELECT version_num FROM alembic_version")) == "0001"
        assert await db.scalar(select(Preferences.keywords)) == "лендинг"
