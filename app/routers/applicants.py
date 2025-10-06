# app/routers/applicants.py
from datetime import datetime, date
import io
import re

from fastapi import APIRouter, Depends, HTTPException, Query, status
from starlette.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..models.applicant import Applicant, ApplicantDoc
from ..models.checklist import ChecklistItem, ChecklistVersion
from ..schemas.applicant import ApplicantIn, ApplicantOut
from ..services.pdf_service import render_single_pdf, render_single_pdf_a5
from fastapi import Body
from sqlalchemy import or_
from fastapi import Query, Depends
from sqlalchemy.orm import Session



router = APIRouter(prefix="/applicants", tags=["applicants"])

# ----------------- DATE HELPERS -----------------
_DATE_DMY = re.compile(r'^(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})$')
_DATE_YMD = re.compile(r'^(\d{4})-(\d{2})-(\d{2})$')
def _parse_date_dmy_any(v) -> date | None:
    """Nhận dd/mm/yyyy | dd-mm-yyyy | yyyy-mm-dd | datetime/date | None -> date|None."""
    if v in (None, ""):
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    s = str(v).strip()
    m = _DATE_DMY.match(s)
    if m:
        d, mth, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return date(y, mth, d)
    m = _DATE_YMD.match(s)
    if m:
        y, mth, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return date(y, mth, d)
    raise ValueError(f"Invalid date format: {v}. Expect dd/mm/yyyy.")

def _to_dmy_any(v) -> str | None:
    """Trả chuỗi dd/mm/yyyy cho date|datetime|str hợp lệ, còn lại None."""
    if v in (None, ""):
        return None
    if isinstance(v, datetime):
        v = v.date()
    if isinstance(v, date):
        return v.strftime("%d/%m/%Y")
    s = str(v).strip()
    m = _DATE_DMY.match(s)
    if m:
        # chuẩn hoá về dấu "/"
        dd, mm, yy = m.group(1).zfill(2), m.group(2).zfill(2), m.group(3)
        return f"{dd}/{mm}/{yy}"
    m = _DATE_YMD.match(s)
    if m:
        return f"{m.group(3)}/{m.group(2)}/{m.group(1)}"
    return None

def _parse_date_flexible(v):
    """
    Trả về datetime.date hoặc None.
    Chấp nhận: dd/mm/yyyy, dd-mm-yyyy, yyyy-mm-dd, datetime/date.
    """
    if v in (None, ""):
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()

    s = str(v).strip()
    if not s:
        return None

    m = _DATE_DMY.match(s)
    if m:
        d, mth, y = map(int, m.groups())
        return date(y, mth, d)

    m = _DATE_YMD.match(s)
    if m:
        y, mth, d = map(int, m.groups())
        return date(y, mth, d)

    # fallback ISO
    try:
        return datetime.fromisoformat(s).date()
    except Exception:
        return None

def _parse_date_dmy(v):
    # alias theo tên cũ – luôn dùng bộ parse linh hoạt
    return _parse_date_flexible(v)

def _parse_date_ymd(v):
    # alias để không còn NameError ở code cũ
    return _parse_date_flexible(v)

def _to_dmy(v):
    """
    Chuẩn hóa sang chuỗi 'dd/mm/yyyy' (dùng cho hiển thị / lưu cột dạng text).
    """
    d = _parse_date_flexible(v)
    return f"{d.day:02d}/{d.month:02d}/{d.year:04d}" if d else None

def _to_ymd(v):
    """
    Nếu cần chuỗi 'yyyy-mm-dd'.
    """
    d = _parse_date_flexible(v)
    return f"{d.year:04d}-{d.month:02d}-{d.day:02d}" if d else None

# ----------------- FIND BY CODE (cho UI) -----------------
from sqlalchemy import func
from datetime import date, datetime
from fastapi import Depends, HTTPException
from .auth import require_roles

def _to_dmy(v):
    if not v:
        return None
    if isinstance(v, datetime):
        d = v.date()
    else:
        d = v
    if isinstance(d, date):
        return f"{d.day:02d}/{d.month:02d}/{d.year:04d}"
    return None

def _to_iso(v):
    if not v:
        return None
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, date):
        return datetime.combine(v, datetime.min.time()).isoformat()
    return None

