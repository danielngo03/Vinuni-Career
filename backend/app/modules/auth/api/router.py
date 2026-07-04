"""Auth HTTP routes (``/api/v1/auth/*``).

Routers are HTTP-only: they validate input, call the auth service, and shape the
response envelope. All business rules, RBAC, audit, and security-event writes live
in the service layer.
"""

from __future__ import annotations

import urllib.parse

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db_session
from app.modules.auth.api import presenters
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.modules.auth.api.schemas import (
    ActivateAccountRequest,
    ForgotPasswordRequest,
    LoginRequest,
    LoginTotpRequest,
    OAuthExchangeRequest,
    OAuthLinkConfirmRequest,
    RefreshRequest,
    RegisterRequest,
    ResendVerificationRequest,
    ResetPasswordOtpRequest,
    ResetPasswordRequest,
    SwitchIdentityRequest,
    VerifyEmailOtpRequest,
    VerifyEmailRequest,
)
from app.modules.auth.application import auth_service, errors, oauth_service
from app.modules.auth.application.auth_service import LoginChallenge
from app.modules.auth.application.context import context_from_request
from app.modules.auth.infrastructure import jwt as jwt_infra
from app.modules.users.application import user_service
from app.shared.responses import success

router = APIRouter(prefix="/auth", tags=["auth"])

# Refresh tokens are delivered ONLY as an httpOnly cookie scoped to the auth API
# (``docs/SECURITY_PRIVACY.md`` §8). They are never returned in a JSON body and
# never required from frontend localStorage.
_COOKIE_PATH = "/api/v1/auth"


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.auth_refresh_cookie_name,
        value=refresh_token,
        max_age=settings.refresh_cookie_max_age,
        path=_COOKIE_PATH,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite="lax",
    )


def _clear_refresh_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=settings.auth_refresh_cookie_name,
        path=_COOKIE_PATH,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite="lax",
    )


