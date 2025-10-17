# app/routers/applicants.py
from __future__ import annotations

import io
import re
import os
import hmac
import json
import hashlib
from datetime import datetime, date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Body, status, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import or_, func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.db.session import get_db
from app.models.applicant import Applicant, ApplicantDoc
from app.models.checklist import ChecklistItem, ChecklistVersion
from app.routers.auth import require_roles

# --- Audit service: ghi log vào bảng audit_logs ---
from app.services.audit import write_audit  # cần file services.audit như em đã gửi

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

DELETE_KEY_SECRET = os.getenv("DELETE_KEY_SECRET", "delete-dev")

def verify_delete_key(key: str) -> bool:
    """
    Xác thực key xóa: HMAC-SHA256("ALLOW_DELETE", DELETE_KEY_SECRET).
    Sinh key hợp lệ để test:
      python -c "import os,hmac,hashlib;print(hmac.new(os.getenv('DELETE_KEY_SECRET','delete-dev').encode(), b'ALLOW_DELETE', hashlib.sha256).hexdigest())"
    """
    digest = hmac.new(DELETE_KEY_SECRET.encode(), b"ALLOW_DELETE", hashlib.sha256).hexdigest()
    return hmac.compare_digest(key or "", digest)

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

def snapshot_applicant(a: Applicant) -> dict:
    """Chụp nhanh bản ghi để ghi audit (prev/new)."""
    if not a:
        return {}
    def iso(d):
        if not d: return None
        if isinstance(d, datetime): return d.isoformat()
        if isinstance(d, date): return datetime.combine(d, datetime.min.time()).isoformat()
        return str(d)
    return {
        "ma_so_hv": a.ma_so_hv,
        "ma_ho_so": a.ma_ho_so,
        "ho_ten": a.ho_ten,
        "email_hoc_vien": getattr(a, "email_hoc_vien", None),
        "ngay_nhan_hs": iso(a.ngay_nhan_hs),
        "ngay_sinh": iso(a.ngay_sinh),
        "so_dt": a.so_dt,
        "nganh_nhap_hoc": getattr(a, "nganh_nhap_hoc", None),
        "dot": getattr(a, "dot", None),
        "khoa": getattr(a, "khoa", None),
        "da_tn_truoc_do": getattr(a, "da_tn_truoc_do", None),
        "ghi_chu": getattr(a, "ghi_chu", None),
        "nguoi_nhan_ky_ten": getattr(a, "nguoi_nhan_ky_ten", None),
        "status": getattr(a, "status", None),
        "printed": getattr(a, "printed", None),
        "checklist_version_id": getattr(a, "checklist_version_id", None),
        # các cột soft-delete (nếu có)
        "deleted_at": iso(getattr(a, "deleted_at", None)),
        "deleted_by": getattr(a, "deleted_by", None),
        "deleted_reason": getattr(a, "deleted_reason", None),
    }

# ================= GET by code =================
@router.get("/by-code/{key}")
def get_by_code(
    key: str,
    request: Request,
    db: Session = Depends(get_db),
    me=Depends(require_roles("Admin", "NhanVien", "CongTacVien")),
):
    k = (key or "").strip()
    if not k:
        write_audit(db, action="READ", target_type="Applicant", target_id=None,
                    status="FAILURE", new_values={"reason":"missing key"}, request=request)
        db.commit()
        raise HTTPException(400, "Thiếu mã tra cứu")

    a = (
        db.query(Applicant)
        .filter(func.lower(Applicant.ma_ho_so) == k.lower())
        .order_by(Applicant.created_at.desc())
        .first()
    )
    if not a and MSSV_REGEX.fullmatch(k):
        a = db.query(Applicant).filter(Applicant.ma_so_hv == k).first()
    if not a:
        a = (
            db.query(Applicant)
            .filter(Applicant.ma_ho_so.ilike(k))
            .order_by(Applicant.created_at.desc())
            .first()
        )

    if not a:
        write_audit(db, action="READ", target_type="Applicant", target_id=k, status="FAILURE", request=request)
        db.commit()
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

    write_audit(db, action="READ", target_type="Applicant", target_id=a.ma_so_hv, status="SUCCESS", request=request)
    db.commit()

    return {
        "applicant": applicant_payload,
        "docs": [{"code": d.code, "so_luong": int(d.so_luong or 0)} for d in docs],
    }

