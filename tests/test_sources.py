import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.errors import InputError
from app.integrations.feeds import api_items, rss_items
from app.security import urls


@pytest.mark.parametrize(
    "value",
    [
        "http://example.org",
        "https://localhost/a",
        "file:///etc/hosts",
        "https://127.0.0.1",
        "https://[::1]",
        "https://[::ffff:127.0.0.1]",
        "https://169.254.169.254",
        "https://100.64.0.1",
        "https://224.0.0.1",
        "https://u:p@example.org",
        "https://example.org:22",
        "https://db.railway.internal",
    ],
)
def test_forbidden_addresses(value):
    with pytest.raises(InputError):
        urls.source_url(value)


async def test_mixed_dns(monkeypatch):
    monkeypatch.setattr(
        asyncio.get_running_loop(),
        "getaddrinfo",
        AsyncMock(return_value=[(0, 0, 0, "", ("1.1.1.1", 443)), (0, 0, 0, "", ("10.0.0.1", 443))]),
    )
    with pytest.raises(InputError, match="DNS"):
        await urls.resolve("example.org")


@pytest.mark.parametrize("mode", ["ok", "redirect", "large", "compressed"])
async def test_pinned_transport(monkeypatch, mode):
    monkeypatch.setattr(urls, "resolve", AsyncMock(return_value="1.1.1.1"))

    def handle(request):
        assert request.url.host == "1.1.1.1"
        assert request.headers["host"] == request.extensions["sni_hostname"] == "example.org"
        headers = {"location": "https://127.0.0.1/"} if mode == "redirect" else {}
        if mode == "compressed":
            headers["content-encoding"] = "gzip"
        body = b"x" * (urls.MAX_BODY + 1) if mode == "large" else b"test"
        return httpx.Response(
            302 if mode == "redirect" else 200, headers=headers, stream=httpx.ByteStream(body)
        )

    fetch = urls.fetch_public("https://example.org/rss", transport=httpx.MockTransport(handle))
    if mode == "ok":
        assert await fetch == b"test"
    else:
        with pytest.raises(InputError):
            await fetch


def test_feed_formats():
    rss = "<rss version='2.0'><channel><item><title>Сайт</title><description>12 000 ₽. Сложность: 2</description></item></channel></rss>"
    (item,) = rss_items(rss.encode())
    assert item.budget_rub == 12000 and item.level == 2
    atom = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Site</title><id>abc</id></entry></feed>'
    assert next(rss_items(atom)).external_id == "abc"
    assert not list(api_items(b'{"jobs":[{"id":42}]}'))
    with pytest.raises(InputError):
        list(api_items(b'{"error":true}'))
