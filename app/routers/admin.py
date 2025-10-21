# app/routers/admin.py
from pathlib import Path
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.db.session import get_db
from app.models.user import User
from app.routers.auth import require_admin  # guard Admin
from app.core.security import hash_password  # dùng context chung

router = APIRouter()

# === Trỏ đúng thư mục template: <repo>/web ===
ROOT_DIR = Path(__file__).resolve().parents[2]   # .../Project_AdmissionCheck
templates = Jinja2Templates(directory=str(ROOT_DIR / "web"))

VALID_ROLES = {"Admin", "NhanVien", "CongTacVien"}

@router.get("/admin")
def admin_index(
    request: Request,
    me: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    users = db.query(User).order_by(User.id.desc()).all()
    return templates.TemplateResponse(
        "admin_index.html",
        {"request": request, "users": users, "me": me}
    )

@router.post("/admin/users/create")
def admin_create_user(
    username: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(""),
    email: str = Form(""),
    role: str = Form("NhanVien"),
    dob: Optional[str] = Form(None),  # <-- thêm ngày sinh (YYYY-MM-DD)
    me: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    username = (username or "").strip()
    email = (email or "").strip() or None
    full_name = (full_name or "").strip() or None
    role = (role or "NhanVien").strip()

    if not username:
        raise HTTPException(400, "Username không được để trống")
    if len(password) < 6:
        raise HTTPException(400, "Mật khẩu tối thiểu 6 ký tự")
    if role not in VALID_ROLES:
        raise HTTPException(400, f"Role không hợp lệ. Hợp lệ: {', '.join(sorted(VALID_ROLES))}")

    # username hoặc email trùng
    exists = db.query(User).filter(or_(User.username == username, User.email == email)).first()
    if exists:
        raise HTTPException(400, "Username/Email đã tồn tại")

    # Parse dob nếu có
    dob_val = None
    if dob:
        try:
            dob_val = date.fromisoformat(dob)  # expecting YYYY-MM-DD
        except ValueError:
            raise HTTPException(400, "Ngày sinh không hợp lệ (định dạng YYYY-MM-DD)")

    try:
        u = User(
            username=username,
            email=email,
            full_name=full_name,
            role=role,
            is_active=True,
            password_hash=hash_password(password),
            must_change_password=True,   # ép đổi mật khẩu lần đầu
            dob=dob_val,
        )
        db.add(u)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "Không tạo được người dùng, vui lòng thử lại.")
    return RedirectResponse(url="/admin", status_code=302)


@router.post("/admin/users/update")
def admin_update_user(
    user_id: int = Form(...),
    full_name: str = Form(""),
    email: str = Form(""),
    dob: Optional[str] = Form(None),
    role: str = Form(...),
    is_active: Optional[str] = Form(None),  # "on" hoặc None nếu dùng checkbox
    me: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")

    # Không cho tự hạ quyền chính mình (tránh khoá quyền Admin)
    if u.id == me.id and role != u.role:
        raise HTTPException(400, "Không thể thay đổi quyền của tài khoản đang đăng nhập")

    # Validate role
    if role not in VALID_ROLES:
        raise HTTPException(400, f"Role không hợp lệ ({', '.join(sorted(VALID_ROLES))})")

    # Email trùng người khác?
    email = (email or "").strip() or None
    if email:
        dup = db.query(User).filter(User.email == email, User.id != u.id).first()
        if dup:
            raise HTTPException(400, "Email đã được dùng bởi tài khoản khác")

    # Parse dob (YYYY-MM-DD) nếu có
    dob_val = None
    if dob:
        try:
            dob_val = date.fromisoformat(dob)
        except ValueError:
            raise HTTPException(400, "Ngày sinh không hợp lệ (định dạng YYYY-MM-DD)")

    try:
        u.full_name = (full_name or "").strip() or None
        u.email = email
        u.dob = dob_val
        u.role = role
        # is_active: nếu có checkbox, giá trị "on" -> True, else False
        if is_active is not None:
            u.is_active = bool(is_active == "on")

        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "Không cập nhật được người dùng")
    return RedirectResponse(url="/admin", status_code=302)

@router.post("/admin/users/toggle")
def admin_toggle_user(
    user_id: int = Form(...),
    me: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    if u.id == me.id:
        raise HTTPException(400, "Không thể tự khoá tài khoản của bạn")
    try:
        u.is_active = not bool(u.is_active)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "Không cập nhật được trạng thái người dùng.")
    return RedirectResponse(url="/admin", status_code=302)

@router.post("/admin/users/reset-pass")
def admin_reset_pass(
    user_id: int = Form(...),
    new_password: str = Form(...),
    me: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if len(new_password) < 6:
        raise HTTPException(400, "Mật khẩu tối thiểu 6 ký tự")
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    try:
        u.password_hash = hash_password(new_password)
        u.must_change_password = True
        u.password_changed_at = None
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "Không đặt lại được mật khẩu.")
    return RedirectResponse(url="/admin", status_code=302)