@router.get("/by-mshv/{ma_so_hv}")
def get_by_mshv(
    ma_so_hv: str,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_roles("Admin", "NhanVien", "CongTacVien")),
):
    key = (ma_so_hv or "").strip()
    if not key:
        write_audit(db, action="READ", target_type="Applicant", target_id=None, status="FAILURE", request=request)
        db.commit()
        raise HTTPException(status_code=400, detail="Thiếu MSHV")

    a = db.query(Applicant).filter(func.lower(Applicant.ma_so_hv) == key.lower()).first()
    if not a:
        a = db.query(Applicant).filter(Applicant.ma_so_hv.ilike(f"%{key}%")).first()
    if not a:
        write_audit(db, action="READ", target_type="Applicant", target_id=key, status="FAILURE", request=request)
        db.commit()
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

    write_audit(db, action="READ", target_type="Applicant", target_id=a.ma_so_hv, status="SUCCESS", request=request)
    db.commit()

    return {
        "applicant": applicant_payload,
        "docs": [{"code": d.code, "so_luong": int(d.so_luong or 0)} for d in docs],
    }

# ================= CREATE =================
@router.post("", status_code=201)
@router.post("/", status_code=201)
def create_applicant(
    request: Request,
    payload: dict = Body(...),  # <- dùng dict để tự parse, tránh 422 của Pydantic
    db: Session = Depends(get_db),
    me=Depends(require_roles("Admin", "NhanVien", "CongTacVien")),
):
    version_name = (payload.get("checklist_version_name") or "").strip() or "v1"
    v = db.query(ChecklistVersion).filter(
        ChecklistVersion.version_name == version_name
    ).first()
    if not v:
        write_audit(db, action="CREATE", target_type="Applicant", target_id=None,
                    status="FAILURE", new_values={"reason":"Checklist version not found", "version":version_name}, request=request)
        db.commit()
        raise HTTPException(400, "Checklist version không tồn tại")

    ma_so_hv = (payload.get("ma_so_hv") or "").strip()
    ensure_mssv(ma_so_hv)

    ma_ho_so = (payload.get("ma_ho_so") or "").strip()
    ho_ten   = (payload.get("ho_ten") or "").strip()
    ngay_nhan_hs = _parse_date_flexible(payload.get("ngay_nhan_hs"))

    if not ma_ho_so:
        raise HTTPException(422, "Thiếu trường bắt buộc: ma_ho_so")
    if not ho_ten:
        raise HTTPException(422, "Thiếu trường bắt buộc: ho_ten")
    if not ngay_nhan_hs:
        raise HTTPException(422, "Thiếu trường bắt buộc: ngay_nhan_hs (dd/MM/YYYY hoặc YYYY-MM-DD)")

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
    prev_snapshot = {}
    db.add(a)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        write_audit(db, action="CREATE", target_type="Applicant", target_id=ma_so_hv,
                    status="FAILURE", new_values={"error":"IntegrityError"}, request=request)
        db.commit()
        raise HTTPException(409, "Mã số HV đã tồn tại")

    docs = (payload.get("docs") or [])
    for d in docs:
        code = d.get("code") if isinstance(d, dict) else getattr(d, "code", None)
        sl   = d.get("so_luong") if isinstance(d, dict) else getattr(d, "so_luong", None)
        if sl in (None, ""):
            continue
        db.add(ApplicantDoc(applicant_ma_so_hv=a.ma_so_hv, code=code, so_luong=int(sl)))

    db.commit()

    write_audit(db, action="CREATE", target_type="Applicant", target_id=a.ma_so_hv,
                prev_values=prev_snapshot, new_values=snapshot_applicant(a), status="SUCCESS", request=request)
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

    # Ẩn record đã soft-delete (nếu schema có cột này)
    if hasattr(Applicant, "deleted_at"):
        query = query.filter(getattr(Applicant, "deleted_at").is_(None))

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
        "ngay_sinh": (a.ngay_sinh if isinstance(a, "ngay_sinh", str) else (a.ngay_sinh.isoformat() if a.ngay_sinh else None)) if hasattr(a, "ngay_sinh") else None,  # giữ tương thích
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
    request: Request,
    body: dict = Body(...),
    db: Session = Depends(get_db),
    me=Depends(require_roles("Admin", "NhanVien", "CongTacVien")),
):
    ensure_mssv(ma_so_hv)

    a = db.query(Applicant).filter(Applicant.ma_so_hv == ma_so_hv).first()
    if not a:
        raise HTTPException(404, "Applicant not found")

    before = snapshot_applicant(a)

    # -------- helpers ----------
    def has(k: str) -> bool:
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
            existed = db.query(Applicant).filter(Applicant.ma_so_hv == new_mssv).first()
            if existed:
                raise HTTPException(409, "MSSV mới đã tồn tại trong hệ thống.")
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

    # Docs
    if has("docs"):
        existing = {
            d.code: d
            for d in db.query(ApplicantDoc).filter_by(applicant_ma_so_hv=a.ma_so_hv).all()
        }
        docs_in = get("docs") or []
        for d in docs_in:
            code = (d.get("code") if isinstance(d, dict) else getattr(d, "code", None)) or None
            sl   =  d.get("so_luong") if isinstance(d, dict) else getattr(d, "so_luong", None)

            if not code:
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

    after = snapshot_applicant(a)
    write_audit(db, action="UPDATE", target_type="Applicant", target_id=a.ma_so_hv,
                prev_values=before, new_values=after, status="SUCCESS", request=request)
    db.commit()

    return {
        "ok": True,
        "ma_so_hv": a.ma_so_hv,
        "ma_ho_so": a.ma_ho_so,
        "ho_ten": a.ho_ten,
        "ngay_nhan_hs": a.ngay_nhan_hs.isoformat() if a.ngay_nhan_hs else None,
    }

