"""Audit writer persists hashed IP/UA and metadata snapshots."""

from __future__ import annotations

import uuid

from app.shared.audit import AuditContext, write_audit
from app.shared.models import AuditLog
from sqlalchemy import select


async def test_write_audit_persists_hashed_values(db_session) -> None:
    actor = uuid.uuid4()
    resource = uuid.uuid4()
    ctx = AuditContext(actor_id=actor, ip="203.0.113.5", user_agent="Mozilla/5.0 Chrome")

    entry = await write_audit(
        db_session,
        action="job.created",
        resource_type="job",
        resource_id=resource,
        context=ctx,
        after={"title": "Backend Intern"},
    )
    await db_session.commit()

    assert entry is not None
    row = (
        await db_session.execute(select(AuditLog).where(AuditLog.id == entry.id))
    ).scalar_one()
    assert row.action == "job.created"
    assert row.actor_id == actor
    # IP/UA stored as hashes, never raw values.
    assert row.ip_hash and row.ip_hash != "203.0.113.5"
    assert len(row.ip_hash) == 64
    assert row.user_agent_hash and "Mozilla" not in row.user_agent_hash
    assert row.after_snapshot == {"title": "Backend Intern"}


async def test_write_audit_handles_missing_context(db_session) -> None:
    entry = await write_audit(
        db_session, action="system.ping", resource_type="system"
    )
    await db_session.commit()
    assert entry is not None
    assert entry.ip_hash is None
    assert entry.user_agent_hash is None