@router.get("/by-code/{ma_ho_so}")
def get_by_code(
    ma_ho_so: str,
    db: Session = Depends(get_db),
    user=Depends(require_roles("Admin", "NhanVien", "CongTacVien")),  # CTV xem được
):
    key = (ma_ho_so or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="Thiếu mã hồ sơ")

    # 1) thử khớp không phân biệt hoa/thường
    a = (
        db.query(Applicant)
        .filter(func.lower(Applicant.ma_ho_so) == key.lower())
        .first()
    )

    # 2) nếu không có và người dùng nhập toàn số -> thử theo ID
    if not a and key.isdigit():
        a = db.query(Applicant).filter(Applicant.id == int(key)).first()

    # 3) fallback nhẹ: like (ít khi cần)
    if not a:
        a = (
            db.query(Applicant)
            .filter(Applicant.ma_ho_so.ilike(key))
            .first()
        )

    if not a:
        raise HTTPException(status_code=404, detail="Not Found")

    docs = (
        db.query(ApplicantDoc)
        .filter(ApplicantDoc.applicant_id == a.id)
        .all()
    )

    # lấy các field có thể khác tên giữa các version
    def pick(*names):
        for n in names:
            if hasattr(a, n):
                v = getattr(a, n)
                if v not in (None, ""):
                    return v
        return None

    applicant_payload = {
        "id": a.id,
        "ma_ho_so": a.ma_ho_so,

        # ngày: trả cả 2 dạng cho UI
        "ngay_nhan_hs": _to_dmy(a.ngay_nhan_hs),
        "ngay_nhan_hs_iso": _to_iso(a.ngay_nhan_hs),
        "ngay_sinh": _to_dmy(a.ngay_sinh),
        "ngay_sinh_iso": _to_iso(a.ngay_sinh),

        "ho_ten": a.ho_ten,
        "ma_so_hv": a.ma_so_hv,
        "so_dt": a.so_dt,
        "nganh_nhap_hoc": pick("nganh_nhap_hoc", "nganh"),
        "dot": pick("dot", "dot_tuyen"),
        "khoa": pick("khoa", "khoa_hoc", "khoahoc", "nien_khoa"),
        "da_tn_truoc_do": a.da_tn_truoc_do,
        "ghi_chu": a.ghi_chu,
        "nguoi_nhan_ky_ten": pick("nguoi_nhan_ky_ten", "nguoi_nhan", "nguoi_ky"),
        "status": getattr(a, "status", None),
        "printed": getattr(a, "printed", None),
        "checklist_version_id": getattr(a, "checklist_version_id", None),
    }

    return {
        "applicant": applicant_payload,
        "docs": [{"code": d.code, "so_luong": int(d.so_luong or 0)} for d in docs],
    }


# ----------------- CREATE -----------------
@router.post("", response_model=ApplicantOut, status_code=201)
@router.post("/", response_model=ApplicantOut, status_code=201)
def create_applicant(
    payload: ApplicantIn,
    db: Session = Depends(get_db),
    me=Depends(require_roles("Admin", "NhanVien", "CongTacVien")),  # ai có quyền tạo
):
    v = (
        db.query(ChecklistVersion)
        .filter(ChecklistVersion.version_name == payload.checklist_version_name)
        .first()
    )
    if not v:
        raise HTTPException(400, f"Checklist version '{payload.checklist_version_name}' not found")

    if db.query(Applicant).filter(Applicant.ma_ho_so == payload.ma_ho_so).first():
        raise HTTPException(409, "Mã hồ sơ đã tồn tại")

    # Lấy tên người đăng nhập
    me_name = (
        getattr(me, "full_name", None) or getattr(me, "username", None) or
        (me.get("full_name") if isinstance(me, dict) else None) or
        (me.get("username") if isinstance(me, dict) else None)
    )
    a = Applicant(
        ma_ho_so=payload.ma_ho_so.strip(),
        ngay_nhan_hs=_parse_date_dmy_any(payload.ngay_nhan_hs),
        ho_ten=payload.ho_ten,
        ma_so_hv=payload.ma_so_hv,
        ngay_sinh=_to_dmy_any(payload.ngay_sinh),
        so_dt=payload.so_dt,
        nganh_nhap_hoc=payload.nganh_nhap_hoc,
        dot=payload.dot,
        khoa=payload.khoa,
        da_tn_truoc_do=payload.da_tn_truoc_do,
        ghi_chu=payload.ghi_chu,
        # 🔴 luôn ghi theo account đang login
        nguoi_nhan_ky_ten = (me.full_name or me.username),
        checklist_version_id=v.id,
        status="saved",
        printed=False,
    )
    db.add(a)
    db.flush()

    for d in payload.docs:
        if d.so_luong in (None, ""):
            continue
        db.add(ApplicantDoc(applicant_id=a.id, code=d.code, so_luong=int(d.so_luong)))

    db.commit()
    db.refresh(a)
    return ApplicantOut(id=a.id, ma_ho_so=a.ma_ho_so, status=a.status, printed=a.printed)

# ----------------- SEARCH (cho UI) -----------------

