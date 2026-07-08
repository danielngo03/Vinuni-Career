"""OAuth/OIDC account linking + login use cases (Google / Facebook).

Flow summary (``docs/DATA_MODEL.md`` §4 ``oidc_accounts``,
``docs/SECURITY_PRIVACY.md``):

1. ``start`` mints a signed, short-lived state token + CSRF nonce for the
   router to redirect the browser to the provider's consent screen.
2. ``handle_callback`` exchanges the authorization code for verified provider
   user info, then either logs an already-linked user in, auto-links a
   passwordless (SSO-only) account, creates a brand-new account, or — when the
   verified email belongs to an existing PASSWORD account with no link yet —
   returns a conflict result instead of silently linking.
3. No session/tokens are minted at callback time: a one-time ticket is minted
   and the actual login only completes when the frontend redeems it via
   ``exchange_ticket`` (brand-new/auto-linked/already-linked accounts) or
   ``confirm_link`` (conflict path, after the user proves password ownership).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application import errors
from app.modules.auth.application.auth_service import (
    DEFAULT_LOCALE,
    DEFAULT_PERSONA,
    LoginResult,
    _audit_ctx,
    _finalize_login,
)
from app.modules.auth.application.context import RequestContext
from app.modules.auth.domain.models import OidcAccount
from app.modules.auth.infrastructure import jwt as jwt_infra
from app.modules.auth.infrastructure.oauth_providers import (
    OAuthUserInfo,
    get_oauth_provider,
    is_provider_configured,
)
from app.modules.auth.infrastructure.passwords import verify_password
from app.modules.notifications.application.dispatch_service import enqueue_notification
from app.modules.users.application import user_service
from app.modules.users.application.user_write_facade import (
    create_identity,
    create_user,
    set_preference,
)
from app.shared.audit import write_audit

SUPPORTED_PROVIDERS = {"google", "facebook"}


@dataclass(slots=True)
class OAuthLoggedIn:
    """A ticket redeemable (once) for a real session via ``exchange_ticket``."""

    ticket: str


@dataclass(slots=True)
class OAuthLinkConflict:
    """The verified provider email matches an existing PASSWORD account with no
    link for this provider yet. The frontend must collect the password and call
    ``confirm_link`` before any ``OidcAccount`` row is created."""

    ticket: str
    email: str


OAuthCallbackResult = OAuthLoggedIn | OAuthLinkConflict


def ensure_provider_configured(provider: str) -> None:
    if provider not in SUPPORTED_PROVIDERS:
        raise errors.InvalidTokenError("oauth_provider_unsupported")
    if not is_provider_configured(provider):
        raise errors.InvalidTokenError("oauth_not_configured")


async def start(
    *, provider: str, mode: str, return_to: str | None, redirect_uri: str
) -> tuple[str, str, str]:
    """Return ``(authorize_url, state_token, nonce)``."""

    ensure_provider_configured(provider)
    prov = get_oauth_provider(provider)
    nonce = uuid.uuid4().hex
    state = jwt_infra.issue_oauth_state_token(
        provider=provider, mode=mode, return_to=return_to, nonce=nonce
    )
    authorize_url = prov.authorize_url(state=state, redirect_uri=redirect_uri)
    return authorize_url, state, nonce


async def _find_link(
    session: AsyncSession, *, provider: str, provider_user_id: str
) -> OidcAccount | None:
    stmt = select(OidcAccount).where(
        OidcAccount.provider == provider,
        OidcAccount.provider_user_id == provider_user_id,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _notify_oauth_linked(
    session: AsyncSession, *, user, provider: str
) -> None:
    await enqueue_notification(
        session,
        recipient_id=user.id,
        template_key="account.oauth_linked",
        channel="email",
        locale=user.preferred_language,
        variables={"email": user.email, "name": user.full_name or "", "provider": provider},
        dedupe_key=f"oauth_linked:{user.id}:{provider}",
    )


async def handle_callback(
    session: AsyncSession,
    *,
    provider: str,
    code: str,
    redirect_uri: str,
    ctx: RequestContext,
) -> OAuthCallbackResult:
    ensure_provider_configured(provider)
    prov = get_oauth_provider(provider)
    user_info: OAuthUserInfo = await prov.exchange_code(
        code=code, redirect_uri=redirect_uri
    )

    existing_link = await _find_link(
        session, provider=provider, provider_user_id=user_info.provider_user_id
    )
    if existing_link is not None:
        return OAuthLoggedIn(
            ticket=jwt_infra.issue_oauth_ticket_token(user_id=existing_link.user_id)
        )

    if not (user_info.email and user_info.email_verified):
        # Never create/link an account off an unverified provider email.
        raise errors.InvalidTokenError("oauth_email_unverified")

    now = datetime.now(tz=UTC)
    normalized_email = user_service.normalize_email(user_info.email)
    user = await user_service.get_by_email(session, normalized_email)

    if user is None:
        new_user = await create_user(
            session,
            email=normalized_email,
            password_hash=None,
            full_name=user_info.name,
            preferred_language=DEFAULT_LOCALE,
        )
        new_user.email_verified_at = now  # the IdP already verified this email
        await create_identity(
            session, user_id=new_user.id, persona=DEFAULT_PERSONA, is_primary=True
        )
        await set_preference(
            session, user_id=new_user.id, locale=DEFAULT_LOCALE, timezone=new_user.timezone
        )
        session.add(
            OidcAccount(
                user_id=new_user.id,
                provider=provider,
                provider_user_id=user_info.provider_user_id,
                extra_claims={"name": user_info.name},
            )
        )
        await write_audit(
            session,
            action="auth.oauth_register",
            resource_type="user",
            resource_id=new_user.id,
            context=_audit_ctx(ctx, actor_id=new_user.id),
            after={"email": normalized_email, "provider": provider},
        )
        await session.commit()
        return OAuthLoggedIn(ticket=jwt_infra.issue_oauth_ticket_token(user_id=new_user.id))

    if user.password_hash is None:
        # Passwordless / SSO-only account with a matching verified email — safe
        # to auto-link without a password challenge.
        if not user.is_email_verified:
            user.email_verified_at = now
        session.add(
            OidcAccount(
                user_id=user.id,
                provider=provider,
                provider_user_id=user_info.provider_user_id,
                extra_claims={"name": user_info.name},
            )
        )
        await write_audit(
            session,
            action="auth.oauth_linked",
            resource_type="user",
            resource_id=user.id,
            context=_audit_ctx(ctx, actor_id=user.id),
            after={"provider": provider},
        )
        await _notify_oauth_linked(session, user=user, provider=provider)
        await session.commit()
        return OAuthLoggedIn(ticket=jwt_infra.issue_oauth_ticket_token(user_id=user.id))

    # Conflict: a genuine password account already owns this verified email.
    # Do NOT create the OidcAccount yet — require an explicit password confirm.
    ticket = jwt_infra.issue_oauth_link_ticket_token(
        user_id=user.id,
        provider=provider,
        provider_user_id=user_info.provider_user_id,
        email=user_info.email,
        name=user_info.name,
    )
    await enqueue_notification(
        session,
        recipient_id=user.id,
        template_key="account.oauth_conflict",
        channel="email",
        locale=user.preferred_language,
        variables={"email": user.email, "name": user.full_name or "", "provider": provider},
        dedupe_key=f"oauth_conflict:{user.id}:{provider}:{now.isoformat()}",
    )
    await session.commit()
    return OAuthLinkConflict(ticket=ticket, email=user.email)


async def exchange_ticket(
    session: AsyncSession, *, ticket: str, ctx: RequestContext
) -> LoginResult:
    """Redeem a one-time post-callback ticket for a real session. Login/session
    creation happens HERE (not at callback time)."""

    try:
        user_id = jwt_infra.decode_oauth_ticket_token(ticket)
    except jwt_infra.InvalidTokenError as exc:
        raise errors.InvalidTokenError("oauth_ticket_invalid") from exc

    user = await user_service.get_by_id(session, user_id)
    if user is None or not user.is_active:
        raise errors.InvalidTokenError("oauth_ticket_invalid")

    return await _finalize_login(session, user=user, ctx=ctx)


async def confirm_link(
    session: AsyncSession, *, ticket: str, password: str, ctx: RequestContext
) -> LoginResult:
    """Complete the link-conflict path: verify the account password, THEN
    create the ``OidcAccount`` row and log the user in.

    Wrong password / invalid or expired ticket both yield the uniform
    :class:`errors.InvalidCredentialsError` — the same enumeration-safety
    posture as ``auth_service.login`` (never reveal which part failed)."""

    try:
        claims = jwt_infra.decode_oauth_link_ticket_token(ticket)
    except jwt_infra.InvalidTokenError as exc:
        raise errors.InvalidCredentialsError() from exc

    user = await user_service.get_by_id(session, claims.user_id)
    if user is None or user.password_hash is None:
        raise errors.InvalidCredentialsError()
    if not verify_password(password, user.password_hash):
        raise errors.InvalidCredentialsError()

    existing_link = await _find_link(
        session, provider=claims.provider, provider_user_id=claims.provider_user_id
    )
    if existing_link is None:
        session.add(
            OidcAccount(
                user_id=user.id,
                provider=claims.provider,
                provider_user_id=claims.provider_user_id,
                extra_claims={"name": claims.name},
            )
        )
        await write_audit(
            session,
            action="auth.oauth_linked",
            resource_type="user",
            resource_id=user.id,
            context=_audit_ctx(ctx, actor_id=user.id),
            after={"provider": claims.provider},
        )
        await _notify_oauth_linked(session, user=user, provider=claims.provider)
        await session.flush()

    return await _finalize_login(session, user=user, ctx=ctx)
