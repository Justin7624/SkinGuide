# services/api/app/routes_admin_users.py

from __future__ import annotations

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session as OrmSession

from .db import get_db
from . import models
from .admin_auth import hash_password
from .security import require_role
from .audit import log_audit

router = APIRouter(prefix="/v1/admin/users", tags=["admin-users"], dependencies=[Depends(require_role("admin"))])

class UserRow(BaseModel):
    id: int
    email: str
    role: str
    is_active: bool
    created_at: str
    last_login_at: str | None = None

class CreateUserReq(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10)
    role: str = Field(default="viewer")  # viewer|labeler|admin

class UpdateUserReq(BaseModel):
    role: str | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=10)

@router.get("", response_model=list[UserRow])
def list_users(db: OrmSession = Depends(get_db)):
    rows = db.query(models.AdminUser).order_by(models.AdminUser.id.asc()).all()
    return [
        UserRow(
            id=u.id,
            email=u.email,
            role=u.role,
            is_active=bool(u.is_active),
            created_at=u.created_at.isoformat(),
            last_login_at=u.last_login_at.isoformat() if u.last_login_at else None,
        )
        for u in rows
    ]

@router.post("", response_model=UserRow)
def create_user(payload: CreateUserReq, request: Request, db: OrmSession = Depends(get_db)):
    email = str(payload.email).lower()
    if db.query(models.AdminUser).filter(models.AdminUser.email == email).first():
        raise HTTPException(409, "Email exists")

    role = payload.role if payload.role in ("viewer", "labeler", "admin") else "viewer"
    u = models.AdminUser(
        email=email,
        password_hash=hash_password(payload.password),
        role=role,
        is_active=True,
        created_at=datetime.utcnow(),
    )
    db.add(u)
    log_audit(db, event_type="admin_user_created", session_id=None, request=request, payload={})
    db.commit()

    return UserRow(
        id=u.id,
        email=u.email,
        role=u.role,
        is_active=bool(u.is_active),
        created_at=u.created_at.isoformat(),
        last_login_at=None,
    )

@router.patch("/{user_id}", response_model=UserRow)
def update_user(user_id: int, payload: UpdateUserReq, request: Request, db: OrmSession = Depends(get_db)):
    u = db.get(models.AdminUser, int(user_id))
    if not u:
        raise HTTPException(404, "Not found")

    if payload.role is not None:
        if payload.role not in ("viewer", "labeler", "admin"):
            raise HTTPException(400, "Bad role")
        u.role = payload.role

    if payload.is_active is not None:
        u.is_active = bool(payload.is_active)

    if payload.password is not None and payload.password.strip():
        u.password_hash = hash_password(payload.password)

    log_audit(db, event_type="admin_user_updated", session_id=None, request=request, payload={})
    db.commit()

    return UserRow(
        id=u.id,
        email=u.email,
        role=u.role,
        is_active=bool(u.is_active),
        created_at=u.created_at.isoformat(),
        last_login_at=u.last_login_at.isoformat() if u.last_login_at else None,
    )