# ---- SEARCH: cho Admin, Nhân viên, Cộng tác viên ----
@router.get("/search")
def search_applicants(
    q: str | None = Query(None, description="Để trống = lấy tất cả"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=1000),
    db: Session = Depends(get_db),
    user=Depends(require_roles("Admin", "NhanVien", "CongTacVien")),
):
    qn = (q or "").strip()
    if qn in {"", "%", "*"}:
        qn = None

    query = db.query(Applicant)
    if qn:
        like = f"%{qn}%"
        query = query.filter(
            or_(Applicant.ho_ten.ilike(like),
                Applicant.ma_ho_so.ilike(like),
                Applicant.ma_so_hv.ilike(like))
        )

    total = query.count()
    rows = (query.order_by(Applicant.id.desc())
                 .offset((page-1)*size)
                 .limit(size)
                 .all())

    return {
        "items": [{
            "id": a.id,
            "ma_ho_so": a.ma_ho_so,
            "ho_ten": a.ho_ten,
            "ma_so_hv": a.ma_so_hv,
            "ngay_nhan_hs": a.ngay_nhan_hs.isoformat() if a.ngay_nhan_hs else None,
            "dot": a.dot,
            "nganh_nhap_hoc": getattr(a, "nganh_nhap_hoc", None),
            "khoa": getattr(a, "khoa", None),
            "nguoi_nhan_ky_ten": getattr(a, "nguoi_nhan_ky_ten", None),
        } for a in rows],
        "page": page, "size": size, "total": total,
    }
# ----------------- FIND BY CODE (API cho hệ thống khác) -----------------
@router.get("/find")
@router.get("/find/")
def find_by_ma_ho_so(ma_ho_so: str = Query(...), db: Session = Depends(get_db)):
    code = (ma_ho_so or "").strip()
    a = db.query(Applicant).filter(Applicant.ma_ho_so == code).first()
    if not a:
        raise HTTPException(status_code=404, detail="Not Found")

    docs = db.query(ApplicantDoc).filter_by(applicant_id=a.id).all()
    q = db.query(ChecklistItem).filter(ChecklistItem.version_id == a.checklist_version_id)
    q = q.order_by(getattr(ChecklistItem, "order_no", ChecklistItem.id).asc())
    items = q.all()

    return {
        "id": a.id,
        "ma_ho_so": a.ma_ho_so,
        # Giữ ISO ở API này để form dễ set value cho <input type="date">
        "ngay_nhan_hs": a.ngay_nhan_hs.isoformat() if a.ngay_nhan_hs else None,
        "ho_ten": a.ho_ten,
        "ma_so_hv": a.ma_so_hv,
        "ngay_sinh": (
            a.ngay_sinh if isinstance(a.ngay_sinh, str)
            else (a.ngay_sinh.isoformat() if a.ngay_sinh else None)
        ),
        "so_dt": a.so_dt,
        "nganh_nhap_hoc": a.nganh_nhap_hoc,
        "dot": a.dot,
        "khoa": getattr(a, "khoa", None),
        "da_tn_truoc_do": a.da_tn_truoc_do,
        "ghi_chu": a.ghi_chu,
        "nguoi_nhan_ky_ten": a.nguoi_nhan_ky_ten,
        "docs": [{"code": d.code, "so_luong": int(d.so_luong or 0)} for d in docs],
        "checklist_items": [
            {"code": it.code, "display_name": it.display_name, "order_no": getattr(it, "order_no", 0)}
            for it in items
        ],
    }

# ----------------- UPDATE -----------------
@router.put("/{applicant_id}")
def update_applicant(
    applicant_id: int,
    body: dict = Body(...),
    db: Session = Depends(get_db),
    me=Depends(require_roles("Admin", "NhanVien", "CongTacVien")),   # <-- CTV được cập nhật
):
    a = db.query(Applicant).get(applicant_id)
    if not a:
        raise HTTPException(404, "Applicant not found")

    def get(k, default=None): return body.get(k, default)
    for f in ("ma_ho_so", "ho_ten", "ma_so_hv", "ngay_nhan_hs"):
      if not str(get(f, "")).strip():
        raise HTTPException(status_code=400, detail=f"Thiếu trường bắt buộc: {f}")

    try:
        a.ma_ho_so       = get("ma_ho_so").strip()
        a.ngay_nhan_hs   = _parse_date_dmy_any(get("ngay_nhan_hs"))
        a.ho_ten         = get("ho_ten")
        a.ma_so_hv       = get("ma_so_hv")
        a.ngay_sinh      = _to_dmy_any(get("ngay_sinh"))
        a.so_dt          = get("so_dt")
        a.nganh_nhap_hoc = get("nganh_nhap_hoc")
        a.dot            = get("dot")
        a.khoa           = get("khoa")
        a.da_tn_truoc_do = get("da_tn_truoc_do")
        a.ghi_chu        = get("ghi_chu")
        # 🔴 BỎ giá trị FE gửi lên, luôn ghi đè theo account hiện tại
        a.nguoi_nhan_ky_ten = (me.full_name or me.username)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    docs = body.get("docs", None)
    if docs is not None:
        existing = {d.code: d for d in db.query(ApplicantDoc).filter_by(applicant_id=a.id).all()}
        for d in docs:
            code = d.get("code")
            sl = d.get("so_luong")
            if code is None or sl is None:
                continue
            sl = int(sl)
            if sl <= 0:
                if code in existing:
                    db.delete(existing[code])
            else:
                if code in existing:
                    existing[code].so_luong = sl
                else:
                    db.add(ApplicantDoc(applicant_id=a.id, code=code, so_luong=sl))

    db.commit()
    return {"ok": True, "id": a.id, "ma_ho_so": a.ma_ho_so}

