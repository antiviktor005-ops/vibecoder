import asyncio
import logging
import time
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.core.errors import InputError
from app.db.models import Job, Notification, Preferences, Source
from app.integrations.feeds import ADAPTERS
from app.security.urls import fetch_public
from app.services.jobs import matches, save_job

log = logging.getLogger(__name__)


class Search:
    def __init__(self, cfg, sessions, bot, fetch=fetch_public):
        self.cfg, self.sessions, self.bot, self.fetch = cfg, sessions, bot, fetch
        self.lock = asyncio.Lock()
        self.last_run = None
        self.last_start = -float("inf")
        self.stopping = False
        self.scheduler = AsyncIOScheduler(timezone="UTC")
        self.scheduler.add_job(
            self.tick,
            "interval",
            minutes=cfg.search_interval_minutes,
            id="feeds",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=60,
        )

    async def tick(self):
        try:
            await self.run()
        except Exception as exc:
            log.warning("Сбой фонового поиска (%s)", type(exc).__name__)

    async def run(self, manual=False):
        if (
            self.stopping
            or self.lock.locked()
            or (manual and time.monotonic() - self.last_start < 60)
        ):
            raise InputError("Поиск уже выполняется или недавно запускался.")
        async with self.lock:
            self.last_start = time.monotonic()
            async with self.sessions() as db:
                sources = (
                    await db.scalars(select(Source).where(Source.enabled).order_by(Source.id))
                ).all()
            added = failed = 0
            for source in sources:
                if self.stopping:
                    break
                count = 0
                try:
                    body = await self.fetch(source.url)
                    listings = list(ADAPTERS[source.kind](body))
                    async with self.sessions.begin() as db:
                        prefs = await db.get(Preferences, self.cfg.admin_telegram_id)
                        for listing in listings:
                            if matches(listing, prefs):
                                _, new = await save_job(db, listing, source.id, prefs.notify)
                                count += int(new)
                    added += count
                    status = f"добавлено {count}"
                except Exception as exc:
                    failed += 1
                    status = (
                        str(exc) if isinstance(exc, InputError) else "ошибка получения или формата"
                    )
                    log.warning("Сбой источника #%d (%s)", source.id, type(exc).__name__)
                async with self.sessions.begin() as db:
                    current = await db.get(Source, source.id)
                    current.last_result = f"{datetime.now(UTC):%m-%d %H:%M} UTC · {status}"
            sent = await self.deliver()
            self.last_run = datetime.now(UTC)
            return f"Новых заказов {added}, уведомлений {sent}, ошибок источников {failed}."

    async def deliver(self):
        async with self.sessions() as db:
            prefs = await db.get(Preferences, self.cfg.admin_telegram_id)
            if not prefs.notify:
                return 0
            rows = (
                await db.execute(
                    select(Notification.id, Job.id, Job.title)
                    .join(Job, Notification.job_id == Job.id)
                    .where(~Notification.sent)
                    .order_by(Notification.id)
                    .limit(30)
                )
            ).all()
        sent = 0
        for key, job_id, title in rows:
            if self.stopping:
                break
            try:
                await self.bot.send_message(
                    self.cfg.admin_telegram_id, f"Новый заказ #{job_id}\n{title}\n/jobs {job_id}"
                )
            except Exception as exc:
                log.warning("Уведомление отложено (%s)", type(exc).__name__)
                break
            async with self.sessions.begin() as db:
                (await db.get(Notification, key)).sent = True
            sent += 1
        return sent

    async def close(self):
        self.stopping = True
        if self.scheduler.running:
            self.scheduler.pause()
            async with self.lock:
                self.scheduler.shutdown(wait=False)
