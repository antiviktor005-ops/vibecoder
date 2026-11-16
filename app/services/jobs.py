import hashlib
import re
from dataclasses import dataclass
from urllib.parse import urldefrag

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.db.models import Job, Notification, Preferences


@dataclass(frozen=True)
class Listing:
    title: str
    brief: str
    url: str | None = None
    external_id: str = ""
    budget_rub: int | None = None
    level: int | None = None


def matches(item: Listing, prefs: Preferences):
    words = [s.strip().casefold() for s in prefs.keywords.split(",") if s.strip()]
    body = f"{item.title} {item.brief}".casefold()
    return (
        (not words or any(w in body for w in words))
        and (not prefs.min_rub or (item.budget_rub or 0) >= prefs.min_rub)
        and (prefs.max_level == 3 or (item.level is not None and item.level <= prefs.max_level))
    )


def manual(text: str):
    lines = text.strip().splitlines()
    return Listing(lines[0][:200], text[:8000])


async def save_job(db, item, source_id=None, notify=False):
    if item.url:
        identity = "url:" + urldefrag(item.url)[0]
    elif item.external_id:
        identity = f"source:{source_id}:{item.external_id}"
    else:
        identity = "text:" + re.sub(r"\s+", " ", item.title + " " + item.brief).strip().casefold()
    key = hashlib.sha256(identity.encode()).hexdigest()
    stmt = insert(Job).values(
        fingerprint=key,
        title=item.title,
        brief=item.brief,
        url=item.url,
        source_id=source_id,
        budget_rub=item.budget_rub,
        level=item.level,
    )
    job_id = await db.scalar(
        stmt.on_conflict_do_nothing(index_elements=[Job.fingerprint]).returning(Job.id)
    )
    if job_id is None:
        return await db.scalar(select(Job.id).where(Job.fingerprint == key)), False
    if notify:
        db.add(Notification(job_id=job_id))
    return job_id, True
