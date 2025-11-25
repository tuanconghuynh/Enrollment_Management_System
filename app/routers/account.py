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

BASE_DIR = Path(__file__).resolve().parents[1]      # .../app
WEB_TEMPLATES_DIR = BASE_DIR / "templates" / "web"
templates = Jinja2Templates(directory=str(WEB_TEMPLATES_DIR))

def _flash(request: Request, msg: str, level: str = "info"):
    request.session["_flash"] = {"message": msg, "level": level}

def _pop_flash(request: Request):
    return request.session.pop("_flash", None)

# ---- helper tách tên Việt ----
def _split_vn(fullname: str):
    s = " ".join((fullname or "").split())
    if not s:
        return "", ""
    parts = s.split(" ")
    if len(parts) == 1:
        # Không rõ họ/đệm -> để vào first_name (tên gọi) cho dễ xưng hô/sort
        return "", parts[0]
    return " ".join(parts[:-1]), parts[-1]

@router.get("/account")
def account_view(
    request: Request,
    me: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    flash = _pop_flash(request)
    first = request.query_params.get("first") == "1"

    return templates.TemplateResponse(
        "account.html",
        {
            "request": request,
            "me": me,
            "flash": flash,
            "first": first,
            "must_change_password": bool(getattr(me, "must_change_password", False)),
        },
    )

@router.post("/account/change-password")
def account_change_password(
    request: Request,
    old_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    # 🆕 nếu FE muốn chỉ định nơi quay về (optional)
    next: str | None = Form(None),
    me: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    # Ghi lại trạng thái TRƯỚC khi đổi để biết có phải đang bị ép đổi lần đầu không
    must_change_flag = bool(getattr(me, "must_change_password", False))
    first_time_change = not bool(getattr(me, "password_changed_at", None))

    if len(new_password) < 6:
        _flash(request, "Mật khẩu mới tối thiểu 6 ký tự!", "error")
        return RedirectResponse(url="/account", status_code=302)
    if new_password != confirm_password:
        _flash(request, "Xác nhận mật khẩu không khớp!", "error")
        return RedirectResponse(url="/account", status_code=302)
    if not verify_password(old_password, me.password_hash):
        _flash(request, "Mật khẩu hiện tại không đúng!", "error")
        return RedirectResponse(url="/account", status_code=302)

    # Không cho dùng lại mật khẩu cũ (hoặc mật khẩu trước khi reset)
    reset_hash = getattr(me, "reset_password_hash", None)
    if not reset_hash and getattr(me, "must_change_password", False) and not getattr(me, "password_changed_at", None):
        reset_hash = me.password_hash

    if reset_hash:
        try:
            if verify_password(new_password, reset_hash):
                _flash(request, "Mật khẩu mới không được trùng với mật khẩu cũ!", "error")
                return RedirectResponse(url="/account", status_code=302)
        except Exception:
            pass

    try:
        me.password_hash = hash_password(new_password)
        me.must_change_password = False
        me.password_changed_at = datetime.now(timezone.utc)
        db.commit()
        request.session["must_change_password"] = False
        _flash(request, "Đổi mật khẩu thành công!", "success")
    except Exception:
        db.rollback()
        _flash(request, "Không thể đổi mật khẩu. Vui lòng thử lại!", "error")
        return RedirectResponse(url="/account", status_code=302)

    # 🧭 Xác định nơi redirect sau khi đổi thành công
    # Ưu tiên: nếu form gửi lên next -> đi theo next
    if next:
        target = next
    # Nếu đang trong trạng thái "bị ép đổi lần đầu" -> cho về thẳng trang chủ AMS
    elif must_change_flag or first_time_change:
        target = "/ams_home.html"
    # Còn lại: quay về trang account như cũ
    else:
        target = "/account"

    return RedirectResponse(url=target, status_code=302)

# ========= Cập nhật hồ sơ: hỗ trợ tên tách đôi & tương thích full_name =========
@router.post("/account/profile")
def account_update_profile(
    request: Request,
    # Form mới (ưu tiên): last_name = họ+đệm, first_name = tên
    last_name: str = Form("", alias="last_name"),
    first_name: str = Form("", alias="first_name"),
    # Form cũ (tương thích): full_name
    full_name: str = Form(""),
    email: str = Form(""),
    dob: str = Form(""),
    me: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    """
    Cập nhật thông tin hồ sơ:
    - Ưu tiên nhận last_name/first_name.
    - Nếu không có, nhận full_name và tự tách -> last_name/first_name.
    - Vẫn ghi 'full_name' (tạm thời) để tương thích chỗ cũ.
    """
    # Chuẩn hóa email & unique check
    email_norm = (email or "").strip() or None
    if email_norm:
        dup = db.query(User).filter(User.email == email_norm, User.id != me.id).first()
        if dup:
            _flash(request, "Email đã được dùng bởi tài khoản khác.", "error")
            return RedirectResponse(url="/account", status_code=302)

    # Parse DOB (YYYY-MM-DD)
    dob_val = None
    if dob:
        try:
            dob_val = date.fromisoformat(dob)
        except ValueError:
            _flash(request, "Ngày sinh không hợp lệ!", "error")
            return RedirectResponse(url="/account", status_code=302)

    # Xác định tên
    ln = (last_name or "").strip()
    fn = (first_name or "").strip()

    # Nếu form mới không gửi, fallback từ full_name cũ
    if not (ln or fn):
        ln, fn = _split_vn(full_name)

    # Build full_name cho giai đoạn chuyển tiếp (nếu bạn vẫn giữ cột full_name)
    display = (" ".join([ln, fn])).strip() or None

    try:
        me.last_name = ln or None
        me.first_name = fn or None
        # Đồng bộ cột full_name (tương thích UI/view cũ)
        setattr(me, "full_name", display)

        me.email = email_norm
        me.dob = dob_val

        db.commit()
        _flash(request, "Cập nhật thông tin tài khoản thành công!", "success")
    except Exception:
        db.rollback()
        _flash(request, "Không cập nhật được thông tin, vui lòng thử lại!", "error")

    return RedirectResponse(url="/account", status_code=302)
