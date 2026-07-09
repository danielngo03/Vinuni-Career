"""SSRF-guarded outbound webhook delivery for the workflow engine.

A ``webhook`` node lets an org push a workflow event to an external URL. That is
a classic Server-Side Request Forgery surface, so every delivery MUST pass the
guard here first:

- scheme restricted to ``http``/``https`` (no ``file:``/``gopher:``/… smuggling);
- the target host is resolved and EVERY resolved address is rejected if it is
  loopback / private / link-local (incl. the ``169.254.169.254`` cloud metadata
  endpoint) / multicast / reserved / unspecified — for both IPv4 and IPv6 (incl.
  IPv4-mapped IPv6);
- redirects are disabled (a 30x can't bounce a public host to an internal one);
- the request is time-boxed;
- the caller sends only a REDACTED payload (no raw PII leaves the platform).

Residual limitation (documented, not silently ignored): resolve-then-connect has
a small DNS-rebinding TOCTOU window. Pinning the validated IP into the transport
is the follow-up hardening; for now redirects-off + timeout + private-range block
is the first-tier defense.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse


class WebhookError(Exception):
    """A webhook could not be delivered safely. ``user_safe_error`` is a short,
    non-leaking reason suitable for a workflow node's recoverable-failure task.
    """

    def __init__(self, user_safe_error: str) -> None:
        self.user_safe_error = user_safe_error
        super().__init__(user_safe_error)


_ALLOWED_SCHEMES = frozenset({"http", "https"})
Resolver = Callable[[str, int], Awaitable[list[str]]]


def _ip_is_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True for any non-public address a webhook must never be able to reach."""

    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


async def _default_resolver(host: str, port: int) -> list[str]:
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    return [info[4][0] for info in infos]


async def assert_safe_webhook_url(url: str, *, resolver: Resolver | None = None) -> tuple[str, int]:
    """Validate ``url`` is a safe public webhook target. Raises ``WebhookError``
    otherwise. Returns ``(host, port)`` on success.
    """

    resolve = resolver or _default_resolver
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise WebhookError("giao thức không được hỗ trợ")
    host = parsed.hostname
    if not host:
        raise WebhookError("URL không hợp lệ")
    port = parsed.port or (443 if scheme == "https" else 80)

    try:
        literal = ipaddress.ip_address(host)
        candidates = [str(literal)]
    except ValueError:
        try:
            candidates = await resolve(host, port)
        except Exception as exc:  # noqa: BLE001 — DNS failure is a safe rejection
            raise WebhookError("không phân giải được tên miền") from exc

    if not candidates:
        raise WebhookError("không phân giải được tên miền")
    for candidate in candidates:
        try:
            ip = ipaddress.ip_address(candidate)
        except ValueError as exc:
            raise WebhookError("địa chỉ đích không hợp lệ") from exc
        if _ip_is_blocked(ip):
            raise WebhookError("đích đến nội bộ bị chặn")
    return host, port


async def post_webhook(
    url: str,
    payload: dict[str, Any],
    *,
    delivery_id: str,
    # `timeout` is forwarded to httpx's own client timeout, not an asyncio.timeout.
    timeout: float = 5.0,  # noqa: ASYNC109
    resolver: Resolver | None = None,
    client: Any | None = None,
) -> int:
    """POST ``payload`` as JSON to a validated public ``url``. Returns the HTTP
    status code; raises ``WebhookError`` on an unsafe target, a transport error,
    or a non-2xx response. ``client`` is injectable for tests (an
    ``httpx.AsyncClient``-shaped object); redirects are always disabled.
    """

    await assert_safe_webhook_url(url, resolver=resolver)

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "VinUni-Workflow/1.0",
        "X-Vinuni-Delivery": delivery_id,
        "X-Vinuni-Timestamp": datetime.now(tz=UTC).isoformat(),
    }

    async def _send(http: Any) -> int:
        response = await http.post(url, json=payload, headers=headers)
        status = int(response.status_code)
        if status >= 400:
            raise WebhookError("đích webhook trả về lỗi")
        return status

    if client is not None:
        return await _send(client)

    import httpx

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as http:
            return await _send(http)
    except WebhookError:
        raise
    except httpx.HTTPError as exc:
        raise WebhookError("không kết nối được tới webhook") from exc
