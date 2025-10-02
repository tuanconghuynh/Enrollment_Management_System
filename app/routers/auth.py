# app/routers/auth.py
from typing import Optional
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import JSONResponse
from starlette.responses import RedirectResponse
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN
from sqlalchemy.orm import Session
from passlib.hash import bcrypt

from app.db.session import get_db
from app.models.user import User  # import trực tiếp, không qua __init__

router = APIRouter()

# ===================== Session helpers & guards =====================
def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    uid = request.session.get("uid")
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
    """Dùng: Depends(require_roles("Admin","NhanVien"))"""
    def _dep(user: User = Depends(require_user)) -> User:
        if roles and user.role not in roles:
            raise HTTPException(HTTP_403_FORBIDDEN, "Forbidden")
        return user
    return _dep

require_admin = require_roles("Admin")

# ===================== Pages =====================
@router.get("/login")
def login_page():
    # chuyển thẳng đến file tĩnh web/auth_login.html đã mount ở "/"
    return RedirectResponse(url="/auth_login.html", status_code=302)

# ===================== APIs (có cả alias /api/...) =====================
@router.post("/api/login")
@router.post("/login")  # alias để gọi thẳng /login nếu cần (form POST)
def login(request: Request,
          username: str = Form(...),
          password: str = Form(...),
          db: Session = Depends(get_db)):
    # cho phép username hoặc email
    user = (
        db.query(User)
        .filter((User.username == username) | (User.email == username))
        .first()
    )
    if not user or not bcrypt.verify(password, user.password_hash):
        raise HTTPException(HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if not user.is_active:
        raise HTTPException(HTTP_403_FORBIDDEN, "User disabled")

    request.session["uid"] = user.id
    return {
        "ok": True,
        "user": {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "role": user.role,
            "is_active": user.is_active,
        },
    }

@router.post("/logout")
@router.post("/api/logout")  # alias cho web cũ
def logout(request: Request):
    request.session.clear()
    return {"ok": True}

@router.get("/me")
@router.get("/api/me")  # alias cho web cũ
def me(user: User = Depends(require_user)):
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active,
    }

# ===================== Bootstrap admin (idempotent) =====================
@router.post("/api/init-admin")
def init_admin(db: Session = Depends(get_db)):
    """
    Đảm bảo luôn có tài khoản admin chuẩn:
      - username/email: vhtpt@hutech.edu.vn
      - password:       VHTPT@hutech123
      - role:           Admin
      - is_active:      True
    Nếu đã tồn tại → reset mật khẩu + bật active + set role.
    Nếu chưa có  → tạo mới.
    """
    username = "vhtpt@hutech.edu.vn"
    pwd = "VHTPT@hutech123"

    u = db.query(User).filter((User.username == username) | (User.email == username)).first()
    if u:
        u.password_hash = bcrypt.hash(pwd)
        u.is_active = True
        u.role = "Admin"
        if not u.email:
            u.email = username
        if not u.full_name:
            u.full_name = "V-HT.PTĐT"
        db.commit()
        db.refresh(u)
        return {"ok": True, "mode": "updated", "id": u.id}
    else:
        u = User(
            username=username,
            email=username,
            full_name="V-HT.PTĐT",
            role="Admin",
            is_active=True,
            password_hash=bcrypt.hash(pwd),
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return {"ok": True, "mode": "created", "id": u.id}
# ===================== Thay đổi mật khẩu =====================