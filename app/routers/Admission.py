# app/routers/Admission.py
import os
import pandas as pd
from fastapi import APIRouter, Request, Depends, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Student, User
from .auth import require_roles

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "web"))

router = APIRouter(prefix="/Admission", tags=["Admission"])

# ========= helper tách tên Việt (trong trường hợp chỉ có full_name) =========
def _split_vn(fullname: str):
    s = " ".join((fullname or "").split())
    if not s:
        return "", ""
    parts = s.split(" ")
    if len(parts) == 1:
        return "", parts[0]
    return " ".join(parts[:-1]), parts[-1]

# =====================
# Import học viên
# =====================

@router.get("/import", response_class=HTMLResponse)
def import_page(
    request: Request,
    me: User = Depends(require_roles("Admin", "NhanVien", "Manager")),  # Chỉ cho phép Admin, NhanVien, Manager
):
    return templates.TemplateResponse("import_students.html", {"request": request, "me": me, "msg": None})

@router.post("/import", response_class=HTMLResponse)
def import_students(
    request: Request,
    file: UploadFile = File(...),
    me: User = Depends(require_roles("Admin", "NhanVien", "Manager")),  # Chỉ cho phép Admin, NhanVien, Manager
    db: Session = Depends(get_db),
):
    # Đọc file
    fname = (file.filename or "").lower()
    try:
        if fname.endswith(".csv"):
            df = pd.read_csv(file.file, dtype=str).fillna("")
        elif fname.endswith(".xlsx") or fname.endswith(".xls"):
            df = pd.read_excel(file.file, dtype=str, engine="openpyxl").fillna("")
        else:
            raise HTTPException(status_code=400, detail="Định dạng file không hỗ trợ. Hãy dùng .csv hoặc .xlsx")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Lỗi đọc file: {e}")

    # Kiểm tra cột bắt buộc
    cols = set(df.columns)
    if "student_code" not in cols:
        raise HTTPException(status_code=400, detail="Thiếu cột bắt buộc: student_code")

    # Các cột tên có thể dùng:
    has_split = ("ho_dem" in cols and "ten" in cols) or ("last_name" in cols and "first_name" in cols)
    has_full = "full_name" in cols or "ho_ten" in cols

    if not (has_split or has_full):
        raise HTTPException(
            status_code=400,
            detail="Thiếu thông tin tên. Cần 'ho_dem' + 'ten' (hoặc 'last_name' + 'first_name') hoặc 'full_name'."
        )

    created, skipped = 0, 0

    for _, row in df.iterrows():
        code = (row.get("student_code") or "").strip()
        if not code:
            continue

        # Bỏ qua nếu đã tồn tại
        if db.query(Student).filter(Student.student_code == code).first():
            skipped += 1
            continue

        # Lấy tên từ các cột có sẵn
        ho_dem = (row.get("ho_dem") or row.get("last_name") or "").strip()
        ten = (row.get("ten") or row.get("first_name") or "").strip()

        # Nếu chưa có thì fallback sang full_name / ho_ten
        if not (ho_dem or ten):
            full = (row.get("full_name") or row.get("ho_ten") or "").strip()
            if not full:
                continue
            ho_dem, ten = _split_vn(full)

        full_name = f"{ho_dem} {ten}".strip()

        # Dân tộc (nếu có)
        dan_toc_val = (row.get("dan_toc") or row.get("Dân tộc") or "").strip()

        # Parse ngày sinh (nếu có)
        dob_raw = (row.get("dob") or "").strip()
        dob_val = None
        if dob_raw:
            from datetime import date
            try:
                dob_val = date.fromisoformat(dob_raw)
            except Exception:
                dob_val = None

        # Tạo đối tượng học viên
        s = Student(
            student_code=code,
            last_name=ho_dem or None,
            first_name=ten or None,
            full_name=full_name or None,
            dob=dob_val,
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

# End of file
