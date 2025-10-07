# app/routers/applicants.py
from __future__ import annotations

import io
import re
from datetime import datetime, date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Body, status
from fastapi.responses import StreamingResponse
from sqlalchemy import or_, func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.applicant import Applicant, ApplicantDoc
from app.models.checklist import ChecklistItem, ChecklistVersion
from app.routers.auth import require_roles

try:
    from app.schemas.applicant import ApplicantIn, ApplicantOut
except Exception:
    ApplicantIn = dict  # type: ignore
    ApplicantOut = dict  # type: ignore

router = APIRouter(prefix="/applicants", tags=["Applicants"])

# ================= Helpers =================
DATE_DMY = re.compile(r"^(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})$")
DATE_YMD = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
MSSV_REGEX = re.compile(r"^\d{10}$")

def ensure_mssv(v: str):
    if not MSSV_REGEX.fullmatch(v or ""):
        raise HTTPException(status_code=422, detail="ma_so_hv phải gồm đúng 10 chữ số.")

def _parse_date_flexible(v: Optional[object]) -> Optional[date]:
    if v in (None, ""):
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    s = str(v).strip()
    if not s:
        return None
    m = DATE_DMY.match(s)
    if m:
        d, mth, y = map(int, m.groups())
        return date(y, mth, d)
    m = DATE_YMD.match(s)
    if m:
        y, mth, d = map(int, m.groups())
        return date(y, mth, d)
    try:
        return datetime.fromisoformat(s).date()
    except Exception:
        return None

def _to_dmy(v: Optional[object]) -> Optional[str]:
    d = _parse_date_flexible(v)
    return f"{d.day:02d}/{d.month:02d}/{d.year:04d}" if d else None

def _to_iso(v: Optional[object]) -> Optional[str]:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, date):
        return datetime.combine(v, datetime.min.time()).isoformat()
    d = _parse_date_flexible(v)
    return datetime.combine(d, datetime.min.time()).isoformat() if d else None

# ================= GET by code =================
@router.get("/by-code/{key}")
def get_by_code(
    key: str,
    db: Session = Depends(get_db),
    me=Depends(require_roles("Admin", "NhanVien", "CongTacVien")),
):
    k = (key or "").strip()
    if not k:
        raise HTTPException(400, "Thiếu mã tra cứu")

    # Ưu tiên theo ma_ho_so (cho phép trùng) -> lấy bản mới nhất
    a = (
        db.query(Applicant)
        .filter(func.lower(Applicant.ma_ho_so) == k.lower())
        .order_by(Applicant.created_at.desc())
        .first()
    )

    # Nếu chưa có, thử theo MSSV (unique)
    if not a and MSSV_REGEX.fullmatch(k):
        a = db.query(Applicant).filter(Applicant.ma_so_hv == k).first()

    # Fallback LIKE ma_ho_so -> lấy mới nhất
    if not a:
        a = (
            db.query(Applicant)
            .filter(Applicant.ma_ho_so.ilike(k))
            .order_by(Applicant.created_at.desc())
            .first()
        )

    if not a:
        raise HTTPException(404, "Not Found")

    docs = db.query(ApplicantDoc).filter(
        ApplicantDoc.applicant_ma_so_hv == a.ma_so_hv
    ).all()

    def pick(obj, *names):
        for n in names:
            if hasattr(obj, n):
                v = getattr(obj, n)
                if v not in (None, ""):
                    return v
        return None

    applicant_payload = {
        "id": a.ma_so_hv,
        "applicant_id": a.ma_so_hv,
        "ma_so_hv": a.ma_so_hv,
        "ma_ho_so": a.ma_ho_so,
        "ngay_nhan_hs": _to_dmy(a.ngay_nhan_hs),
        "ngay_nhan_hs_iso": _to_iso(a.ngay_nhan_hs),
        "ho_ten": a.ho_ten,
        "email_hoc_vien": getattr(a, "email_hoc_vien", None),
        "ngay_sinh": _to_dmy(a.ngay_sinh),
        "ngay_sinh_iso": _to_iso(a.ngay_sinh),
        "so_dt": a.so_dt,
        "nganh_nhap_hoc": pick(a, "nganh_nhap_hoc", "nganh"),
        "dot": pick(a, "dot", "dot_tuyen"),
        "khoa": pick(a, "khoa", "khoa_hoc", "khoahoc", "nien_khoa"),
        "da_tn_truoc_do": a.da_tn_truoc_do,
        "ghi_chu": a.ghi_chu,
        "nguoi_nhan_ky_ten": pick(a, "nguoi_nhan_ky_ten", "nguoi_nhan", "nguoi_ky"),
        "status": getattr(a, "status", None),
        "printed": getattr(a, "printed", None),
        "checklist_version_id": getattr(a, "checklist_version_id", None),
    }

    return {
        "applicant": applicant_payload,
        "docs": [{"code": d.code, "so_luong": int(d.so_luong or 0)} for d in docs],
    }

