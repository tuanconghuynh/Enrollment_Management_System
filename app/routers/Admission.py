# app/routers/Admission.py
import os
import pandas as pd
from fastapi import APIRouter, Request, Depends, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session


from app.db.session import get_db
from app.models import Student, Application, User
from .auth import require_roles, get_current_user
from app.routers.checklist import _get_active


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "web"))

router = APIRouter(prefix="/Admission", tags=["Admission"])

# =====================
# Import học viên
# =====================

@router.get("/import", response_class=HTMLResponse)
def import_page(
    request: Request,
    me: User = Depends(require_roles("Admin", "NhanVien")),   # quyền import: Admin + Nhân viên
):
    return templates.TemplateResponse("import_students.html", {"request": request, "me": me, "msg": None})


@router.post("/import", response_class=HTMLResponse)
def import_students(
    request: Request,
    file: UploadFile = File(...),
    me: User = Depends(require_roles("Admin", "NhanVien")),
    db: Session = Depends(get_db),
):
    # Đọc file
    fname = file.filename.lower()
    try:
        if fname.endswith(".csv"):
            df = pd.read_csv(file.file, dtype=str).fillna("")
        elif fname.endswith(".xlsx") or fname.endswith(".xls"):
            df = pd.read_excel(file.file, dtype=str, engine="openpyxl").fillna("")
        else:
            raise HTTPException(status_code=400, detail="Định dạng file không hỗ trợ. Hãy dùng .csv hoặc .xlsx")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Lỗi đọc file: {e}")

    # Cột tối thiểu
    required_cols = {"student_code", "full_name"}
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise HTTPException(status_code=400, detail=f"Thiếu cột bắt buộc: {', '.join(missing)}")

    created, skipped = 0, 0
    for _, row in df.iterrows():
        code = (row.get("student_code") or "").strip()
        name = (row.get("full_name") or "").strip()
        if not code or not name:
            continue

        # bỏ qua nếu đã có
        if db.query(Student).filter(Student.student_code == code).first():
            skipped += 1
            continue

        # ✅ thêm dân tộc nếu có trong file
        dan_toc_val = (row.get("dan_toc") or row.get("Dân tộc") or "").strip()

        s = Student(
            student_code=code,
            full_name=name,
            dob=(row.get("dob") or "").strip(),
            gender=(row.get("gender") or "").strip(),
            phone=(row.get("phone") or "").strip(),
            email=(row.get("email") or "").strip(),
            id_number=(row.get("id_number") or "").strip(),
            address=(row.get("address") or "").strip(),
            dan_toc=dan_toc_val,
            note=(row.get("note") or "").strip(),
            created_by_user_id=me.id,
        )
        db.add(s)
        created += 1

    db.commit()
    msg = f"Tạo {created} học viên mới, bỏ qua {skipped} (đã tồn tại)."
    return templates.TemplateResponse("import_students.html", {"request": request, "me": me, "msg": msg})

# =====================
# Danh sách học viên
# =====================

@router.get("/students", response_class=HTMLResponse)
def students_list(
    request: Request,
    me: User = Depends(require_roles("Admin", "NhanVien", "CongTacVien")),
    db: Session = Depends(get_db),
):
    students = db.query(Student).order_by(Student.created_at.desc()).all()
    # ✅ truyền thêm trường dan_toc sang template
    return templates.TemplateResponse(
        "students_list.html",
        {"request": request, "me": me, "students": students},
    )

# =====================
# Tạo hồ sơ nộp (Application) cho học viên
# =====================

@router.post("/applications/create/{student_id}")
def create_application(
    student_id: int,
    me: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    student = db.get(Student, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Không tìm thấy học viên")

    # Lấy version danh mục hồ sơ đang active
    active_ver = _get_active(db)

    app_row = Application(
        student_id=student_id,
        status="Draft",
        assigned_to_user_id=me.id,
        last_modified_by_user_id=me.id,
        checklist_version_id=active_ver.id,          # ✅ gắn version_id
        checklist_version_name=active_ver.version_name,  # ✅ gắn tên version
    )
    db.add(app_row)
    db.commit()
    return RedirectResponse(url="/Admission/students", status_code=302)
