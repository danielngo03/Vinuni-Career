"""Adversarial tests for the workflow webhook SSRF guard.

A ``webhook`` workflow node lets an org POST an event to an external URL — a
classic Server-Side Request Forgery surface. These tests pin the guard's
fail-closed behaviour: only public http(s) targets are reachable, every
internal/private/metadata address is refused (for both IPv4 and IPv6, incl.
IPv4-mapped), DNS that resolves to a private address is refused, redirects are
disabled, and a non-2xx response is a failure — never a silent success.
"""

from __future__ import annotations

import pytest
from app.modules.workflow.application import webhook_dispatch
from app.modules.workflow.application.webhook_dispatch import (
    WebhookError,
    assert_safe_webhook_url,
    post_webhook,
)


def _resolver_to(*ips: str):
    async def _resolve(host: str, port: int) -> list[str]:
        return list(ips)

    return _resolve


# --------------------------------------------------------------------------- #
# Scheme / URL validation                                                     #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "gopher://evil/",
        "ftp://internal/secret",
        "ws://internal/socket",
        "://no-scheme",
    ],
)
async def test_non_http_scheme_is_refused(url: str) -> None:
    with pytest.raises(WebhookError):
        await assert_safe_webhook_url(url, resolver=_resolver_to("8.8.8.8"))


@pytest.mark.asyncio
async def test_missing_host_is_refused() -> None:
    with pytest.raises(WebhookError):
        await assert_safe_webhook_url("http://", resolver=_resolver_to("8.8.8.8"))


# --------------------------------------------------------------------------- #
# Private / internal / metadata address blocking                              #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "literal",
    [
        "http://127.0.0.1/hook",  # loopback
        "http://10.0.0.5/hook",  # private A
        "http://192.168.1.10/hook",  # private C
        "http://172.16.9.9/hook",  # private B
        "http://169.254.169.254/latest/meta-data",  # cloud metadata (link-local)
        "http://0.0.0.0/hook",  # unspecified
        "http://[::1]/hook",  # IPv6 loopback
        "http://[fd00::1]/hook",  # IPv6 unique-local (private)
        "http://[::ffff:127.0.0.1]/hook",  # IPv4-mapped loopback
    ],
)
async def test_internal_ip_literal_is_blocked(literal: str) -> None:
    with pytest.raises(WebhookError):
        await assert_safe_webhook_url(literal)


@pytest.mark.asyncio
async def test_public_hostname_resolving_to_private_is_blocked() -> None:
    # DNS points a friendly-looking host at an internal address — must be refused.
    with pytest.raises(WebhookError):
        await assert_safe_webhook_url(
            "https://hook.partner.example", resolver=_resolver_to("10.1.2.3")
        )


@pytest.mark.asyncio
async def test_any_private_address_among_many_blocks_the_whole_target() -> None:
    # Even one private A-record in a multi-address answer must fail closed.
    with pytest.raises(WebhookError):
        await assert_safe_webhook_url(
            "https://hook.partner.example",
            resolver=_resolver_to("8.8.8.8", "127.0.0.1"),
        )


@pytest.mark.asyncio
async def test_public_target_is_accepted() -> None:
    host, port = await assert_safe_webhook_url(
        "https://hooks.partner.example/wf", resolver=_resolver_to("8.8.8.8")
    )
    assert host == "hooks.partner.example"
    assert port == 443


@pytest.mark.asyncio
async def test_dns_failure_is_a_safe_rejection() -> None:
    async def _boom(host: str, port: int) -> list[str]:
        raise OSError("dns down")

    with pytest.raises(WebhookError):
        await assert_safe_webhook_url("https://hook.partner.example", resolver=_boom)


# --------------------------------------------------------------------------- #
# post_webhook delivery (injected client)                                     #
# --------------------------------------------------------------------------- #


class _FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _FakeClient:
    """Records the outbound call so we can assert redirects-off + payload."""

    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code
        self.calls: list[dict] = []

    async def post(self, url: str, *, json: dict, headers: dict) -> _FakeResponse:
        self.calls.append({"url": url, "json": json, "headers": headers})
        return _FakeResponse(self.status_code)


@pytest.mark.asyncio
async def test_post_webhook_delivers_to_public_target() -> None:
    client = _FakeClient(status_code=200)
    status = await post_webhook(
        "https://hooks.partner.example/wf",
        {"event": "x"},
        delivery_id="wf:1:n2",
        resolver=_resolver_to("8.8.8.8"),
        client=client,
    )
    assert status == 200
    assert len(client.calls) == 1
    sent = client.calls[0]
    assert sent["headers"]["X-Vinuni-Delivery"] == "wf:1:n2"
    assert sent["json"] == {"event": "x"}


@pytest.mark.asyncio
async def test_post_webhook_refuses_internal_target_before_sending() -> None:
    client = _FakeClient(status_code=200)
    with pytest.raises(WebhookError):
        await post_webhook(
            "http://169.254.169.254/latest/meta-data",
            {"event": "x"},
            delivery_id="wf:1:n2",
            client=client,
        )
    # The guard must reject BEFORE any network call is attempted.
    assert client.calls == []


@pytest.mark.asyncio
async def test_post_webhook_non_2xx_is_a_failure() -> None:
    client = _FakeClient(status_code=500)
    with pytest.raises(WebhookError):
        await post_webhook(
            "https://hooks.partner.example/wf",
            {"event": "x"},
            delivery_id="d",
            resolver=_resolver_to("8.8.8.8"),
            client=client,
        )


def test_module_disables_redirects_by_default() -> None:
    # Defence-in-depth: the real httpx client is always built with
    # follow_redirects=False so a 30x cannot bounce a public host internal.
    import inspect

    src = inspect.getsource(webhook_dispatch.post_webhook)
    assert "follow_redirects=False" in src
