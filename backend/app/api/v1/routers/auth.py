from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies.auth import get_current_user
from app.core.config import settings
from app.core.security import hash_password
from app.infra.database.models import User
from app.infra.database.session import get_db
from app.schemas.auth import DemoAccountView, LoginRequest, RegisterRequest, TokenResponse, UserView
from app.services.auth_service import login_user, register_user

router = APIRouter()
DEMO_DATA_DIR = Path(__file__).resolve().parents[4] / ".data" / "demo"
DEMO_PASSWORD = "1"


@router.post("/register", response_model=UserView, status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> User:
    return register_user(db, payload)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    return login_user(db, payload)


@router.get("/me", response_model=UserView)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.post("/demo-accounts", response_model=list[DemoAccountView], status_code=201)
def create_demo_accounts(db: Session = Depends(get_db)) -> list[DemoAccountView]:
    if settings.app_env == "production":
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo account creation is disabled in production",
        )

    accounts: list[DemoAccountView] = []
    accounts.extend(_create_accounts_from_json(db, "students", "student", "student_id"))
    accounts.extend(_create_accounts_from_json(db, "companies", "company", "company_id"))
    db.commit()
    return accounts


def _create_accounts_from_json(
    db: Session,
    folder_name: str,
    prefix: str,
    id_field: str,
) -> list[DemoAccountView]:
    folder = DEMO_DATA_DIR / folder_name
    if not folder.exists():
        return []

    records = []
    for file_path in folder.glob("*.json"):
        with file_path.open(encoding="utf-8") as file:
            payload = json.load(file)
        records.append((file_path, payload))

    accounts: list[DemoAccountView] = []
    for index, (file_path, payload) in enumerate(
        sorted(records, key=lambda record: _demo_sort_key(record[0], record[1], id_field)),
        start=1,
    ):
        account = f"{prefix}_{index}"
        source_id = str(payload.get(id_field, file_path.stem))
        full_name = _demo_display_name(payload, source_id)
        user = db.query(User).filter(User.email == account).first()
        if not user:
            user = User(
                email=account,
                full_name=f"{full_name} ({source_id})",
                password_hash=hash_password(DEMO_PASSWORD),
            )
            db.add(user)
        else:
            user.full_name = f"{full_name} ({source_id})"
            user.password_hash = hash_password(DEMO_PASSWORD)
            user.is_active = True
        accounts.append(DemoAccountView(account=account, password=DEMO_PASSWORD, source_id=source_id))
    return accounts


def _demo_sort_key(file_path: Path, payload: dict, id_field: str) -> tuple[int, int, str]:
    source_id = str(payload.get(id_field, file_path.stem))
    match = re.search(r"(\d+)$", source_id)
    numeric_order = int(match.group(1)) if match else 9999
    demo_order = 0 if "demo" in source_id else 1
    return numeric_order, demo_order, source_id


def _demo_display_name(payload: dict, source_id: str) -> str:
    profile = payload.get("profile")
    if isinstance(profile, dict) and profile.get("full_name"):
        return str(profile["full_name"])
    return str(payload.get("name") or source_id)
