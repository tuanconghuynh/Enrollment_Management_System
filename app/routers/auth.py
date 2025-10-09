# app/routers/auth.py
import time
from typing import Optional
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from sqlalchemy.orm import Session
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN
from passlib.hash import bcrypt
from app.db.session import get_db
from app.models.user import User
from starlette.responses import RedirectResponse
from app.core.security import verify_password, hash_password

router = APIRouter()

IDLE_TIMEOUT_SEC = 3 * 60 * 60   # 3 giờ

def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    # IDLE TIMEOUT CHECK (3h không hoạt động)
    sess = request.session
    now = int(time.time())
    last = int(sess.get("_last_seen") or 0)
    if last and (now - last) > IDLE_TIMEOUT_SEC:
        sess.clear()
        return None
    # cập nhật mốc hoạt động cuối
    sess["_last_seen"] = now

    uid = sess.get("uid")
    if not uid:
        return None
    return db.get(User, uid)

def require_user(user: Optional[User] = Depends(get_current_user)) -> User:
    if not user:
        raise HTTPException(HTTP_401_UNAUTHORIZED, "Not authenticated")
    if not user.is_active:
        raise HTTPException(HTTP_403_FORBIDDEN, "User disabled")
    return user

def require_roles(*roles: str):
    def _dep(user: User = Depends(require_user)) -> User:
        if roles and user.role not in roles:
            raise HTTPException(HTTP_403_FORBIDDEN, "Forbidden")
        return user
    return _dep

require_admin = require_roles("Admin")

@router.get("/login")
def login_page():
    return RedirectResponse(url="/auth_login.html", status_code=302)

@router.post("/api/login")
@router.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = (
        db.query(User)
        .filter((User.username == username) | (User.email == username))
        .first()
    )
    if not user or not bcrypt.verify(password, user.password_hash):
        raise HTTPException(HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if not user.is_active:
        raise HTTPException(HTTP_403_FORBIDDEN, "User disabled")

    request.session.clear()
    request.session["uid"] = user.id
    request.session["_last_seen"] = int(time.time())
    return {"ok": True, "user": {
        "id": user.id, "username": user.username, "full_name": user.full_name,
        "role": user.role, "is_active": user.is_active
    }}

@router.post("/logout")
@router.post("/api/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}

@router.get("/me")
@router.get("/api/me")
def me(user: User = Depends(require_user)):
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active,
    }

@router.post("/api/init-admin")
def init_admin(db: Session = Depends(get_db)):
    if db.query(User).count() > 0:
        raise HTTPException(status_code=400, detail="Already initialized")
    u = User(
        username="vhtpt@hutech.edu.vn",
        email="vhtpt@hutech.edu.vn",
        full_name="V-HT.PTĐT",
        role="Admin",
        is_active=True,
        password_hash=bcrypt.hash("VHTPT@hutech123"),
    )
    db.add(u); db.commit(); db.refresh(u)
    return {"ok": True, "created_user_id": u.id}
