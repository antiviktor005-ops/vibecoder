from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

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
