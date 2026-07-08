"""Messaging realtime WebSocket endpoint — ``/api/v1/messaging/ws?token=…``.

Auth is re-checked on connect (`.claude/rules/realtime.md`): the access token is
decoded and the session/user/identity validated exactly like the HTTP path, then the
socket subscribes to its ``user:{id}`` channel and — for a staff member with the
``messaging:read`` capability — its ``org:{id}`` channel (shared inbox). Only lightweight
signals flow over the socket (``{type, thread_id}``); clients refetch, so masking is
never bypassed. The DB session is short-lived (auth + per-typing checks), never held for
the connection lifetime.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.core.db import get_sessionmaker
from app.modules.auth.domain.models import Session
from app.modules.auth.infrastructure import token_revocation
from app.modules.auth.infrastructure.jwt import (
    InvalidTokenError,
    decode_access_token,
)
from app.modules.messaging.application import capability
from app.modules.messaging.application.realtime import (
    channels_for_thread,
    connection_manager,
    publish_signal,
)
from app.modules.messaging.application.realtime.hub import org_channel, user_channel
from app.modules.messaging.domain import rules
from app.modules.messaging.domain.models import (
    MessageThreadParticipant,
    MessageThreadParty,
)
from app.modules.organization.application import grant_resolver
from app.modules.users.application import user_service
from app.shared.permissions import Principal

ws_router = APIRouter(prefix="/messaging", tags=["messaging"])


async def _principal_from_token(token: str) -> Principal | None:
    try:
        claims = decode_access_token(token)
    except InvalidTokenError:
        return None
    if await token_revocation.is_revoked(claims.jti):
        return None
    async with get_sessionmaker()() as session:
        sess = (
            await session.execute(select(Session).where(Session.id == claims.session_id))
        ).scalar_one_or_none()
        if sess is None or not sess.is_active(now=datetime.now(tz=UTC)):
            return None
        user = await user_service.get_by_id(session, claims.user_id)
        if user is None or not user.is_active:
            return None
        identity = await user_service.get_identity(
            session, identity_id=claims.identity_id, user_id=user.id
        )
        if identity is None:
            return None
        permissions = await grant_resolver.resolve_grants(
            session, user_id=user.id, identity=identity
        )
        return Principal(
            user_id=user.id,
            persona=identity.persona,
            org_id=identity.org_id,
            is_superadmin=user.is_superadmin,
            permissions=permissions,
        )


async def _user_in_thread(principal: Principal, thread_id: uuid.UUID) -> bool:
    async with get_sessionmaker()() as session:
        part = (
            await session.execute(
                select(MessageThreadParticipant.user_id).where(
                    MessageThreadParticipant.thread_id == thread_id,
                    MessageThreadParticipant.user_id == principal.user_id,
                    MessageThreadParticipant.removed_at.is_(None),
                )
            )
        ).first()
        if part is not None:
            return True
        if principal.org_id is None:
            return False
        org_party = (
            await session.execute(
                select(MessageThreadParty.id).where(
                    MessageThreadParty.thread_id == thread_id,
                    MessageThreadParty.party_kind == rules.PARTY_ORG,
                    MessageThreadParty.org_id == principal.org_id,
                )
            )
        ).first()
        return org_party is not None and capability.can_read_org_inbox(
            principal, principal.org_id
        )


@ws_router.websocket("/ws")
async def messaging_ws(
    websocket: WebSocket,
    token: str = Query(default=""),
) -> None:
    principal = await _principal_from_token(token) if token else None
    if principal is None or principal.user_id is None:
        await websocket.close(code=4401)  # unauthorized
        return

    channels = [user_channel(principal.user_id)]
    if principal.org_id is not None and capability.can_read_org_inbox(
        principal, principal.org_id
    ):
        channels.append(org_channel(principal.org_id))

    await websocket.accept()

    async def _send(event: dict) -> None:
        await websocket.send_json(event)

    conn = await connection_manager.register(send=_send, channels=channels)
    try:
        await websocket.send_json({"type": "ready"})
        while True:
            data = await websocket.receive_json()
            # The only client→server message is an ephemeral typing signal.
            if isinstance(data, dict) and data.get("type") == "typing":
                raw = data.get("thread_id")
                try:
                    thread_id = uuid.UUID(str(raw))
                except (ValueError, TypeError):
                    continue
                if await _user_in_thread(principal, thread_id):
                    async with get_sessionmaker()() as session:
                        targets = await channels_for_thread(
                            session,
                            thread_id=thread_id,
                            exclude_user_id=principal.user_id,
                        )
                    await publish_signal(
                        targets, {"type": "typing", "thread_id": str(thread_id)}
                    )
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001 - never let a socket error crash the worker
        pass
    finally:
        await connection_manager.unregister(conn)
