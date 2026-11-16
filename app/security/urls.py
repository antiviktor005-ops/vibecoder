import asyncio
import ipaddress
import socket

import httpx

from app.core.errors import InputError

MAX_BODY = 512 * 1024


def public_ip(host):
    ip = ipaddress.ip_address(host)
    if ip == ipaddress.ip_address("168.63.129.16"):
        return False  # Azure platform virtual IP
    if not ip.is_global or ip.is_multicast or ip.is_reserved:
        return False
    if ip.version == 6:
        return ip in ipaddress.ip_network("2000::/3") and not (ip.sixtofour or ip.teredo)
    return True


def source_url(value: str) -> httpx.URL:
    if len(value) > 1024 or not value or any(ord(c) <= 32 for c in value):
        raise InputError("Некорректный адрес источника.")
    try:
        url = httpx.URL(value)
        if (
            url.scheme != "https"
            or not url.host
            or url.port not in (None, 443)
            or url.userinfo
            or url.fragment
            or "\\" in value
            or "%" in url.host
            or any(ord(c) < 32 for c in value)
        ):
            raise ValueError
        try:
            ipaddress.ip_address(url.host)
        except ValueError:
            if "." not in url.host or url.host.rstrip(".").lower().endswith(
                (".internal", ".local", ".localhost")
            ):
                raise ValueError from None
        else:
            if not public_ip(url.host):
                raise ValueError
    except (ValueError, httpx.InvalidURL) as exc:
        raise InputError("Нужен публичный HTTPS URL на порту 443 без данных входа.") from exc
    return url


async def resolve(host: str):
    rows = await asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    addresses = [row[4][0] for row in rows]
    if not addresses or not all(public_ip(ip) for ip in addresses):
        raise InputError("DNS источника вернул запрещённый адрес.")
    return addresses[0]


async def fetch_public(value, *, transport=None):
    url = source_url(value)
    async with asyncio.timeout(18):
        ip = await resolve(url.host)
        # Connect directly to the validated address. Preserve certificate verification for the origin.
        async with httpx.AsyncClient(
            trust_env=False, follow_redirects=False, transport=transport
        ) as client:
            async with client.stream(
                "GET",
                url.copy_with(host=ip),
                headers={
                    "Host": url.netloc.decode(),
                    "Accept-Encoding": "identity",
                    "User-Agent": "VibeWorkerAI/0.1",
                },
                extensions={"sni_hostname": url.raw_host.decode()},
            ) as response:
                if response.status_code != 200:
                    raise InputError(f"Источник вернул HTTP {response.status_code}.")
                if response.headers.get("content-encoding", "identity").lower() != "identity":
                    raise InputError("Источник вернул сжатый ответ.")
                body = bytearray()
                async for part in response.aiter_raw(chunk_size=16384):
                    body.extend(part)
                    if len(body) > MAX_BODY:
                        raise InputError("Источник превышает 512 КиБ.")
                return bytes(body)
