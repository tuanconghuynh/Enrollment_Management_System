import pandas as pd
from fastapi import APIRouter, Request, Depends, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import os
from app.models.user import User  

from app.db.session import get_db
from app.models import Student, Application, User
from .auth import require_roles, get_current_user

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "web"))

router = APIRouter(prefix="/admissions", tags=["admissions"])

@router.get("/import", response_class=HTMLResponse)
def import_page(request: Request, user=Depends(require_roles("Admin","NhanVien","CongTacVien"))):
    return templates.TemplateResponse("import_students.html", {"request": request, "msg": None})

@router.post("/import", response_class=HTMLResponse)
def import_students(
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(require_roles("Admin","NhanVien","CongTacVien")),
    db: Session = Depends(get_db)
):
    if file.filename.lower().endswith(".csv"):
        df = pd.read_csv(file.file, dtype=str).fillna("")
    else:
        df = pd.read_excel(file.file, dtype=str).fillna("")
    created, skipped = 0, 0
    for _, row in df.iterrows():
        code = (row.get("student_code") or "").strip()
        name = (row.get("full_name") or "").strip()
        if not code or not name:
            continue
        if db.query(Student).filter(Student.student_code == code).first():
            skipped += 1; continue
        s = Student(
            student_code=code, full_name=name,
            dob=row.get("dob",""), gender=row.get("gender",""),
            phone=row.get("phone",""), email=row.get("email",""),
            id_number=row.get("id_number",""), address=row.get("address",""),
            note=row.get("note",""), created_by_user_id=user.id
        )
        db.add(s); created += 1
    db.commit()
    return templates.TemplateResponse("import_students.html", {"request": request, "msg": f"Tạo {created}, bỏ qua {skipped}."})

@router.get("/students", response_class=HTMLResponse)
def students_list(request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    students = db.query(Student).order_by(Student.created_at.desc()).all()
    return templates.TemplateResponse("students_list.html", {"request": request, "students": students})

@router.post("/applications/create/{student_id}")
def create_application(student_id: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    app_row = Application(student_id=student_id, status="Draft",
                          assigned_to_user_id=user.id, last_modified_by_user_id=user.id)
    db.add(app_row); db.commit()
    return RedirectResponse(url="/admissions/students", status_code=302)

@router.get("/admissions/import", response_class=HTMLResponse)
def import_page(request: Request, user=Depends(require_roles("Admin","NhanVien"))):
    return templates.TemplateResponse("import_students.html", {"request": request, "me": user})

@router.post("/admissions/import", response_class=HTMLResponse)
def import_students(
    request: Request,
    file: UploadFile = File(...),
    user=Depends(require_roles("Admin","NhanVien")),   # <---
    db: Session = Depends(get_db)
):
    
    # ... (phần đọc CSV/Excel không đổi)
    # CUỐI CÙNG trả template có 'me'
    return templates.TemplateResponse("import_students.html", {"request": request, "msg": msg, "me": user})

@router.get("/students", response_class=HTMLResponse)
def students_list(
    request: Request,
    user: User = Depends(require_roles("Admin","NhanVien","CongTacVien")),
    db: Session = Depends(get_db)
):
    students = db.query(Student).order_by(Student.created_at.desc()).all()
    # TRUYỀN 'me'
    return templates.TemplateResponse(
        "students_list.html",
        {"request": request, "students": students, "me": user}
    )

# === Import học viên: chỉ Admin + Nhân viên ===
@router.get("/admissions/import", response_class=HTMLResponse)
def import_page(request: Request, user=Depends(require_roles("Admin","NhanVien"))):
    return templates.TemplateResponse("import_students.html", {"request": request, "me": user})

@router.post("/admissions/import", response_class=HTMLResponse)
def import_students(
    request: Request,
    file: UploadFile = File(...),
    user=Depends(require_roles("Admin","NhanVien")),   # <---
    db: Session = Depends(get_db)
):
    # ... logic import
    return templates.TemplateResponse("import_students.html", {"request": request, "msg": msg, "me": user})

# === Danh sách hồ sơ: chỉ Admin + Nhân viên ===
@router.get("/admissions/students", response_class=HTMLResponse)
def students_list(request: Request, user=Depends(require_roles("Admin","NhanVien","CongTacVien")), db: Session = Depends(get_db)):
    # ... load dữ liệu nếu cần
    return templates.TemplateResponse("students_list.html", {"request": request, "me": user})
