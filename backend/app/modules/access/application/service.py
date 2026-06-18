from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.access.schemas import (
    IdentityView,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserView,
)
from app.platform.database.models import RegistrationApplication, User, UserOrgRole, UserSession
from app.shared.config import settings
from app.shared.enum import OrgType
from app.shared.errors import AppError, ErrorCode
from app.shared.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email, User.deleted_at.is_(None)))


def get_user_by_id(db: Session, user_id: str) -> User | None:
    return db.get(User, user_id)


def register_user(db: Session, payload: RegisterRequest) -> User:
    existing = get_user_by_email(db, payload.email)
    if existing:
        raise AppError(code=ErrorCode.CONFLICT, message="Email already registered", status_code=409)

    user = User(
        email=payload.email,
        full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def login_user(db: Session, payload: LoginRequest) -> TokenResponse:
    user = get_user_by_email(db, payload.email)
    if not user or not verify_password(payload.password, user.password_hash):
        raise AppError(code=ErrorCode.UNAUTHORIZED, message="Invalid credentials", status_code=401)
    if not user.is_active:
        application = db.scalar(
            select(RegistrationApplication)
            .where(RegistrationApplication.user_id == user.id)
            .order_by(RegistrationApplication.submitted_at.desc())
        )
        if application:
            return TokenResponse(
                access_token=create_access_token(
                    user.id,
                    claims={
                        "scope": "registration:pending",
                        "registration_id": application.id,
                    },
                ),
                refresh_token=None,
                user=UserView.model_validate(user),
                identities=[],
                access_scope="registration:pending",
                pending_registration_id=application.id,
            )
        raise AppError(code=ErrorCode.FORBIDDEN, message="User is inactive", status_code=403)

    return _issue_session(db, user, device_info=payload.device_info)


def refresh_user_session(db: Session, payload: RefreshRequest) -> TokenResponse:
    token_hash = hash_refresh_token(payload.refresh_token)
    session = db.scalar(select(UserSession).where(UserSession.refresh_token == token_hash))
    now = datetime.now(UTC)
    if not session:
        raise AppError(
            code=ErrorCode.UNAUTHORIZED, message="Invalid refresh token", status_code=401
        )
    if session.revoked_at is not None:
        _revoke_session_family(db, session.family_id, now)
        db.commit()
        raise AppError(
            code=ErrorCode.UNAUTHORIZED,
            message="Refresh token reuse detected; session family revoked",
            status_code=401,
        )
    if _as_utc(session.expires_at) <= now:
        session.revoked_at = now
        db.commit()
        raise AppError(
            code=ErrorCode.UNAUTHORIZED, message="Invalid refresh token", status_code=401
        )

    user = get_user_by_id(db, session.user_id)
    if not user or not user.is_active or user.deleted_at is not None:
        _revoke_session_family(db, session.family_id, now)
        db.commit()
        raise AppError(
            code=ErrorCode.UNAUTHORIZED, message="Invalid refresh token", status_code=401
        )

    refresh_token = create_refresh_token()
    replacement = UserSession(
        user_id=user.id,
        family_id=session.family_id,
        refresh_token=hash_refresh_token(refresh_token),
        device_info=payload.device_info or session.device_info,
        expires_at=now + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(replacement)
    db.flush()
    session.rotated_at = now
    session.revoked_at = now
    session.replaced_by_id = replacement.id
    db.commit()
    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=refresh_token,
        user=UserView.model_validate(user),
        identities=list_user_identities(db, user.id),
        access_scope="workspace",
    )


def revoke_user_session(db: Session, refresh_token: str) -> None:
    token_hash = hash_refresh_token(refresh_token)
    session = db.scalar(select(UserSession).where(UserSession.refresh_token == token_hash))
    if session:
        _revoke_session_family(db, session.family_id, datetime.now(UTC))
        db.commit()


def get_identity_for_user(db: Session, user_id: str, identity_id: str) -> IdentityView:
    identities = list_user_identities(db, user_id)
    identity = next((item for item in identities if item.id == identity_id), None)
    if not identity:
        raise AppError(
            code=ErrorCode.FORBIDDEN, message="Identity is not available", status_code=403
        )
    return identity


def _issue_session(db: Session, user: User, *, device_info: str | None) -> TokenResponse:
    refresh_token = create_refresh_token()
    db.add(
        UserSession(
            user_id=user.id,
            family_id=create_refresh_token()[:36],
            refresh_token=hash_refresh_token(refresh_token),
            device_info=device_info,
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days),
        )
    )
    db.commit()
    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=refresh_token,
        user=UserView.model_validate(user),
        identities=list_user_identities(db, user.id),
        access_scope="workspace",
    )


def issue_user_session(
    db: Session,
    user: User,
    *,
    device_info: str | None = None,
) -> TokenResponse:
    """Public session issuance boundary for verified authentication methods."""
    return _issue_session(db, user, device_info=device_info)


def _revoke_session_family(db: Session, family_id: str, revoked_at: datetime) -> None:
    sessions = db.scalars(
        select(UserSession).where(
            UserSession.family_id == family_id,
            UserSession.revoked_at.is_(None),
        )
    )
    for item in sessions:
        item.revoked_at = revoked_at


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def list_user_identities(db: Session, user_id: str) -> list[IdentityView]:
    stmt = (
        select(UserOrgRole)
        .where(UserOrgRole.user_id == user_id)
        .join(UserOrgRole.org)
        .join(UserOrgRole.role)
        .order_by(UserOrgRole.id)
    )
    identities: list[IdentityView] = []
    for item in db.scalars(stmt).unique():
        identities.append(
            IdentityView(
                id=item.id,
                org_id=item.org_id,
                org_name=item.org.name,
                org_type=item.org.type.value,
                role_id=item.role_id,
                role_name=item.role.name,
                dept_id=item.dept_id,
                dept_name=item.dept.name if item.dept else None,
                portal=_portal_for_identity(item.org.type, item.role.name),
                redirect_path=_redirect_for_identity(item.org.type, item.role.name),
            )
        )
    return identities


def _portal_for_identity(org_type: OrgType, role_name: str) -> str:
    if org_type == OrgType.UNIVERSITY and role_name == "student":
        return "student"
    if org_type == OrgType.PARTNER:
        return "partner"
    return "university"


def _redirect_for_identity(org_type: OrgType, role_name: str) -> str:
    return f"/{_portal_for_identity(org_type, role_name)}"
