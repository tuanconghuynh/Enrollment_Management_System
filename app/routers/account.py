# app/routers/account.py
from pathlib import Path
from datetime import datetime, timezone, date

from fastapi import APIRouter, Depends, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.routers.auth import require_user as require_login
from app.core.security import verify_password, hash_password

router = APIRouter()

# Trỏ thư mục template: <repo>/web
ROOT_DIR = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(ROOT_DIR / "web"))

# ---------------- Flash helpers ----------------
def _flash(request: Request, msg: str, level: str = "info"):
    """Đặt flash message (lưu trong session; đọc một lần)"""
    request.session["_flash"] = {"message": msg, "level": level}

def _pop_flash(request: Request):
    """Lấy và xóa flash trong session"""
    return request.session.pop("_flash", None)

# ---------------- Views ----------------
@router.get("/account")
def account_view(
    request: Request,
    me: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    """Trang thông tin tài khoản + form đổi mật khẩu.
    UI sẽ tự hiển thị nhắc đổi mật khẩu (không dùng flash ở BE)."""
    flash = _pop_flash(request)  # chỉ dùng cho các thông báo thật sự (lỗi/success)
    first = request.query_params.get("first") == "1"

    return templates.TemplateResponse(
        "account.html",
        {
            "request": request,
            "me": me,
            "flash": flash,  # có thể None
            # cờ 'first' để JS giao diện tự mở form/hiện nhắc
            "first": first,
            # (tuỳ chọn) truyền thêm cờ must_change_password để UI quyết định
            "must_change_password": bool(getattr(me, "must_change_password", False)),
        },
    )

@router.post("/account/change-password")
def account_change_password(
    request: Request,
    old_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    me: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    """Đổi mật khẩu tài khoản hiện tại"""
    # Validate cơ bản
    if len(new_password) < 6:
        _flash(request, "Mật khẩu mới tối thiểu 6 ký tự!", "error")
        return RedirectResponse(url="/account", status_code=302)
    if new_password != confirm_password:
        _flash(request, "Xác nhận mật khẩu không khớp!", "error")
        return RedirectResponse(url="/account", status_code=302)
    if not verify_password(old_password, me.password_hash):
        _flash(request, "Mật khẩu hiện tại không đúng!", "error")
        return RedirectResponse(url="/account", status_code=302)

    # 🛑 Không cho trùng mật khẩu mặc định sau reset
    # - Nếu reset_password_hash có giá trị -> dùng nó
    # - Nếu chưa có mà user vẫn đang ở trạng thái "vừa reset" (must_change_password=1
    #   và chưa từng đổi password) -> fallback dùng password_hash hiện tại
    reset_hash = getattr(me, "reset_password_hash", None)
    if not reset_hash and getattr(me, "must_change_password", False) and not getattr(me, "password_changed_at", None):
        reset_hash = me.password_hash  # fallback an toàn cho dữ liệu cũ chưa populate

    if reset_hash:
        try:
            if verify_password(new_password, reset_hash):
                _flash(
                    request,
                    "Mật khẩu mới không được trùng với mật khẩu cũ!",
                    "error",
                )
                return RedirectResponse(url="/account", status_code=302)
        except Exception:
            pass  # hash rỗng/hỏng -> bỏ qua check thay vì crash

    # Lưu DB
    try:
        me.password_hash = hash_password(new_password)
        me.must_change_password = False
        me.password_changed_at = datetime.now(timezone.utc)
        # ❗ KHÔNG xóa reset_password_hash: tiếp tục cấm dùng lại mật khẩu reset cũ
        db.commit()

        # Đồng bộ session
        request.session["must_change_password"] = False

        _flash(request, "Đổi mật khẩu thành công!", "success")
    except Exception:
        db.rollback()
        _flash(request, "Không thể đổi mật khẩu. Vui lòng thử lại!", "error")

    return RedirectResponse(url="/account", status_code=302)

@router.post("/account/profile")
def account_update_profile(
    request: Request,
    full_name: str = Form(""),
    email: str = Form(""),
    dob: str = Form(""),
    me: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    """Cập nhật thông tin hồ sơ: họ tên, email, ngày sinh"""
    # Chuẩn hóa & kiểm tra unique email
    email_norm = (email or "").strip() or None
    if email_norm:
        dup = db.query(User).filter(User.email == email_norm, User.id != me.id).first()
        if dup:
            _flash(request, "Email đã được dùng bởi tài khoản khác.", "error")
            return RedirectResponse(url="/account", status_code=302)

    # Parse DOB nếu có (YYYY-MM-DD)
    dob_val = None
    if dob:
        try:
            dob_val = date.fromisoformat(dob)
        except ValueError:
            _flash(request, "Ngày sinh không hợp lệ!", "error")
            return RedirectResponse(url="/account", status_code=302)

    # Lưu DB
    try:
        me.full_name = (full_name or "").strip() or None
        me.email = email_norm
        me.dob = dob_val
        db.commit()
        _flash(request, "Cập nhật thông tin tài khoản thành công!", "success")
    except Exception:
        db.rollback()
        _flash(request, "Không cập nhật được thông tin, vui lòng thử lại!", "error")

    return RedirectResponse(url="/account", status_code=302)
