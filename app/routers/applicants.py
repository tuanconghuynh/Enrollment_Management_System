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
        raise HTTPException(status_code=422, detail="MSSV phải gồm đúng 10 chữ số.")

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
    payload: dict = Body(...),  # <- dùng dict để tự parse, tránh 422 của Pydantic
    db: Session = Depends(get_db),
    me=Depends(require_roles("Admin", "NhanVien", "CongTacVien")),
):
    # Checklist version
    version_name = (payload.get("checklist_version_name") or "").strip() or "v1"
    v = db.query(ChecklistVersion).filter(
        ChecklistVersion.version_name == version_name
    ).first()
    if not v:
        raise HTTPException(400, "Checklist version không tồn tại")

    # Lấy & kiểm tra MSSV (10 số)
    ma_so_hv = (payload.get("ma_so_hv") or "").strip()
    ensure_mssv(ma_so_hv)  # nếu sai -> 422 với thông điệp rõ ràng

    # Trường bắt buộc cho tạo hồ sơ
    ma_ho_so = (payload.get("ma_ho_so") or "").strip()
    ho_ten   = (payload.get("ho_ten") or "").strip()
    ngay_nhan_hs = _parse_date_flexible(payload.get("ngay_nhan_hs"))

    if not ma_ho_so:
        raise HTTPException(422, "Thiếu trường bắt buộc: ma_ho_so")
    if not ho_ten:
        raise HTTPException(422, "Thiếu trường bắt buộc: ho_ten")
    if not ngay_nhan_hs:
        raise HTTPException(422, "Thiếu trường bắt buộc: ngay_nhan_hs (dd/MM/YYYY hoặc YYYY-MM-DD)")

    # Cho phép trùng MA_HO_SO -> KHÔNG kiểm tra unique ma_ho_so nữa
    # Vẫn phải đảm bảo MSSV không trùng
    existed_mssv = db.query(Applicant).filter(Applicant.ma_so_hv == ma_so_hv).first()
    if existed_mssv:
        raise HTTPException(409, "MSSV (ma_so_hv) đã tồn tại")

    a = Applicant(
        ma_so_hv=ma_so_hv,
        ma_ho_so=ma_ho_so,
        ngay_nhan_hs=ngay_nhan_hs,
        ho_ten=ho_ten,
        email_hoc_vien=payload.get("email_hoc_vien"),
        ngay_sinh=_parse_date_flexible(payload.get("ngay_sinh")),
        so_dt=payload.get("so_dt"),
        nganh_nhap_hoc=payload.get("nganh_nhap_hoc"),
        dot=payload.get("dot"),
        khoa=payload.get("khoa"),
        da_tn_truoc_do=payload.get("da_tn_truoc_do"),
        ghi_chu=payload.get("ghi_chu"),
        nguoi_nhan_ky_ten=(getattr(me, "full_name", None) or getattr(me, "username", None)),
        checklist_version_id=v.id,
        status="saved",
        printed=False,
    )
    db.add(a)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        # Rất có thể do PK/Unique MSSV (ma_so_hv) đụng; trả thông điệp rõ ràng
        raise HTTPException(409, "MSSV (ma_so_hv) đã tồn tại")

    # Docs (nếu có) – để trống cũng không sao
    docs = (payload.get("docs") or [])
    for d in docs:
        code = d.get("code") if isinstance(d, dict) else getattr(d, "code", None)
        sl   = d.get("so_luong") if isinstance(d, dict) else getattr(d, "so_luong", None)
        if sl in (None, ""):
            continue
        db.add(ApplicantDoc(applicant_ma_so_hv=a.ma_so_hv, code=code, so_luong=int(sl)))

    db.commit()
    return {
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
def update_applicant(
    ma_so_hv: str,
    body: dict = Body(...),
    db: Session = Depends(get_db),
    me=Depends(require_roles("Admin", "NhanVien", "CongTacVien")),
):
    ensure_mssv(ma_so_hv)

    a = db.query(Applicant).filter(Applicant.ma_so_hv == ma_so_hv).first()
    if not a:
        raise HTTPException(404, "Applicant not found")

    # -------- helpers ----------
    def has(k: str) -> bool:
        # có key trong body dù giá trị là "" (để cho phép xóa)
        return k in body

    def get(k: str, default=None):
        return body.get(k, default)

    def str_or_none(v):
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            return s if s != "" else None
        return v

    # Cho phép đổi MSSV nếu chưa bị trùng
    if has("ma_so_hv"):
        new_mssv = str(get("ma_so_hv") or "").strip()
        if new_mssv and new_mssv != ma_so_hv:
            # kiểm tra xem MSSV mới có trùng hồ sơ khác không
            existed = db.query(Applicant).filter(Applicant.ma_so_hv == new_mssv).first()
            if existed:
                raise HTTPException(409, "MSSV mới đã tồn tại trong hệ thống.")
            # cập nhật luôn khóa chính (cho phép đổi)
            a.ma_so_hv = new_mssv

    # ma_ho_so: CHO PHÉP TRÙNG & không cho phép xóa mã HS
    if has("ma_ho_so"):
        new_code = (str(get("ma_ho_so") or "").strip())
        if new_code == "":
            raise HTTPException(400, "Mã HS không được để trống.")
        a.ma_ho_so = new_code

    # Ngày: "" -> None, parse linh hoạt
    if has("ngay_nhan_hs"):
        a.ngay_nhan_hs = _parse_date_flexible(get("ngay_nhan_hs"))
    if has("ngay_sinh"):
        a.ngay_sinh = _parse_date_flexible(get("ngay_sinh"))

    # Text fields: "" -> None
    for f in ("ho_ten", "email_hoc_vien", "so_dt",
              "nganh_nhap_hoc", "dot", "khoa",
              "da_tn_truoc_do", "ghi_chu"):
        if has(f):
            setattr(a, f, str_or_none(get(f)))

    # Lưu người cập nhật gần nhất
    a.nguoi_nhan_ky_ten = (getattr(me, "full_name", None) or getattr(me, "username", None))

    # Docs: ghi đè theo số lượng; <=0 hoặc None -> xóa
    if has("docs"):
        existing = {
            d.code: d
            for d in db.query(ApplicantDoc).filter_by(applicant_ma_so_hv=a.ma_so_hv).all()
        }
        docs_in = get("docs") or []
        for d in docs_in:
            # hỗ trợ dict hoặc pydantic
            code = (d.get("code") if isinstance(d, dict) else getattr(d, "code", None)) or None
            sl   =  d.get("so_luong") if isinstance(d, dict) else getattr(d, "so_luong", None)

            if not code:   # thiếu code => bỏ qua
                continue

            try:
                sl_int = int(sl) if sl is not None else 0
            except Exception:
                sl_int = 0

            if sl_int <= 0:
                if code in existing:
                    db.delete(existing[code])
            else:
                if code in existing:
                    existing[code].so_luong = sl_int
                else:
                    db.add(ApplicantDoc(
                        applicant_ma_so_hv=a.ma_so_hv,
                        code=code,
                        so_luong=sl_int
                    ))

    db.commit()
    return {
        "ok": True,
        "ma_so_hv": a.ma_so_hv,
        "ma_ho_so": a.ma_ho_so,
        "ho_ten": a.ho_ten,
        "ngay_nhan_hs": a.ngay_nhan_hs.isoformat() if a.ngay_nhan_hs else None,
    }


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
