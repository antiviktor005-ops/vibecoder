import os
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from alembic.config import Config as Migration
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from alembic import command
from app.config import Config, pg_url
from app.db.models import Base
from app.db.session import bootstrap
from app.integrations.ai import AI
from app.scheduler.search import Search
from app.services.commands import Commands


@pytest.fixture
def cfg():
    return Config(
        _env_file=None,
        bot_token="1:test",
        admin_telegram_id=9876,
        openai_api_key=None,
        database_url="postgresql://localhost/test",
        allowed_user_ids="123",
        openai_model="gpt-4o-mini",
    )


@pytest.fixture
async def sessions(cfg):
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    await bootstrap(factory, cfg.admin_telegram_id)
    yield factory
    await engine.dispose()


@pytest.fixture
async def pg_engine():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Для интеграционного теста задайте TEST_DATABASE_URL.")
    schema = "vw_test_" + uuid4().hex
    root = create_async_engine(pg_url(url))
    async with root.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        pg_url(url), connect_args={"server_settings": {"search_path": schema}}
    )
    try:
        yield engine
    finally:
        await engine.dispose()
        async with root.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await root.dispose()


@pytest.fixture
async def pg_sessions(cfg, pg_engine):
    async with pg_engine.begin() as conn:

        def migrate(connection):
            migration = Migration("alembic.ini")
            migration.attributes["connection"] = connection
            command.upgrade(migration, "head")

        await conn.run_sync(migrate)
    factory = async_sessionmaker(pg_engine, expire_on_commit=False)
    await bootstrap(factory, cfg.admin_telegram_id)
    return factory


@pytest.fixture
def service(cfg, sessions):
    ai = AI(cfg, sessions)
    search = Search(cfg, sessions, AsyncMock(), fetch=AsyncMock())
    return Commands(cfg, sessions, ai, search)