@router.get("/by-mshv/{ma_so_hv}")
def get_by_mshv(
    ma_so_hv: str,
    db: Session = Depends(get_db),
    user=Depends(require_roles("Admin", "NhanVien", "CongTacVien")),
):
    key = (ma_so_hv or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="Thiếu MSHV")

    a = db.query(Applicant).filter(func.lower(Applicant.ma_so_hv) == key.lower()).first()
    if not a:
        a = db.query(Applicant).filter(Applicant.ma_so_hv.ilike(f"%{key}%")).first()
    if not a:
        raise HTTPException(status_code=404, detail="Not Found")

    docs = db.query(ApplicantDoc).filter(
        ApplicantDoc.applicant_ma_so_hv == a.ma_so_hv
    ).all()

    def pick(*names):
        for n in names:
            if hasattr(a, n):
                v = getattr(a, n)
                if v not in (None, ""):
                    return v
        return None

    def _to_dmy2(v):
        if not v: return None
        if isinstance(v, datetime): v = v.date()
        if isinstance(v, date): return f"{v.day:02d}/{v.month:02d}/{v.year:04d}"
        try:
            return datetime.fromisoformat(str(v)).strftime("%d/%m/%Y")
        except Exception:
            return str(v)

    def _to_iso2(v):
        if not v: return None
        if isinstance(v, datetime): return v.isoformat()
        if isinstance(v, date):
            return datetime.combine(v, datetime.min.time()).isoformat()
        try:
            d = datetime.fromisoformat(str(v))
            return d.isoformat()
        except Exception:
            return None

    applicant_payload = {
        "id": a.ma_so_hv,
        "applicant_id": a.ma_so_hv,
        "ma_ho_so": a.ma_ho_so,
        "ngay_nhan_hs": _to_dmy2(a.ngay_nhan_hs),
        "ngay_nhan_hs_iso": _to_iso2(a.ngay_nhan_hs),
        "ngay_sinh": _to_dmy2(a.ngay_sinh),
        "ngay_sinh_iso": _to_iso2(a.ngay_sinh),
        "ho_ten": a.ho_ten,
        "ma_so_hv": a.ma_so_hv,
        "so_dt": a.so_dt,
        "nganh_nhap_hoc": pick("nganh_nhap_hoc","nganh"),
        "dot": pick("dot","dot_tuyen"),
        "khoa": pick("khoa","khoa_hoc","khoahoc","nien_khoa"),
        "da_tn_truoc_do": a.da_tn_truoc_do,
        "ghi_chu": a.ghi_chu,
        "nguoi_nhan_ky_ten": pick("nguoi_nhan_ky_ten","nguoi_nhan","nguoi_ky"),
        "status": getattr(a, "status", None),
        "printed": getattr(a, "printed", None),
        "checklist_version_id": getattr(a, "checklist_version_id", None),
        "email_hoc_vien": getattr(a, "email_hoc_vien", None),
    }

    return {
        "applicant": applicant_payload,
        "docs": [{"code": d.code, "so_luong": int(d.so_luong or 0)} for d in docs],
    }

