import io
import json
import re
from html.parser import HTMLParser

import feedparser
from defusedxml import ElementTree
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.errors import InputError
from app.security.urls import source_url
from app.services.jobs import Listing


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def plain(value, limit):
    parser = PlainText()
    parser.feed(str(value or ""))
    return " ".join(" ".join(parser.parts).split())[:limit]


def link(value):
    if not value:
        return None
    try:
        return str(source_url(value))
    except InputError:
        return None


class Entry(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)
    id: str = Field(default="", max_length=512)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=8000)
    url: str | None = None
    budget_rub: int | None = Field(default=None, ge=0, le=2_000_000_000)
    level: int | None = Field(default=None, ge=1, le=3)


def api_items(body):
    payload = json.loads(body)
    rows = payload.get("jobs") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise InputError("JSON API должен возвращать массив jobs.")
    for row in rows[:50]:
        try:
            entry = Entry.model_validate(row)
        except ValidationError:
            continue
        yield Listing(
            entry.title, entry.description, link(entry.url), entry.id, entry.budget_rub, entry.level
        )


def rss_items(body):
    ElementTree.fromstring(body, forbid_dtd=True)
    feed = feedparser.parse(io.BytesIO(body), resolve_relative_uris=False)
    if not feed.version:
        raise InputError("Не распознана лента RSS/Atom.")
    for row in feed.entries[:50]:
        title = plain(row.get("title"), 200)
        if not title:
            continue
        brief = plain(row.get("summary") or title, 8000)
        match = re.search(r"(?<![\d.])(\d[\d \u00a0]{0,12})\s*(?:₽|руб\b|RUB\b)", brief, re.I)
        price = int("".join(match[1].split())) if match else None
        if price is not None and price > 2_000_000_000:
            price = None
        label = re.search(r"сложность\s*[:=]\s*([1-3])\b", brief, re.I)
        yield Listing(
            title,
            brief,
            link(row.get("link")),
            str(row.get("id", ""))[:512],
            price,
            int(label[1]) if label else None,
        )


ADAPTERS = {"rss": rss_items, "api": api_items}
