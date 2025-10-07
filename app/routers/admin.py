# app/routers/admin.py
from pathlib import Path
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from passlib.hash import bcrypt

from app.db.session import get_db
from app.models.user import User
from app.routers.auth import require_admin  # guard Admin

router = APIRouter()

# === Trỏ đúng thư mục template: <repo>/web ===
ROOT_DIR = Path(__file__).resolve().parents[2]   # .../Project_AdmissionCheck
templates = Jinja2Templates(directory=str(ROOT_DIR / "web"))

@router.get("/admin")
def admin_index(request: Request,
                me: User = Depends(require_admin),
                db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.id.desc()).all()
    return templates.TemplateResponse(
        "admin_index.html",
        {"request": request, "users": users, "me": me}
    )

@router.post("/admin/users/create")
def admin_create_user(username: str = Form(...),
                      password: str = Form(...),
                      full_name: str = Form(""),
                      email: str = Form(""),
                      role: str = Form("NhanVien"),
                      me: User = Depends(require_admin),
                      db: Session = Depends(get_db)):
    # username hoặc email trùng
    exists = db.query(User).filter((User.username == username) | (User.email == email)).first()
    if exists:
        raise HTTPException(400, "Username/Email đã tồn tại")
    u = User(
        username=username,
        email=email or None,
        full_name=full_name or None,
        role=role,
        is_active=True,
        password_hash=bcrypt.hash(password),
    )
    db.add(u); db.commit()
    return RedirectResponse(url="/admin", status_code=302)

@router.post("/admin/users/toggle")
def admin_toggle_user(user_id: int = Form(...),
                      me: User = Depends(require_admin),
                      db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    if u.id == me.id:
        raise HTTPException(400, "Không thể tự khoá tài khoản của bạn")
    u.is_active = not bool(u.is_active)
    db.commit()
    return RedirectResponse(url="/admin", status_code=302)

@router.post("/admin/users/reset-pass")
def admin_reset_pass(user_id: int = Form(...),
                     new_password: str = Form(...),
                     me: User = Depends(require_admin),
                     db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    u.password_hash = bcrypt.hash(new_password)
    db.commit()
    return RedirectResponse(url="/admin", status_code=302)
