from alembic.config import Config as AlembicConfig
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from alembic import command
from app.config import Config, pg_url
from app.db.models import Preferences, User


def database(cfg: Config):
    engine = create_async_engine(
        pg_url(cfg.database_url.get_secret_value()),
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={"timeout": 10, "command_timeout": 25},
    )
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def bootstrap(sessions, admin_id):
    async with sessions.begin() as db:
        if not await db.get(User, admin_id):
            db.add(User(id=admin_id))
            await db.flush()
        if not await db.get(Preferences, admin_id):
            db.add(Preferences(user_id=admin_id))


def _upgrade(connection):
    config = AlembicConfig("alembic.ini")
    config.attributes["connection"] = connection
    command.upgrade(config, "head")


async def prepare_database(engine, admin_id):
    # Use the runtime connection: pre-deploy and worker can be configured separately.
    async with engine.begin() as connection:
        await connection.exec_driver_sql("SELECT pg_advisory_xact_lock(27462582)")
        await connection.run_sync(_upgrade)
        await bootstrap(async_sessionmaker(connection), admin_id)
