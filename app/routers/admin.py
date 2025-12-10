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
from app.routers.auth import require_admin
from app.core.security import hash_password
from starlette.status import HTTP_403_FORBIDDEN  # Import status code for Forbidden

router = APIRouter()

# == CHỈNH LẠI TEMPLATE PATH ĐÚNG ==
BASE_DIR = Path(__file__).resolve().parents[1]  # .../app
WEB_TEMPLATES_DIR = BASE_DIR / "templates" / "web"
templates = Jinja2Templates(directory=str(WEB_TEMPLATES_DIR))
# ==================================

VALID_ROLES = {"Admin", "NhanVien", "CongTacVien", "Manager"}

# ---------- helper tách tên Việt ----------
def _split_vn(fullname: str):
    s = " ".join((fullname or "").split())
    if not s:
        return "", ""
    parts = s.split(" ")
    if len(parts) == 1:
        # không rõ họ/đệm -> để vào first_name (tên gọi)
        return "", parts[0]
    return " ".join(parts[:-1]), parts[-1]
# -----------------------------------------

@router.get("/admin")
def admin_index(
    request: Request,
    me: User = Depends(require_admin),  # Kiểm tra nếu người dùng là Admin
    db: Session = Depends(get_db),
):
    # Nếu người dùng có quyền Manager, chuyển hướng về trang chủ
    if me.role == "Manager":
        return RedirectResponse(url="/ams_home.html", status_code=302)  # Chuyển hướng nếu là Manager

    # Tiến hành truy vấn danh sách người dùng nếu là Admin
    users = db.query(User).order_by(User.id.desc()).all()
    return templates.TemplateResponse(
        "admin_ams.html",
        {
            "request": request,
            "users": users,
            "me": me,
            "active_page": "admin",  # Để layout_ams.html tô màu menu Admin
        },
    )

@router.post("/admin/users/create")
def admin_create_user(
    username: str = Form(...),
    password: str = Form(...),
    # ===== mới: form ưu tiên họ+tên =====
    last_name: str = Form("", alias="last_name"),
    first_name: str = Form("", alias="first_name"),
    # ===== cũ: full_name để tương thích =====
    full_name: str = Form(""),
    email: str = Form(""),
    role: str = Form("NhanVien"),
    dob: Optional[str] = Form(None),  # YYYY-MM-DD
    me: User = Depends(require_admin),  # Kiểm tra quyền Admin
    db: Session = Depends(get_db),
):
    # Chỉ cho phép Admin tạo người dùng
    if me.role == "Manager":
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Bạn không có quyền tạo người dùng.")  # Manager không thể tạo người dùng

    username = (username or "").strip()
    email = (email or "").strip() or None
    role = (role or "NhanVien").strip()

    if not username:
        raise HTTPException(400, "Username không được để trống")
    if len(password) < 6:
        raise HTTPException(400, "Mật khẩu tối thiểu 6 ký tự")
    if role not in VALID_ROLES:
        raise HTTPException(400, f"Role không hợp lệ. Hợp lệ: {', '.join(sorted(VALID_ROLES))}")

    # Chuẩn tên
    ln = (last_name or "").strip()
    fn = (first_name or "").strip()
    if not (ln or fn):
        # fallback từ full_name
        ln, fn = _split_vn(full_name)

    display = (" ".join([ln, fn])).strip() or None

    # Check trùng username/email (chỉ thêm điều kiện email khi có email)
    conds = [User.username == username]
    if email:
        conds.append(User.email == email)
    exists = db.query(User).filter(or_(*conds)).first()
    if exists:
        raise HTTPException(400, "Username/Email đã tồn tại")

    # Parse dob nếu có
    dob_val = None
    if dob:
        try:
            dob_val = date.fromisoformat(dob)
        except ValueError:
            raise HTTPException(400, "Ngày sinh không hợp lệ (định dạng YYYY-MM-DD)")

    try:
        u = User(
            username=username,
            email=email,
            role=role,
            is_active=True,
            password_hash=hash_password(password),
            must_change_password=True, # Đổi mk lần đầu đăng nhập
            dob=dob_val,
            last_name=ln or None,
            first_name=fn or None,
            full_name=display,
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
    # ===== mới: form ưu tiên họ+tên =====
    last_name: str = Form("", alias="last_name"),
    first_name: str = Form("", alias="first_name"),
    # ===== cũ: full_name để tương thích =====
    full_name: str = Form(""),
    email: str = Form(""),
    dob: Optional[str] = Form(None),
    role: str = Form(...),
    is_active: Optional[str] = Form(None),  # "on" hoặc None nếu dùng checkbox
    me: User = Depends(require_admin),  # Kiểm tra quyền Admin
    db: Session = Depends(get_db),
):
    # Chỉ cho phép Admin cập nhật người dùng
    if me.role == "Manager":
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Bạn không có quyền cập nhật người dùng.")  # Manager không thể cập nhật người dùng

    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")

    if u.id == me.id and role != u.role:
        raise HTTPException(400, "Không thể thay đổi quyền của tài khoản đang đăng nhập")
    if role not in VALID_ROLES:
        raise HTTPException(400, f"Role không hợp lệ ({', '.join(sorted(VALID_ROLES))})")

    email = (email or "").strip() or None
    if email:
        dup = db.query(User).filter(User.email == email, User.id != u.id).first()
        if dup:
            raise HTTPException(400, "Email đã được dùng bởi tài khoản khác")

    dob_val = None
    if dob:
        try:
            dob_val = date.fromisoformat(dob)
        except ValueError:
            raise HTTPException(400, "Ngày sinh không hợp lệ (định dạng YYYY-MM-DD)")

    # Chuẩn tên
    ln = (last_name or "").strip()
    fn = (first_name or "").strip()
    if not (ln or fn):
        ln, fn = _split_vn(full_name)

    display = (" ".join([ln, fn])).strip() or None

    try:
        u.last_name = ln or None
        u.first_name = fn or None
        u.full_name = display

        u.email = email
        u.dob = dob_val
        u.role = role
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
    # Chỉ cho phép Admin thực hiện thao tác này
    if me.role == "Manager":
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Bạn không có quyền thay đổi trạng thái người dùng.")  # Manager không thể thay đổi trạng thái người dùng

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
    # Chỉ cho phép Admin thực hiện thao tác này
    if me.role == "Manager":
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Bạn không có quyền reset mật khẩu người dùng.")  # Manager không thể reset mật khẩu

    if len(new_password) < 6:
        raise HTTPException(400, "Mật khẩu tối thiểu 6 ký tự")
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    try:
        new_hash = hash_password(new_password)
        # Lưu cả password_hash và reset_password_hash để tránh người dùng đổi lại mật khẩu
        u.password_hash = new_hash
        u.reset_password_hash = new_hash
        u.must_change_password = True
        u.password_changed_at = None
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "Không đặt lại được mật khẩu.")
    return RedirectResponse(url="/admin", status_code=302)
