# app/routers/account.py
from pathlib import Path
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.routers.auth import require_user as require_login
from app.core.security import verify_password, hash_password
from datetime import date

router = APIRouter()

ROOT_DIR = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(ROOT_DIR / "web"))

def _flash(request: Request, msg: str, level: str = "info"):
    request.session["_flash"] = {"message": msg, "level": level}

def _pop_flash(request: Request):
    f = request.session.pop("_flash", None)
    return f

@router.get("/account")
def account_view(request: Request, me: User = Depends(require_login), db: Session = Depends(get_db)):
    flash = _pop_flash(request)
    return templates.TemplateResponse(
        "account.html",
        {"request": request, "me": me, "flash": flash, "first": request.query_params.get("first") == "1"}
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
    if len(new_password) < 6:
        _flash(request, "Mật khẩu mới tối thiểu 6 ký tự.", "error")
        return RedirectResponse(url="/account", status_code=302)
    if new_password != confirm_password:
        _flash(request, "Xác nhận mật khẩu không khớp.", "error")
        return RedirectResponse(url="/account", status_code=302)
    if not verify_password(old_password, me.password_hash):
        _flash(request, "Mật khẩu hiện tại không đúng.", "error")
        return RedirectResponse(url="/account", status_code=302)

    try:
        me.password_hash = hash_password(new_password)
        me.must_change_password = False
        me.password_changed_at = datetime.now(timezone.utc)
        db.commit()
        # đồng bộ session để middleware không redirect nữa
        request.session["must_change_password"] = False
        _flash(request, "Đổi mật khẩu thành công.", "success")
    except Exception:
        db.rollback()
        _flash(request, "Không thể đổi mật khẩu. Vui lòng thử lại.", "error")

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
    # Validate & unique email (không trùng người khác)
    email = (email or "").strip() or None
    if email:
        dup = db.query(User).filter(User.email == email, User.id != me.id).first()
        if dup:
            _flash(request, "Email đã được dùng bởi tài khoản khác.", "error")
            return RedirectResponse(url="/account", status_code=302)

    # parse dob nếu có
    dob_val = None
    if dob:
        try:
            dob_val = date.fromisoformat(dob)
        except ValueError:
            _flash(request, "Ngày sinh không hợp lệ (YYYY-MM-DD).", "error")
            return RedirectResponse(url="/account", status_code=302)

    try:
        me.full_name = (full_name or "").strip() or None
        me.email = email
        me.dob = dob_val
        db.commit()
        _flash(request, "Cập nhật thông tin tài khoản thành công.", "success")
    except Exception:
        db.rollback()
        _flash(request, "Không cập nhật được thông tin, vui lòng thử lại.", "error")

    return RedirectResponse(url="/account", status_code=302)