# ================= CREATE =================
@router.post("", status_code=201)
@router.post("/", status_code=201)
def create_applicant(
    payload: ApplicantIn,
    db: Session = Depends(get_db),
    me=Depends(require_roles("Admin", "NhanVien", "CongTacVien")),
):
    v = db.query(ChecklistVersion).filter(
        ChecklistVersion.version_name == getattr(payload, "checklist_version_name", None)
    ).first()
    if not v:
        raise HTTPException(400, "Checklist version không tồn tại")

    ma_so_hv = (getattr(payload, "ma_so_hv", "") or "").strip()
    ensure_mssv(ma_so_hv)

    ma_ho_so = (getattr(payload, "ma_ho_so", "") or "").strip()
    ho_ten   = (getattr(payload, "ho_ten", "") or "").strip()
    ngay_nhan_hs = _parse_date_flexible(getattr(payload, "ngay_nhan_hs", None))

    if not ma_ho_so:
        raise HTTPException(400, "Thiếu trường bắt buộc: ma_ho_so")
    if not ho_ten:
        raise HTTPException(400, "Thiếu trường bắt buộc: ho_ten")
    if not ngay_nhan_hs:
        raise HTTPException(400, "Thiếu trường bắt buộc: ngay_nhan_hs (dd/MM/YYYY hoặc YYYY-MM-DD)")

    # CHỈ chặn trùng MSSV
    if db.query(Applicant).filter(Applicant.ma_so_hv == ma_so_hv).first():
        raise HTTPException(409, "MSSV (ma_so_hv) đã tồn tại")

    a = Applicant(
        ma_so_hv=ma_so_hv,
        ma_ho_so=ma_ho_so,
        ngay_nhan_hs=ngay_nhan_hs,
        ho_ten=ho_ten,
        email_hoc_vien=getattr(payload, "email_hoc_vien", None),
        ngay_sinh=_parse_date_flexible(getattr(payload, "ngay_sinh", None)),
        so_dt=getattr(payload, "so_dt", None),
        nganh_nhap_hoc=getattr(payload, "nganh_nhap_hoc", None),
        dot=getattr(payload, "dot", None),
        khoa=getattr(payload, "khoa", None),
        da_tn_truoc_do=getattr(payload, "da_tn_truoc_do", None),
        ghi_chu=getattr(payload, "ghi_chu", None),
        nguoi_nhan_ky_ten=(getattr(me, "full_name", None) or getattr(me, "username", None)),
        checklist_version_id=v.id,
        status="saved",
        printed=False,
    )
    db.add(a)

    docs = getattr(payload, "docs", []) or []
    for d in docs:
        code = d.get("code") if isinstance(d, dict) else getattr(d, "code", None)
        sl   = d.get("so_luong") if isinstance(d, dict) else getattr(d, "so_luong", None)
        if sl in (None, ""):
            continue
        db.add(ApplicantDoc(applicant_ma_so_hv=ma_so_hv, code=code, so_luong=int(sl)))

    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        # Nếu trong DB vẫn còn unique trên ma_ho_so → trả thông báo rõ ràng
        if "ma_ho_so" in str(e.orig).lower() and "unique" in str(e.orig).lower():
            raise HTTPException(409, "DB còn UNIQUE index trên ma_ho_so – hãy DROP INDEX trước khi import trùng.")
        raise HTTPException(500, "Lỗi ghi dữ liệu.")

    return {
        "id": a.ma_so_hv,
        "ma_so_hv": a.ma_so_hv,
        "ma_ho_so": a.ma_ho_so,
        "status": a.status,
        "printed": a.printed,
    }

