# app/routers/auth.py
import time
from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN

from app.db.session import get_db
from app.models.user import User
from app.core.security import verify_password, hash_password, try_rehash_on_success

router = APIRouter()

# Idle timeout: 1 giờ (đồng bộ với main.py)
IDLE_TIMEOUT_SEC = 1 * 60 * 60

def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
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
        raise HTTPException(HTTP_401_UNAUTHORIZED, "Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại!")
    if not user.is_active:
        raise HTTPException(HTTP_403_FORBIDDEN, "User disabled")
    return user

def require_roles(*roles: str):
    def _dep(
        request: Request,
        user: User = Depends(require_user)
    ) -> User:
        if roles and user.role not in roles:
            raise HTTPException(HTTP_403_FORBIDDEN, "Forbidden")

        # Bơm đầy đủ thông tin vào session cho chắc
        s = request.session
        s["uid"] = getattr(user, "id", s.get("uid"))
        s["full_name"] = (
            getattr(user, "full_name", None)
            or getattr(user, "username", None)
            or getattr(user, "email", None)
            or s.get("full_name")
        )
        s["username"] = getattr(user, "username", s.get("username"))
        s["email"]    = getattr(user, "email", s.get("email"))
        s["role"]     = getattr(user, "role", s.get("role"))
        s["must_change_password"] = bool(getattr(user, "must_change_password", False))
        return user
    return _dep

require_admin = require_roles("Admin")

@router.get("/login")
def login_page():
    # Trang HTML login tĩnh
    return RedirectResponse(url="/auth_login.html", status_code=302)

@router.post("/api/login")
@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = (
        db.query(User)
        .filter(or_(User.username == username, User.email == username))
        .first()
    )
    # Xác thực
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if not user.is_active:
        raise HTTPException(HTTP_403_FORBIDDEN, "User disabled")

    # Nâng cấp hash nếu cần (đổi cost/scheme)
    try:
        new_hash = try_rehash_on_success(password, user.password_hash)
        if new_hash:
            user.password_hash = new_hash
    except Exception:
        # không chặn đăng nhập nếu rehash lỗi
        pass

    # Ghi nhận thời điểm đăng nhập
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)

    # Lưu phiên + thông tin để audit dùng ngay
    request.session.clear()
    request.session["uid"] = user.id
    request.session["_last_seen"] = int(time.time())
    request.session["full_name"] = user.full_name or user.username or user.email
    request.session["username"]  = user.username
    request.session["email"]     = user.email
    request.session["role"]      = user.role
    request.session["must_change_password"] = bool(getattr(user, "must_change_password", False))

    # Nếu lần đầu/đã reset → yêu cầu đổi mật khẩu
    must_change = bool(getattr(user, "must_change_password", False))
    is_api = request.url.path.startswith("/api")

    if must_change:
        if is_api:
            return {
                "ok": True,
                "require_change_password": True,
                "redirect": "/account?first=1",
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "full_name": user.full_name,
                    "role": user.role,
                    "is_active": user.is_active,
                },
            }
        # form login HTML → chuyển hướng thẳng
        return RedirectResponse(url="/account?first=1", status_code=302)

    # Đăng nhập bình thường
    if is_api:
        return {
            "ok": True,
            "require_change_password": False,
            "user": {
                "id": user.id,
                "username": user.username,
                "full_name": user.full_name,
                "role": user.role,
                "is_active": user.is_active,
            },
        }
    return RedirectResponse(url="/index_home.html", status_code=302)

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
        "email": user.email,
        "role": user.role,
        "is_active": user.is_active,
        "must_change_password": bool(getattr(user, "must_change_password", False)),
        "last_login_at": user.last_login_at,
        "password_changed_at": getattr(user, "password_changed_at", None),
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
        password_hash=hash_password("VHTPT@hutech123"),
        must_change_password=True,  # bắt đổi sau khi đăng nhập
    )
    db.add(u); db.commit(); db.refresh(u)
    return {"ok": True, "created_user_id": u.id}
