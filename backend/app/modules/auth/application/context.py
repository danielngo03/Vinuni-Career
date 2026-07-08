"""Request-scoped client context (raw IP / user-agent).

Raw values live only in memory for the duration of a request. Services hash them
(IP/UA) before persistence and derive a coarse ``device_hint`` — raw IP, raw UA,
and refresh tokens are never stored or returned (``docs/SECURITY_PRIVACY.md``).
"""

from __future__ import annotations

from dataclasses import dataclass

from starlette.requests import Request


@dataclass(slots=True)
class RequestContext:
    ip: str | None = None
    user_agent: str | None = None


def context_from_request(request: Request) -> RequestContext:
    forwarded = request.headers.get("x-forwarded-for")
    ip: str | None
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    else:
        ip = request.client.host if request.client else None
    return RequestContext(ip=ip, user_agent=request.headers.get("user-agent"))