# ----------------- DELETE -----------------
@router.delete("/{applicant_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_applicant(applicant_id: int, db: Session = Depends(get_db)):
    a = db.query(Applicant).get(applicant_id)
    if not a:
        raise HTTPException(404, "Applicant not found")
    db.query(ApplicantDoc).filter_by(applicant_id=a.id).delete(synchronize_session=False)
    db.delete(a)
    db.commit()
    return

# ----------------- PRINT ONE (A4 2-up & A5) -----------------
def _do_print(applicant_id: int, mark_printed: bool, db: Session):
    a = db.query(Applicant).filter(Applicant.id == applicant_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Applicant not found")

    q = db.query(ChecklistItem).filter(ChecklistItem.version_id == a.checklist_version_id)
    if hasattr(ChecklistItem, "order_index"):
        q = q.order_by(getattr(ChecklistItem, "order_index").asc())
    elif hasattr(ChecklistItem, "order_no"):
        q = q.order_by(getattr(ChecklistItem, "order_no").asc())
    else:
        q = q.order_by(ChecklistItem.id.asc())
    items = q.all()

    docs = db.query(ApplicantDoc).filter(ApplicantDoc.applicant_id == a.id).all()
    pdf_bytes = render_single_pdf(a, items, docs)

    if mark_printed:
        a.printed = True
        a.status = "printed"
        a.updated_at = datetime.utcnow()
        db.commit()

    filename = f"HS_{a.ma_ho_so or applicant_id}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )

@router.get("/{applicant_id}/print")
def print_applicant_now(applicant_id: int, mark_printed: bool = Query(False), db: Session = Depends(get_db)):
    return _do_print(applicant_id, mark_printed, db)

@router.post("/{applicant_id}/print")
def print_applicant_now_post(applicant_id: int, mark_printed: bool = Query(True), db: Session = Depends(get_db)):
    return _do_print(applicant_id, mark_printed, db)

def _do_print_a5(applicant_id: int, mark_printed: bool, db: Session):
    a = db.query(Applicant).filter(Applicant.id == applicant_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Applicant not found")

    q = db.query(ChecklistItem).filter(ChecklistItem.version_id == a.checklist_version_id)
    if hasattr(ChecklistItem, "order_index"):
        q = q.order_by(getattr(ChecklistItem, "order_index").asc())
    elif hasattr(ChecklistItem, "order_no"):
        q = q.order_by(getattr(ChecklistItem, "order_no").asc())
    else:
        q = q.order_by(ChecklistItem.id.asc())
    items = q.all()

    docs = db.query(ApplicantDoc).filter(ApplicantDoc.applicant_id == a.id).all()
    pdf_bytes = render_single_pdf_a5(a, items, docs)

    if mark_printed:
        a.printed = True
        a.status = "printed"
        a.updated_at = datetime.utcnow()
        db.commit()

    filename = f"HS_{a.ma_ho_so or applicant_id}_A5.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )



@router.get("/recent")
def get_recent_applicants(db: Session = Depends(get_db), limit: int = 50):
    q = db.query(Applicant).order_by(Applicant.id.desc()).limit(limit).all()
    return [{"id": a.id, "ma_ho_so": a.ma_ho_so, "ho_ten": a.ho_ten} for a in q]

@router.get("/{applicant_id}/print-a5")
def print_applicant_a5(applicant_id: int, mark_printed: bool = Query(False), db: Session = Depends(get_db)):
    return _do_print_a5(applicant_id, mark_printed, db)

@router.post("/{applicant_id}/print-a5")
def print_applicant_a5_post(applicant_id: int, mark_printed: bool = Query(True), db: Session = Depends(get_db)):
    return _do_print_a5(applicant_id, mark_printed, db)