# ================= SEARCH =================
@router.get("/search")
def search_applicants(
    q: Optional[str] = Query(None, description="Để trống = lấy tất cả"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=1000),
    db: Session = Depends(get_db),
    me=Depends(require_roles("Admin", "NhanVien", "CongTacVien")),
):
    qn = (q or "").strip() or None
    query = db.query(Applicant)
    if qn:
        like = f"%{qn}%"
        query = query.filter(
            or_(
                Applicant.ho_ten.ilike(like),
                Applicant.ma_ho_so.ilike(like),
                Applicant.ma_so_hv.ilike(like),
            )
        )

    total = query.count()
    rows = (
        query.order_by(Applicant.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    return {
        "items": [
            {
                "ma_so_hv": a.ma_so_hv,
                "ma_ho_so": a.ma_ho_so,
                "ho_ten": a.ho_ten,
                "email_hoc_vien": getattr(a, "email_hoc_vien", None),
                "ngay_nhan_hs": a.ngay_nhan_hs.isoformat() if a.ngay_nhan_hs else None,
                "dot": a.dot,
                "nganh_nhap_hoc": getattr(a, "nganh_nhap_hoc", None),
                "khoa": getattr(a, "khoa", None),
                "nguoi_nhan_ky_ten": getattr(a, "nguoi_nhan_ky_ten", None),
            }
            for a in rows
        ],
        "page": page,
        "size": size,
        "total": total,
    }

# ================= API find theo mã hồ sơ (giữ tương thích) =================
@router.get("/find")
@router.get("/find/")
def find_by_ma_ho_so(
    ma_ho_so: str = Query(...),
    db: Session = Depends(get_db),
    me=Depends(require_roles("Admin", "NhanVien", "CongTacVien")),
):
    code = (ma_ho_so or "").strip()
    a = (
        db.query(Applicant)
        .filter(Applicant.ma_ho_so == code)
        .order_by(Applicant.created_at.desc())   # chọn bản mới nhất nếu trùng
        .first()
    )
    if not a:
        raise HTTPException(404, "Not Found")

    docs = db.query(ApplicantDoc).filter_by(applicant_ma_so_hv=a.ma_so_hv).all()
    q = db.query(ChecklistItem).filter(ChecklistItem.version_id == a.checklist_version_id)
    q = q.order_by(getattr(ChecklistItem, "order_no", ChecklistItem.id).asc())
    items = q.all()

    return {
        "ma_so_hv": a.ma_so_hv,
        "ma_ho_so": a.ma_ho_so,
        "ngay_nhan_hs": a.ngay_nhan_hs.isoformat() if a.ngay_nhan_hs else None,
        "ho_ten": a.ho_ten,
        "email_hoc_vien": getattr(a, "email_hoc_vien", None),
        "ngay_sinh": (a.ngay_sinh if isinstance(a.ngay_sinh, str) else (a.ngay_sinh.isoformat() if a.ngay_sinh else None)),
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

# ================= UPDATE by MSSV =================
@router.put("/{ma_so_hv}")
def update_applicant(ma_so_hv: str, body: dict = Body(...), db: Session = Depends(get_db), me=Depends(require_roles("Admin", "NhanVien", "CongTacVien"))):
    ensure_mssv(ma_so_hv)
    a = db.query(Applicant).filter(Applicant.ma_so_hv == ma_so_hv).first()
    if not a:
        raise HTTPException(404, "Applicant not found")

    def has(k): return k in body and body[k] is not None
    def get(k, default=None): return body.get(k, default)

    # Không cho đổi MSSV
    if has("ma_so_hv") and get("ma_so_hv") != ma_so_hv:
        raise HTTPException(400, "Không được phép thay đổi MSSV (ma_so_hv).")

    # ✅ Cho phép ma_ho_so trùng, chỉ cần không rỗng nếu có gửi
    if has("ma_ho_so"):
        new_code = (get("ma_ho_so") or "").strip()
        if not new_code:
            raise HTTPException(400, "ma_ho_so không được để trống.")
        a.ma_ho_so = new_code

    # Ngày
    if has("ngay_nhan_hs"): a.ngay_nhan_hs = _parse_date_flexible(get("ngay_nhan_hs"))
    if has("ngay_sinh"):    a.ngay_sinh    = _parse_date_flexible(get("ngay_sinh"))

    # Text
    for f in ("ho_ten","email_hoc_vien","so_dt","nganh_nhap_hoc","dot","khoa","da_tn_truoc_do","ghi_chu"):
        if has(f):
            setattr(a, f, get(f))

    a.nguoi_nhan_ky_ten = (getattr(me, "full_name", None) or getattr(me, "username", None))

    # Docs (ghi đè theo số lượng, 0 => xoá)
    if has("docs"):
        existing = {d.code: d for d in db.query(ApplicantDoc).filter_by(applicant_ma_so_hv=a.ma_so_hv).all()}
        for d in get("docs") or []:
            code = d.get("code") if isinstance(d, dict) else getattr(d, "code", None)
            sl   = d.get("so_luong") if isinstance(d, dict) else getattr(d, "so_luong", None)
            if code is None or sl is None:
                continue
            sl = int(sl)
            if sl <= 0:
                if code in existing: db.delete(existing[code])
            else:
                if code in existing:
                    existing[code].so_luong = sl
                else:
                    db.add(ApplicantDoc(applicant_ma_so_hv=a.ma_so_hv, code=code, so_luong=sl))

    db.commit()
    return {"ok": True, "ma_so_hv": a.ma_so_hv, "ma_ho_so": a.ma_ho_so}


# ================= DELETE by MSSV =================

@router.delete("/{ma_so_hv}", status_code=status.HTTP_204_NO_CONTENT)
def delete_applicant(ma_so_hv: str, db: Session = Depends(get_db)):
    ensure_mssv(ma_so_hv)
    a = db.query(Applicant).filter(Applicant.ma_so_hv == ma_so_hv).first()
    if not a:
        raise HTTPException(404, "Applicant not found")
    # Docs có ondelete=cascade; đoạn dưới an toàn nếu DB chưa bật
    db.query(ApplicantDoc).filter_by(applicant_ma_so_hv=a.ma_so_hv).delete(synchronize_session=False)
    db.delete(a)
    db.commit()
    return

# ================= PRINT (A4, A5) by MSSV =================

def _do_print(ma_so_hv: str, mark_printed: bool, db: Session, a5: bool = False):
    from app.services.pdf_service import render_single_pdf, render_single_pdf_a5

    ensure_mssv(ma_so_hv)
    a = db.query(Applicant).filter(Applicant.ma_so_hv == ma_so_hv).first()
    if not a:
        raise HTTPException(404, "Applicant not found")

    q = db.query(ChecklistItem).filter(ChecklistItem.version_id == a.checklist_version_id)
    if hasattr(ChecklistItem, "order_no"):
        q = q.order_by(getattr(ChecklistItem, "order_no").asc())
    else:
        q = q.order_by(ChecklistItem.id.asc())
    items = q.all()

    docs = db.query(ApplicantDoc).filter(ApplicantDoc.applicant_ma_so_hv == a.ma_so_hv).all()
    pdf_bytes = (render_single_pdf_a5 if a5 else render_single_pdf)(a, items, docs)

    if mark_printed:
        a.printed = True
        a.status = "printed"
        db.commit()

    filename = f"HS_{a.ma_ho_so or a.ma_so_hv}{'_A5' if a5 else ''}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )

@router.get("/{ma_so_hv}/print")
def print_applicant_now(ma_so_hv: str, mark_printed: bool = Query(False), db: Session = Depends(get_db)):
    return _do_print(ma_so_hv, mark_printed, db, a5=False)

@router.post("/{ma_so_hv}/print")
def print_applicant_now_post(ma_so_hv: str, mark_printed: bool = Query(True), db: Session = Depends(get_db)):
    return _do_print(ma_so_hv, mark_printed, db, a5=False)

@router.get("/{ma_so_hv}/print-a5")
def print_applicant_a5(ma_so_hv: str, mark_printed: bool = Query(False), db: Session = Depends(get_db)):
    return _do_print(ma_so_hv, mark_printed, db, a5=True)

@router.post("/{ma_so_hv}/print-a5")
def print_applicant_a5_post(ma_so_hv: str, mark_printed: bool = Query(True), db: Session = Depends(get_db)):
    return _do_print(ma_so_hv, mark_printed, db, a5=True)

# ================= Recent =================

@router.get("/recent")
def get_recent_applicants(db: Session = Depends(get_db), limit: int = 50):
    rows = db.query(Applicant).order_by(Applicant.created_at.desc()).limit(limit).all()
    return [{"ma_so_hv": a.ma_so_hv, "ma_ho_so": a.ma_ho_so, "ho_ten": a.ho_ten} for a in rows]
