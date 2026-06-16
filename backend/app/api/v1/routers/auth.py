from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies.auth import get_current_user
from app.infra.database.models import User
from app.infra.database.session import get_db
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserView
from app.services.auth_service import login_user, register_user

router = APIRouter()


@router.post("/register", response_model=UserView, status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> User:
    return register_user(db, payload)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    return login_user(db, payload)


@router.get("/me", response_model=UserView)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
