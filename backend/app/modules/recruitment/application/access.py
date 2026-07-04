"""Wiring for the documents snapshot-access authorizer seam.

The documents module exposes a SYNC authorizer seam
(:func:`documents...set_snapshot_access_authorizer`) called inside
:func:`get_snapshot_download` to decide whether a non-owner principal may obtain a
(watermarked) signed URL for an application CV snapshot. Partner authorization is
inherently async (load the application -> verify the partner owns the job's org ->
verify the anonymous-reveal state), so the recruitment service performs the full
async decision first, then publishes a one-shot grant on a context variable that
the registered sync authorizer simply echoes.

This keeps the documents module unaware of recruitment internals (it never imports
``applications``) while letting recruitment own the real authorization logic. The
grant is scoped to a single ``with authorized_download(...)`` block and is matched
by snapshot id + acting user id, so a stray ``get_snapshot_download`` call outside
the block can never inherit another request's grant.
"""

from __future__ import annotations

import contextvars
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from app.modules.documents.application.snapshot_service import (
    SnapshotAccess,
    set_snapshot_access_authorizer,
)
from app.shared.permissions import Principal


@dataclass(slots=True)
class _Grant:
    snapshot_id: uuid.UUID
    user_id: uuid.UUID | None
    watermark_text: str


_pending_grant: contextvars.ContextVar[_Grant | None] = contextvars.ContextVar(
    "recruitment_snapshot_grant", default=None
)


def _authorizer(principal: Principal, snapshot) -> SnapshotAccess | None:
    grant = _pending_grant.get()
    if grant is None:
        return None
    if snapshot.id != grant.snapshot_id:
        return None
    if principal.user_id != grant.user_id:
        return None
    return SnapshotAccess(watermark_text=grant.watermark_text)


def install_authorizer() -> None:
    """Register the recruitment partner-access authorizer (idempotent)."""

    set_snapshot_access_authorizer(_authorizer)


@contextmanager
def authorized_download(
    *, snapshot_id: uuid.UUID, user_id: uuid.UUID | None, watermark_text: str
) -> Iterator[None]:
    """Publish a one-shot partner-access grant for a single snapshot download."""

    token = _pending_grant.set(
        _Grant(snapshot_id=snapshot_id, user_id=user_id, watermark_text=watermark_text)
    )
    try:
        yield
    finally:
        _pending_grant.reset(token)
