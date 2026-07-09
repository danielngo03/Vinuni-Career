"""Email adapters — ``ConsoleEmailAdapter`` for local dev, ``SmtpEmailAdapter`` for production.

Both implement the ``EmailAdapter`` protocol so ``dispatch_service.process_outbox``
can swap them without any product code changes. SMTP credentials live in
``backend/.env`` only — never committed.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
import uuid
from dataclasses import dataclass
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Protocol

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SentEmail:
    to: str
    subject: str
    body: str
    message_id: str


class EmailAdapter(Protocol):
    async def send(self, *, to: str, subject: str, body: str) -> str: ...


class ConsoleEmailAdapter:
    """Captures emails locally instead of sending them (dev/test only)."""

    def __init__(self) -> None:
        self.outbox: list[SentEmail] = []

    async def send(self, *, to: str, subject: str, body: str) -> str:
        message_id = f"local_{uuid.uuid4().hex}"
        self.outbox.append(SentEmail(to=to, subject=subject, body=body, message_id=message_id))
        # Log metadata only — never the body or recipient PII.
        logger.info(
            "email.sent_local",
            extra={
                "message_id": message_id,
                "subject_len": len(subject),
                "channel": "email",
            },
        )
        return message_id


class SmtpEmailAdapter:
    """Production SMTP adapter. Supports SSL (port 465) and STARTTLS (port 587).

    Sending is done in a thread-pool executor so we don't block the event loop.
    Credentials are passed at construction time from ``Settings`` (never hardcoded).
    """

    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        from_address: str,
        from_name: str,
        use_ssl: bool = True,
        timeout: int = 30,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._from = formataddr((from_name, from_address))
        self._use_ssl = use_ssl
        self._timeout = timeout

    async def send(self, *, to: str, subject: str, body: str) -> str:
        message_id = f"smtp_{uuid.uuid4().hex}"
        raw_message = self._build_message(to=to, subject=subject, body=body, message_id=message_id)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._send_sync, to, raw_message)
        logger.info(
            "email.sent_smtp",
            extra={"message_id": message_id, "subject_len": len(subject), "channel": "email"},
        )
        return message_id

    def _build_message(self, *, to: str, subject: str, body: str, message_id: str) -> str:
        msg = MIMEMultipart("alternative")
        msg["From"] = self._from
        msg["To"] = to
        msg["Subject"] = str(Header(subject, "utf-8"))
        msg["Message-ID"] = f"<{message_id}@vinuni.edu.vn>"
        # Attach plain text part; if body looks like HTML, attach HTML part too
        msg.attach(MIMEText(body, "plain", "utf-8"))
        if body.lstrip().startswith("<"):
            msg.attach(MIMEText(body, "html", "utf-8"))
        return msg.as_string()

    def _send_sync(self, to: str, raw_message: str) -> None:
        if self._use_ssl:
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(
                self._host, self._port, context=ctx, timeout=self._timeout
            ) as smtp:
                smtp.login(self._username, self._password)
                smtp.sendmail(self._username, [to], raw_message.encode("utf-8"))
        else:
            with smtplib.SMTP(self._host, self._port, timeout=self._timeout) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.login(self._username, self._password)
                smtp.sendmail(self._username, [to], raw_message.encode("utf-8"))


def build_email_adapter() -> EmailAdapter:
    """Factory: resolve the correct adapter from Settings.

    Called once at startup or per-process by ``process_outbox``.
    Returns ``SmtpEmailAdapter`` when ``email_provider == "smtp"``,
    otherwise falls back to ``ConsoleEmailAdapter``.
    """
    from app.core.config import get_settings  # local import to avoid circular

    settings = get_settings()
    if settings.email_provider == "smtp":
        return SmtpEmailAdapter(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password,
            from_address=settings.email_from_address,
            from_name=settings.email_from_name,
            use_ssl=settings.smtp_use_ssl,
            timeout=settings.smtp_timeout,
        )
    return ConsoleEmailAdapter()
