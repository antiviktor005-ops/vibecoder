from datetime import UTC, datetime
from urllib.parse import urlsplit

from sqlalchemy import func, select, text

from app.core.errors import InputError
from app.db.models import Analysis, Artifact, Draft, Job, Preferences, Project, Source
from app.generator.site import archive
from app.integrations.ai import totals
from app.integrations.feeds import ADAPTERS
from app.security.urls import source_url
from app.services.jobs import manual, save_job

SETTINGS_HELP = (
    "/settings слова python, сайт  ·  очистить: /settings слова -\n"
    "/settings бюджет 10000  ·  минимум в ₽\n/settings сложность 2  ·  от 1 до 3\n"
    "/settings уведомления вкл  ·  вкл/выкл"
)
FEEDS_HELP = (
    "/feeds rss HTTPS_URL  ·  RSS или Atom\n/feeds api HTTPS_URL  ·  JSON API\n"
    "/feeds off ID  ·  отключить\n/feeds on ID  ·  включить\n/feeds run  ·  искать сейчас"
)


def number(value, low=1, high=2_000_000_000):
    if (
        not value.isascii()
        or not value.isdecimal()
        or len(value) > 10
        or not low <= int(value) <= high
    ):
        raise InputError(f"Введите целое число от {low} до {high}.")
    return int(value)


class Commands:
    def __init__(self, cfg, sessions, ai, search):
        self.cfg, self.sessions, self.ai, self.search = cfg, sessions, ai, search

    async def settings(self, args):
        async with self.sessions.begin() as db:
            prefs = await db.get(Preferences, self.cfg.admin_telegram_id, with_for_update=True)
            if args:
                mode, _, value = args.partition(" ")
                value = value.strip()
                if mode == "слова" and 0 < len(value) <= 200:
                    prefs.keywords = "" if value == "-" else value
                elif mode == "бюджет":
                    prefs.min_rub = number(value, 0)
                elif mode == "сложность":
                    prefs.max_level = number(value, 1, 3)
                elif mode == "уведомления" and value in ("вкл", "выкл"):
                    prefs.notify = value == "вкл"
                else:
                    raise InputError(SETTINGS_HELP)
            return (
                f"Слова: {prefs.keywords or 'любые'}\nМинимум: {prefs.min_rub} ₽\n"
                f"Сложность до {prefs.max_level}\nУведомления: {'вкл' if prefs.notify else 'выкл'}\n\n{SETTINGS_HELP}"
            )

    async def feeds(self, args):
        if args == "run":
            return await self.search.run(manual=True)
        async with self.sessions.begin() as db:
            if args:
                mode, _, value = args.partition(" ")
                value = value.strip()
                if mode in ADAPTERS:
                    address = str(source_url(value))
                    source = await db.scalar(select(Source).where(Source.url == address))
                    if source:
                        source.enabled, source.kind = True, mode
                    elif await db.scalar(select(func.count()).select_from(Source)) >= 20:
                        raise InputError("Достигнут лимит 20 источников.")
                    else:
                        db.add(Source(kind=mode, url=address))
                elif mode in ("off", "on"):
                    source = await db.get(Source, number(value))
                    if not source:
                        raise InputError("Источник не найден.")
                    source.enabled = mode == "on"
                else:
                    raise InputError(FEEDS_HELP)
            rows = (await db.scalars(select(Source).order_by(Source.id))).all()
            lines = [
                f"#{s.id} {s.kind} {urlsplit(s.url).hostname} · {'вкл' if s.enabled else 'выкл'} · {s.last_result}"
                for s in rows
            ]
            return "\n".join(lines or ["Источники пока не добавлены."]) + "\n\n" + FEEDS_HELP

    async def add(self, args):
        if not args:
            raise InputError("Напишите /add Заголовок, а со следующей строки добавьте ТЗ.")
        async with self.sessions.begin() as db:
            key, new = await save_job(db, manual(args))
        return f"{'Добавлен заказ' if new else 'Уже есть заказ'} #{key}. Открыть: /jobs {key}"

    async def job(self, args):
        async with self.sessions() as db:
            job = await db.get(Job, number(args))
            if not job:
                raise InputError("Заказ не найден. Посмотрите /jobs.")
            return job

    async def jobs(self, args):
        if args:
            job = await self.job(args)
            return (
                f"Заказ #{job.id} · {job.title}\n{job.brief[:2600]}\n"
                f"Бюджет, ₽: {job.budget_rub if job.budget_rub is not None else 'не указан'}\n"
                f"Сложность: {job.level or 'не указана'}\n{job.url or ''}\n\n"
                f"/analyze {job.id}   /reply {job.id}   /site {job.id}"
            )
        async with self.sessions() as db:
            rows = (await db.scalars(select(Job).order_by(Job.id.desc()).limit(15))).all()
            return (
                "\n".join(f"#{r.id} {r.title}" for r in rows) + "\n\nОткрыть: /jobs ID"
                if rows
                else "Заказов пока нет. Начните с /add или /feeds."
            )

    async def generate(self, task, args):
        if not args:
            raise InputError(f"Выберите заказ из /jobs и введите /{task} ID.")
        job = await self.job(args)
        result = await self.ai.run(task, job)
        async with self.sessions.begin() as db:
            if task == "site":
                payload = archive(result)
                project = Project(job_id=job.id, title=result.title)
                db.add(project)
                await db.flush()
                db.add(Artifact(project_id=project.id, payload=payload))
                return project.id, payload
            body = result.render() if task == "analyze" else result.text
            model = Analysis if task == "analyze" else Draft
            db.add(model(job_id=job.id, body=body))
            return body

    async def projects(self, args):
        async with self.sessions() as db:
            if args:
                key = number(args)
                payload = await db.scalar(
                    select(Artifact.payload).where(Artifact.project_id == key)
                )
                if payload is None:
                    raise InputError("Проект не найден.")
                return key, payload
            rows = (await db.scalars(select(Project).order_by(Project.id.desc()).limit(15))).all()
            return (
                "\n".join(f"#{r.id} {r.title}" for r in rows) + "\n\nСкачать: /projects ID"
                if rows
                else "Проектов пока нет. Создать: /site ID"
            )

    async def budget(self):
        async with self.sessions() as db:
            count, tokens, cost = await totals(db, datetime.now(UTC).date())
        return (
            f"Сегодня, UTC · с учётом резервов\nЗапросы: {count}/{self.cfg.ai_daily_request_limit}\n"
            f"Токены: {tokens}/{self.cfg.ai_daily_token_limit}\n"
            f"Расчётный расход: ${cost:.6f} / ${self.cfg.ai_daily_budget_usd}\nМодель: {self.cfg.openai_model}"
        )

    async def status(self):
        try:
            async with self.sessions() as db:
                await db.execute(text("SELECT 1"))
            database = "доступна"
        except Exception:
            database = "недоступна"
        last = self.search.last_run
        return (
            f"Telegram: личный чат активен\nБД: {database}\n"
            f"OpenAI: {'ключ задан' if self.ai.client else 'отключён'}\n"
            f"Поиск: {'включён' if self.search.scheduler.running else 'остановлен'}, каждые {self.cfg.search_interval_minutes} мин.\n"
            f"Последний проход: {last.strftime('%d.%m %H:%M UTC') if last else 'ещё не завершён'}"
        )
