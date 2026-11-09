from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.errors import ApiError
from app.models import Clinic, User
from app.ratelimit import limiter
from app.security import CurrentUser, create_token, hash_password, verify_password
from app.services.demo_data import create_demo_clinic, purge_expired_demo_clinics

router = APIRouter(prefix="/api/auth", tags=["auth"])
Db = Annotated[Session, Depends(get_db)]


class RegisterIn(BaseModel):
    clinic_name: str = Field(min_length=2, max_length=120)
    name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    id: str
    name: str
    email: str
    is_demo: bool
    clinic_id: str
    clinic_name: str
    clinic_slug: str


class SessionOut(BaseModel):
    token: str
    user: UserOut


def _out(db: Session, user: User) -> UserOut:
    clinic = db.get(Clinic, user.clinic_id)
    assert clinic is not None
    return UserOut(
        id=user.id,
        name=user.name,
        email=user.email,
        is_demo=user.is_demo,
        clinic_id=clinic.id,
        clinic_name=clinic.name,
        clinic_slug=clinic.slug,
    )


@router.post("/register", status_code=201)
def register(body: RegisterIn, db: Db) -> SessionOut:
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise ApiError(409, "email_taken", "An account with this email already exists")
    clinic = Clinic(name=body.clinic_name.strip())
    db.add(clinic)
    db.flush()
    user = User(clinic_id=clinic.id, email=email, name=body.name.strip(), password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    return SessionOut(token=create_token(user.id), user=_out(db, user))


@router.post("/login")
def login(body: LoginIn, db: Db) -> SessionOut:
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if not user or user.is_demo or not verify_password(body.password, user.password_hash):
        raise ApiError(401, "invalid_credentials", "Email or password is incorrect")
    return SessionOut(token=create_token(user.id), user=_out(db, user))


@router.post("/demo")
def demo(request: Request, db: Db) -> SessionOut:
    """One-click demo: a fresh fictional clinic per click (isolated from other visitors), deleted after 24 h."""
    ip = request.client.host if request.client else "unknown"
    limiter.hit("demo", ip, limit=20)
    purge_expired_demo_clinics(db)
    user = create_demo_clinic(db, ZoneInfo(get_settings().timezone))
    return SessionOut(token=create_token(user.id), user=_out(db, user))


@router.get("/me")
def me(user: CurrentUser, db: Db) -> UserOut:
    return _out(db, user)