# ================= DELETE by MSSV (SOFT-DELETE, chỉ cần lý do) =================
@router.delete("/{ma_so_hv}", status_code=status.HTTP_204_NO_CONTENT)
def delete_applicant(
    ma_so_hv: str,
    request: Request,
    body: dict | None = Body(None, embed=False),
    db: Session = Depends(get_db),
    me=Depends(require_roles("Admin", "NhanVien", "CongTacVien")),
):
    """
    Soft-delete: cần {"reason": "..."} trong body.
    Trả 204 No Content để FE ẩn dòng ngay, không cần reload.
    """
    ensure_mssv(ma_so_hv)

    a = db.query(Applicant).filter(Applicant.ma_so_hv == ma_so_hv).first()
    if not a:
        raise HTTPException(404, "Applicant not found")

    reason = (body or {}).get("reason") if isinstance(body, dict) else None
    if not reason or not str(reason).strip():
        raise HTTPException(400, "Thiếu lý do xoá (reason)")
    reason = str(reason).strip()[:1000]

    before = snapshot_applicant(a)

    # Idempotent: nếu đã có deleted_at thì chỉ cập nhật lý do/người xoá
    now = datetime.utcnow()
    if not getattr(a, "deleted_at", None):
        a.deleted_at = now
    # luôn set/ghi lại người xoá theo actor hiện tại
    a.deleted_by = getattr(me, "full_name", None) or getattr(me, "username", None) or "ADMIN"
    a.deleted_reason = reason

    db.add(a)
    db.commit()

    # 🔧 Ghi audit đầy đủ để FE hiển thị "Thời điểm xóa" / "Người xóa"
    write_audit(
        db,
        action="DELETE_SOFT",
        target_type="Applicant",
        target_id=ma_so_hv,
        prev_values=before,
        new_values={
            "deleted_at": _to_iso(getattr(a, "deleted_at", None)),
            "deleted_by": getattr(a, "deleted_by", None),
            "deleted_reason": getattr(a, "deleted_reason", None),
        },
        status="SUCCESS",
        request=request,
    )
    db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)

# ================= PRINT (A4, A5) by MSSV =================

def _do_print(ma_so_hv: str, mark_printed: bool, db: Session, request: Request, a5: bool = False):
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
        # log đánh dấu in
        write_audit(db, action="PRINT", target_type="Applicant", target_id=a.ma_so_hv,
                    prev_values={}, new_values={"printed": True, "a5": a5}, status="SUCCESS", request=request)
        db.commit()

    filename = f"HS_{a.ma_ho_so or a.ma_so_hv}{'_A5' if a5 else ''}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename=\"{filename}\"'},
    )

@router.get("/{ma_so_hv}/print")
def print_applicant_now(
    ma_so_hv: str,
    request: Request,
    mark_printed: bool = Query(False),
    db: Session = Depends(get_db),
):
    return _do_print(ma_so_hv, mark_printed, db, request=request, a5=False)

@router.post("/{ma_so_hv}/print")
def print_applicant_now_post(
    ma_so_hv: str,
    request: Request,
    mark_printed: bool = Query(True),
    db: Session = Depends(get_db),
):
    return _do_print(ma_so_hv, mark_printed, db, request=request, a5=False)

@router.get("/{ma_so_hv}/print-a5")
def print_applicant_a5(
    ma_so_hv: str,
    request: Request,
    mark_printed: bool = Query(False),
    db: Session = Depends(get_db),
):
    return _do_print(ma_so_hv, mark_printed, db, request=request, a5=True)

@router.post("/{ma_so_hv}/print-a5")
def print_applicant_a5_post(
    ma_so_hv: str,
    request: Request,
    mark_printed: bool = Query(True),
    db: Session = Depends(get_db),
):
    return _do_print(ma_so_hv, mark_printed, db, request=request, a5=True)

# ================= Recent =================
@router.get("/recent")
def get_recent_applicants(db: Session = Depends(get_db), limit: int = 50):
    rows = db.query(Applicant).order_by(Applicant.created_at.desc()).limit(limit).all()
    return [{"ma_so_hv": a.ma_so_hv, "ma_ho_so": a.ma_ho_so, "ho_ten": a.ho_ten} for a in rows]