@router.post("/register", status_code=status.HTTP_202_ACCEPTED, summary="Register a local account")
async def register(
    body: RegisterRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await auth_service.register(
        session,
        email=body.email,
        password=body.password,
        full_name=body.full_name,
        locale=body.locale,
        ctx=context_from_request(request),
    )
    return success(result)


@router.post("/verify-email", summary="Verify an email address")
async def verify_email(
    body: VerifyEmailRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    user = await auth_service.verify_email(
        session, token=body.token, ctx=context_from_request(request)
    )
    return success({"email": user.email, "email_verified": user.is_email_verified})


@router.post("/verify-email/otp", summary="Verify email with a 6-digit OTP code")
async def verify_email_otp(
    body: VerifyEmailOtpRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    user = await auth_service.verify_email_otp(
        session,
        email=body.email,
        otp_code=body.otp_code,
        purpose=body.purpose,
        ctx=context_from_request(request),
    )
    return success({"email": user.email, "email_verified": user.is_email_verified})


@router.post("/verify-email/resend", summary="Resend the email-verification link")
async def resend_verification(
    body: ResendVerificationRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await auth_service.resend_verification(
        session, email=body.email, ctx=context_from_request(request)
    )
    return success(result)


@router.post("/activate", summary="Activate a passwordless account (set password + verify)")
async def activate_account(
    body: ActivateAccountRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    user = await auth_service.activate_account(
        session, token=body.token, password=body.password,
        ctx=context_from_request(request),
    )
    return success({"email": user.email, "email_verified": user.is_email_verified})


@router.post("/forgot-password", summary="Request a password-reset email")
async def forgot_password(
    body: ForgotPasswordRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await auth_service.forgot_password(
        session, email=body.email, ctx=context_from_request(request)
    )
    return success(result)


@router.post("/reset-password", summary="Set a new password using a reset token")
async def reset_password(
    body: ResetPasswordRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await auth_service.reset_password(
        session,
        token=body.token,
        password=body.password,
        ctx=context_from_request(request),
    )
    return success({"status": "password_reset"})


@router.post("/reset-password/otp", summary="Set a new password using a reset OTP")
async def reset_password_otp(
    body: ResetPasswordOtpRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await auth_service.reset_password_otp(
        session,
        email=body.email,
        otp_code=body.otp_code,
        password=body.password,
        ctx=context_from_request(request),
    )
    return success({"status": "password_reset"})


@router.post("/login", summary="Email/password login")
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await auth_service.login(
        session,
        email=body.email,
        password=body.password,
        ctx=context_from_request(request),
    )
    # Confirmed-TOTP accounts get a challenge, not tokens: no cookie is set.
    if isinstance(result, LoginChallenge):
        return success(
            {"totp_required": True, "challenge_token": result.challenge_token}
        )
    _set_refresh_cookie(response, result.tokens.refresh_token)
    payload = presenters.tokens_payload(result.tokens)
    payload["user"] = presenters.user_summary(result.user, result.identity)
    return success(payload)


@router.post("/login/totp", summary="Complete a TOTP-gated login")
async def login_totp(
    body: LoginTotpRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await auth_service.login_totp(
        session,
        challenge_token=body.challenge_token,
        code=body.code,
        ctx=context_from_request(request),
    )
    _set_refresh_cookie(response, result.tokens.refresh_token)
    payload = presenters.tokens_payload(result.tokens)
    payload["user"] = presenters.user_summary(result.user, result.identity)
    return success(payload)


@router.post("/refresh", summary="Rotate refresh token")
async def refresh(
    request: Request,
    response: Response,
    body: RefreshRequest | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    # Browser path: the refresh token lives in the httpOnly cookie. The optional
    # JSON body is a fallback for non-browser clients only.
    settings = get_settings()
    refresh_token = request.cookies.get(settings.auth_refresh_cookie_name)
    if not refresh_token and body is not None:
        refresh_token = body.refresh_token
    if not refresh_token:
        raise errors.SessionExpiredError("invalid_refresh")

    tokens = await auth_service.refresh(
        session, refresh_token=refresh_token, ctx=context_from_request(request)
    )
    _set_refresh_cookie(response, tokens.refresh_token)
    return success(presenters.tokens_payload(tokens))


@router.post("/logout", summary="Revoke the current session")
async def logout(
    request: Request,
    response: Response,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await auth_service.logout(
        session,
        principal=auth.principal,
        session_id=auth.claims.session_id,
        jti=auth.claims.jti,
        access_expires_at=auth.claims.expires_at,
        ctx=auth.ctx,
    )
    _clear_refresh_cookie(response)
    return success({"status": "signed_out"})


@router.get("/me", summary="Current user and active identity")
async def me(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    assert auth.principal.user_id is not None
    user = await user_service.get_by_id(session, auth.principal.user_id)
    identity = await user_service.get_identity(
        session, identity_id=auth.claims.identity_id, user_id=auth.principal.user_id
    )
    assert user is not None and identity is not None
    return success(presenters.user_summary(user, identity))


@router.get("/identity", summary="List the user's identities")
async def list_identities(
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    assert auth.principal.user_id is not None
    identities = await user_service.list_identities(session, auth.principal.user_id)
    items = [
        presenters.identity_summary(
            identity, is_active=identity.id == auth.claims.identity_id
        )
        for identity in identities
    ]
    return success(items)


@router.post("/identity", summary="Switch the active identity")
async def switch_identity(
    body: SwitchIdentityRequest,
    response: Response,
    auth: CurrentAuth = Depends(get_current_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    tokens = await auth_service.switch_identity(
        session,
        principal=auth.principal,
        session_id=auth.claims.session_id,
        identity_id=body.identity_id,
        ctx=auth.ctx,
    )
    _set_refresh_cookie(response, tokens.refresh_token)
    return success(presenters.tokens_payload(tokens))


# --------------------------------------------------------------------------- #
# OAuth / OIDC social login (Google / Facebook)                               #
# --------------------------------------------------------------------------- #

_OAUTH_COOKIE_PATH = "/api/v1/auth/oauth"
_OAUTH_NONCE_COOKIE = "vinuni_oauth_nonce"
_OAUTH_NONCE_MAX_AGE = 600


def _oauth_redirect_uri(provider: str) -> str:
    base = get_settings().effective_oauth_redirect_base_url
    return f"{base}/api/v1/auth/oauth/{provider}/callback"


def _set_oauth_nonce_cookie(response: Response, nonce: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=_OAUTH_NONCE_COOKIE,
        value=nonce,
        max_age=_OAUTH_NONCE_MAX_AGE,
        path=_OAUTH_COOKIE_PATH,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite="lax",
    )


def _clear_oauth_nonce_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=_OAUTH_NONCE_COOKIE,
        path=_OAUTH_COOKIE_PATH,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite="lax",
    )


def _frontend_oauth_url(path: str, params: dict[str, str]) -> str:
    settings = get_settings()
    locale = settings.default_locale
    query = urllib.parse.urlencode(params)
    return f"{settings.frontend_url.rstrip('/')}/{locale}/{path.lstrip('/')}?{query}"


@router.get("/oauth/{provider}/start", summary="Start an OAuth login/register flow")
async def oauth_start(
    provider: str,
    mode: str = Query(default="login", pattern="^(login|register)$"),
    return_to: str | None = Query(default=None, max_length=500),
) -> RedirectResponse:
    authorize_url, state, nonce = await oauth_service.start(
        provider=provider,
        mode=mode,
        return_to=return_to,
        redirect_uri=_oauth_redirect_uri(provider),
    )
    resp = RedirectResponse(
        url=f"{authorize_url}", status_code=status.HTTP_302_FOUND
    )
    _set_oauth_nonce_cookie(resp, nonce)
    return resp


@router.get("/oauth/{provider}/callback", summary="OAuth provider callback")
async def oauth_callback(
    provider: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
) -> RedirectResponse:
    resp: RedirectResponse
    try:
        if not code or not state:
            raise errors.InvalidTokenError("oauth_missing_params")

        try:
            state_claims = jwt_infra.decode_oauth_state_token(state)
        except jwt_infra.InvalidTokenError as exc:
            raise errors.InvalidTokenError("oauth_state_invalid") from exc

        cookie_nonce = request.cookies.get(_OAUTH_NONCE_COOKIE)
        if (
            state_claims.provider != provider
            or not cookie_nonce
            or cookie_nonce != state_claims.nonce
        ):
            raise errors.InvalidTokenError("oauth_state_mismatch")

        result = await oauth_service.handle_callback(
            session,
            provider=provider,
            code=code,
            redirect_uri=_oauth_redirect_uri(provider),
            ctx=context_from_request(request),
        )
        if isinstance(result, oauth_service.OAuthLinkConflict):
            url = _frontend_oauth_url(
                "auth/oauth/link-conflict",
                {"ticket": result.ticket, "email": result.email},
            )
        else:
            url = _frontend_oauth_url("auth/oauth/callback", {"ticket": result.ticket})
        resp = RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)
    except errors.AppError:
        # Never leak provider/internal error details in the redirect URL.
        url = _frontend_oauth_url("auth/login", {"error": "oauth_failed"})
        resp = RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)

    _clear_oauth_nonce_cookie(resp)
    return resp


@router.post("/oauth/exchange", summary="Redeem a post-OAuth-callback ticket for a session")
async def oauth_exchange(
    body: OAuthExchangeRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await oauth_service.exchange_ticket(
        session, ticket=body.ticket, ctx=context_from_request(request)
    )
    _set_refresh_cookie(response, result.tokens.refresh_token)
    payload = presenters.tokens_payload(result.tokens)
    payload["user"] = presenters.user_summary(result.user, result.identity)
    return success(payload)


@router.post("/oauth/link-confirm", summary="Confirm linking an OAuth identity with a password")
async def oauth_link_confirm(
    body: OAuthLinkConfirmRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await oauth_service.confirm_link(
        session,
        ticket=body.ticket,
        password=body.password,
        ctx=context_from_request(request),
    )
    _set_refresh_cookie(response, result.tokens.refresh_token)
    payload = presenters.tokens_payload(result.tokens)
    payload["user"] = presenters.user_summary(result.user, result.identity)
    return success(payload)
