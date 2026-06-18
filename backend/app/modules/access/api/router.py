from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.modules.access.api.auth import get_current_user
from app.modules.access.application.service import (
    get_identity_for_user,
    list_user_identities,
    login_user,
    refresh_user_session,
    register_user,
    revoke_user_session,
)
from app.modules.access.infrastructure.oidc import (
    authorization_url,
    complete_oidc_login,
    configured_providers,
    exchange_login_ticket,
)
from app.modules.access.schemas import (
    IdentitySelectionRequest,
    IdentityView,
    LoginRequest,
    LogoutRequest,
    OIDCExchangeRequest,
    OIDCProviderStatus,
    RefreshRequest,
    RegisterRequest,
    SessionView,
    TokenResponse,
    UserView,
)
from app.platform.database.models import User
from app.platform.database.session import get_db
from app.shared.config import settings
from app.shared.schemas import APIMessage

router = APIRouter()


@router.get("/oidc/providers", response_model=OIDCProviderStatus)
def oidc_providers() -> dict[str, bool]:
    return configured_providers()


@router.get("/oidc/{provider}/authorize", response_class=RedirectResponse)
def oidc_authorize(provider: str) -> RedirectResponse:
    return RedirectResponse(authorization_url(provider), status_code=302)


@router.get("/oidc/{provider}/callback", response_class=RedirectResponse)
def oidc_callback(
    provider: str,
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    ticket = complete_oidc_login(db, provider=provider, code=code, state=state)
    separator = "&" if "?" in settings.oidc_frontend_callback_url else "?"
    return RedirectResponse(
        f"{settings.oidc_frontend_callback_url}{separator}ticket={ticket}",
        status_code=302,
    )


@router.post("/oidc/exchange", response_model=TokenResponse)
def oidc_exchange(
    payload: OIDCExchangeRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    return exchange_login_ticket(
        db,
        payload.ticket,
        device_info=payload.device_info,
    )


@router.post("/register", response_model=UserView, status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> User:
    return register_user(db, payload)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    return login_user(db, payload)


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    return refresh_user_session(db, payload)


@router.post("/logout", response_model=APIMessage)
def logout(payload: LogoutRequest, db: Session = Depends(get_db)) -> APIMessage:
    revoke_user_session(db, payload.refresh_token)
    return APIMessage(message="Signed out")


@router.get("/me", response_model=UserView)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.get("/identities", response_model=list[IdentityView])
def identities(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[IdentityView]:
    return list_user_identities(db, current_user.id)


@router.get("/session", response_model=SessionView)
def session(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SessionView:
    return SessionView(
        user=UserView.model_validate(current_user),
        identities=list_user_identities(db, current_user.id),
    )


@router.post("/identity", response_model=IdentityView)
def select_identity(
    payload: IdentitySelectionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IdentityView:
    return get_identity_for_user(db, current_user.id, payload.identity_id)
