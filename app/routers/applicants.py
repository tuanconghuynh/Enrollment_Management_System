# app/routers/applicants.py
from __future__ import annotations

import io, re, os, hmac, json, hashlib
from datetime import datetime, date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Body, status, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import literal, or_, and_, func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.db.session import get_db
from app.models.applicant import Applicant, ApplicantDoc
from app.models.checklist import ChecklistItem, ChecklistVersion
from app.routers.auth import require_roles
from app.services.audit import write_audit
import re

from app.utils.soft_delete import exclude_deleted

try:
    from app.schemas.applicant import ApplicantIn, ApplicantOut
except Exception:
    ApplicantIn = dict  # type: ignore
    ApplicantOut = dict  # type: ignore

router = APIRouter(prefix="/applicants", tags=["Applicants"])

# ====== Lý do cập nhật (preset) ======
UPDATE_REASON_CHOICES = {
    "capnhat_thongtin": "Cập nhật thông tin học viên",
    "capnhat_hoso_moi": "Cập nhật hồ sơ mới",
    "bosung_hoso": "Bổ sung hồ sơ",
    "capnhat_chungchi": "Cập nhật chứng chỉ",
    "chinhsua_hoso": "Chỉnh sửa hồ sơ",
    "khac": "Lý do khác",
}

def _validate_update_reason(data) -> str:
    """
    Hỗ trợ 2 kiểu truyền từ FE:
      1) update_reason: {"key": "...", "text": "..."}  # chuẩn
      2) update_reason_key="...", update_reason_text="..."  # tương thích cũ
    Trả về chuỗi mô tả lý do đã hợp lệ, hoặc raise HTTPException(400).
    """
    from fastapi import HTTPException

    key = None
    text = None

    if isinstance(data, dict):
        key = (data.get("key") or "").strip()
        text = (data.get("text") or "").strip()
    elif isinstance(data, str):
        key = data.strip()
    elif data is None:
        pass

    if not key:
        raise HTTPException(400, "Thiếu lý do cập nhật (update_reason.key).")

    label = UPDATE_REASON_CHOICES.get(key)
    if not label:
        raise HTTPException(400, "Lý do cập nhật không hợp lệ.")

    if key == "khac":
        if not text:
            raise HTTPException(400, "Vui lòng nhập nội dung cho 'Lý do khác'.")
        label = f"Lý do khác: {text}"

    return label

# 🆕 Regex lấy số thứ tự 4 chữ số cuối mã hồ sơ
SEQ4_RE = re.compile(r"(\d{4})$")

def _next_seq4(db: Session, khoa: Optional[str], dot: Optional[str]) -> str:
    q = db.query(Applicant)
    if khoa: q = q.filter(Applicant.khoa == str(khoa).strip())
    if dot:  q = q.filter(Applicant.dot  == str(dot).strip())

    maxn = 0
    for a in q.all():
        m = SEQ4_RE.search(str(getattr(a, "ma_ho_so", "") or ""))
        if m:
            try:
                n = int(m.group(1))
                if n > maxn: maxn = n
            except: pass
    return f"{(maxn + 1):04d}"

# ================= Helpers =================
DATE_DMY = re.compile(r"^(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})$")
DATE_YMD = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
MSSV_REGEX = re.compile(r"^\d{10}$")

DELETE_KEY_SECRET = os.getenv("DELETE_KEY_SECRET", "delete-dev")

def verify_delete_key(key: str) -> bool:
    """
    Xác thực key xóa: HMAC-SHA256("ALLOW_DELETE", DELETE_KEY_SECRET).
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

# 🆕 Chuẩn hóa giới tính
def _normalize_gender(v):
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in {"nam", "m", "male", "1", "true"}:
        return "Nam"
    if s in {"nữ", "nu", "f", "female", "0", "false"}:
        return "Nữ"
    # nếu FE gửi "Nam"/"Nữ"/khác đúng ý thì giữ nguyên
    return v

def snapshot_applicant(a: Applicant) -> dict:
    """Chụp nhanh bản ghi để ghi audit (prev/new)."""
    if not a:
        return {}

    def iso(d):
        if not d:
            return None
        if isinstance(d, datetime):
            return d.isoformat()
        if isinstance(d, date):
            return datetime.combine(d, datetime.min.time()).isoformat()
        return str(d)

    return {
        "ma_so_hv": a.ma_so_hv,
        "ma_ho_so": a.ma_ho_so,
        "ho_ten": a.ho_ten,
        "ho_dem": getattr(a, "ho_dem", None),
        "ten": getattr(a, "ten", None),
        "email_hoc_vien": getattr(a, "email_hoc_vien", None),
        "ngay_nhan_hs": iso(a.ngay_nhan_hs),
        "ngay_sinh": iso(a.ngay_sinh),
        "so_dt": a.so_dt,
        # trả về theo key nganh_nhap_hoc — map cả khi DB dùng cột 'nganh'
        "nganh_nhap_hoc": getattr(a, "nganh_nhap_hoc", None) if hasattr(a, "nganh_nhap_hoc") else getattr(a, "nganh", None),
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
        "gioi_tinh": getattr(a, "gioi_tinh", None),
        "dan_toc": getattr(a, "dan_toc", None),
    }

# 🆕 Helper: lấy map docs {code: so_luong}
def _docs_map(db: Session, mshv: str) -> dict[str, int]:
    rows = db.query(ApplicantDoc).filter_by(applicant_ma_so_hv=mshv).all()
    return {d.code: int(d.so_luong or 0) for d in rows}

def _split_vn_name(fullname: str) -> tuple[str, str]:
    s = " ".join((fullname or "").split())
    if not s:
        return "", ""
    parts = s.split(" ")
    if len(parts) == 1:
        # 1 từ -> xem như tên gọi, họ đệm rỗng
        return "", parts[0]
    return " ".join(parts[:-1]), parts[-1]

def _display_name(ho_dem: Optional[str], ten: Optional[str], fallback_full: Optional[str] = None) -> str:
    ln = (ho_dem or "").strip()
    fn = (ten or "").strip()
    if ln or fn:
        return (ln + " " + fn).strip()
    return (fallback_full or "").strip()

# ================= GET by code =================
@router.get("/by-code/{key}")
def get_by_code(
    key: str,
    request: Request,
    db: Session = Depends(get_db),
    me=Depends(require_roles("Admin", "NhanVien", "CongTacVien", "Manager")),
):
    k = (key or "").strip()
    if not k:
        write_audit(
            db,
            action="READ",
            target_type="Applicant",
            target_id=None,
            status="FAILURE",
            new_values={"reason": "missing key"},
            request=request
        )
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
            .filter(Applicant.ma_ho_so.ilike(f"%{k}%"))
            .order_by(Applicant.created_at.desc())
            .first()
        )

    if not a:
        write_audit(db, action="READ", target_type="Applicant", target_id=k,
                    status="FAILURE", request=request)
        db.commit()
        raise HTTPException(
            404,
            detail="Không tìm thấy hồ sơ phù hợp với mã tra cứu đã nhập."
        )

    # Chặn hồ sơ đã xoá mềm
    if hasattr(Applicant, "deleted_at") and getattr(a, "deleted_at", None):
        raise HTTPException(410, "Hồ sơ đã bị xoá tạm.")

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
        "ho_dem": getattr(a, "ho_dem", None),
        "ten": getattr(a, "ten", None),
        "full_name": _display_name(getattr(a, "ho_dem", None), getattr(a, "ten", None), getattr(a, "ho_ten", None)),
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
        "gioi_tinh": getattr(a, "gioi_tinh", None),
        "dan_toc": getattr(a, "dan_toc", None),
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
    user=Depends(require_roles("Admin", "NhanVien", "CongTacVien", "Manager")),
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
        write_audit(db, action="READ", target_type="Applicant", target_id=key,
                    status="FAILURE", request=request)
        db.commit()
        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy học viên / hồ sơ nào với MSHV đã nhập."
        )

    # Chặn hồ sơ đã xoá mềm
    if hasattr(Applicant, "deleted_at") and getattr(a, "deleted_at", None):
        raise HTTPException(410, "Hồ sơ đã bị xoá tạm.")

    # ===== DOCS & CHECKLIST =====
    docs = db.query(ApplicantDoc).filter(
        ApplicantDoc.applicant_ma_so_hv == a.ma_so_hv
    ).all()
    docs_map = {d.code: int(d.so_luong or 0) for d in docs}

    # Lấy danh mục checklist của version hiện tại (nếu có)
    checklist_items = []
    if getattr(a, "checklist_version_id", None):
        q = db.query(ChecklistItem).filter(ChecklistItem.version_id == a.checklist_version_id)
        if hasattr(ChecklistItem, "order_no"):
            q = q.order_by(getattr(ChecklistItem, "order_no").asc())
        else:
            q = q.order_by(ChecklistItem.id.asc())
        items = q.all()

        for it in items:
            cnt = docs_map.get(it.code, 0)
            checklist_items.append({
                "code": it.code,
                "label": getattr(it, "display_name", None) or getattr(it, "name", None) or it.code,
                "order_no": getattr(it, "order_no", 0),
                "so_luong": cnt,
                "done": cnt > 0,
            })

    def pick(*names):
        for n in names:
            if hasattr(a, n):
                v = getattr(a, n)
                if v not in (None, ""):
                    return v
        return None

    def _to_dmy2(v):
        if not v:
            return None
        if isinstance(v, datetime):
            v = v.date()
        if isinstance(v, date):
            return f"{v.day:02d}/{v.month:02d}/{v.year:04d}"
        try:
            return datetime.fromisoformat(str(v)).strftime("%d/%m/%Y")
        except Exception:
            return str(v)

    def _to_iso2(v):
        if not v:
            return None
        if isinstance(v, datetime):
            return v.isoformat()
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
        "ma_so_hv": a.ma_so_hv,

        "ngay_nhan_hs": _to_dmy2(a.ngay_nhan_hs),
        "ngay_nhan_hs_iso": _to_iso2(a.ngay_nhan_hs),
        "ngay_sinh": _to_dmy2(a.ngay_sinh),
        "ngay_sinh_iso": _to_iso2(a.ngay_sinh),

        "ho_ten": a.ho_ten,
        "ho_dem": getattr(a, "ho_dem", None),
        "ten": getattr(a, "ten", None),
        "full_name": _display_name(
            getattr(a, "ho_dem", None),
            getattr(a, "ten", None),
            getattr(a, "ho_ten", None),
        ),

        "so_dt": a.so_dt,
        "email_hoc_vien": getattr(a, "email_hoc_vien", None),

        "nganh_nhap_hoc": pick("nganh_nhap_hoc", "nganh"),
        "dot": pick("dot", "dot_tuyen"),
        "khoa": pick("khoa", "khoa_hoc", "khoahoc", "nien_khoa"),
        "da_tn_truoc_do": a.da_tn_truoc_do,
        "ghi_chu": a.ghi_chu,
        "nguoi_nhan_ky_ten": pick("nguoi_nhan_ky_ten", "nguoi_nhan", "nguoi_ky"),

        "status": getattr(a, "status", None),
        "printed": getattr(a, "printed", None),
        "checklist_version_id": getattr(a, "checklist_version_id", None),

        # 🆕 giới tính & dân tộc
        "gioi_tinh": getattr(a, "gioi_tinh", None),
        "dan_toc": getattr(a, "dan_toc", None),

        # 🆕 nhật ký cập nhật
        "updated_at": _to_iso2(getattr(a, "updated_at", None)) if hasattr(a, "updated_at") else None,
        "updated_by": getattr(a, "updated_by", None)
                      or getattr(a, "nguoi_nhan_ky_ten", None),

        # 🆕 checklist đã map với docs
        "checklist": checklist_items,
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
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    me=Depends(require_roles("Admin", "NhanVien", "CongTacVien", "Manager")),
):
    version_name = (payload.get("checklist_version_name") or "").strip() or "v1"
    v = db.query(ChecklistVersion).filter(
        ChecklistVersion.version_name == version_name
    ).first()
    if not v:
        write_audit(
            db,
            action="CREATE",
            target_type="Applicant",
            target_id=None,
            status="FAILURE",
            new_values={"reason": "Checklist version not found", "version": version_name},
            request=request,
        )
        db.commit()
        raise HTTPException(400, "Checklist version không tồn tại")

      # ✅ MSSV vẫn bắt buộc 10 số
    ma_so_hv = (payload.get("ma_so_hv") or "").strip()
    ensure_mssv(ma_so_hv)

    # ✅ Mã hồ sơ: KHÔNG bắt buộc khi tạo mới
    raw_ma_hs = (payload.get("ma_ho_so") or "").strip()
    ma_ho_so = raw_ma_hs or None

    # ===== tên =====
    input_ho_dem = (payload.get("ho_dem") or "").strip()
    input_ten = (payload.get("ten") or "").strip()
    ho_ten = (payload.get("ho_ten") or "").strip()

    if not (input_ho_dem or input_ten):
        # nếu FE gửi mỗi ho_ten -> tách
        input_ho_dem, input_ten = _split_vn_name(ho_ten)

    # build full cho giai đoạn chuyển tiếp (vẫn còn cột ho_ten)
    full_built = _display_name(input_ho_dem, input_ten, ho_ten)

    ngay_nhan_hs = _parse_date_flexible(payload.get("ngay_nhan_hs"))

    # ❌ bỏ check bắt buộc Mã HS
    if not (input_ho_dem or input_ten or ho_ten):
        raise HTTPException(422, "Thiếu trường bắt buộc: Họ Và Tên")
    if not ngay_nhan_hs:
        raise HTTPException(422, "Thiếu trường bắt buộc: Ngày nhận hồ sơ (dd/MM/YYYY hoặc YYYY-MM-DD)")

    existed_mssv = db.query(Applicant).filter(Applicant.ma_so_hv == ma_so_hv).first()
    if existed_mssv:
        raise HTTPException(409, "Mã số học viên đã tồn tại!")

    _nganh_val = (payload.get("nganh_nhap_hoc") or payload.get("nganh") or None)

    a = Applicant(
        ma_so_hv=ma_so_hv,
        ma_ho_so=ma_ho_so,
        ngay_nhan_hs=ngay_nhan_hs,
        # ===== tên =====
        ho_ten=full_built or None,          # giữ tương thích
        ho_dem=input_ho_dem or None,        # tên tách đôi
        ten=input_ten or None,              
        # =================
        email_hoc_vien=payload.get("email_hoc_vien"),
        ngay_sinh=_parse_date_flexible(payload.get("ngay_sinh")),
        so_dt=payload.get("so_dt"),
        dot=payload.get("dot"),
        khoa=payload.get("khoa"),
        da_tn_truoc_do=payload.get("da_tn_truoc_do"),
        ghi_chu=payload.get("ghi_chu"),
        nguoi_nhan_ky_ten=(getattr(me, "full_name", None) or getattr(me, "username", None)),
        checklist_version_id=v.id,
        status="saved",
        printed=False,
        gioi_tinh=_normalize_gender(payload.get("gioi_tinh")),
        **({"dan_toc": payload.get("dan_toc")} if hasattr(Applicant, "dan_toc") else {}),
    )
    if hasattr(Applicant, "nganh_nhap_hoc"):
        a.nganh_nhap_hoc = _nganh_val
    elif hasattr(Applicant, "nganh"):
        a.nganh = _nganh_val

    prev_snapshot = {}
    db.add(a)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        write_audit(
            db,
            action="CREATE",
            target_type="Applicant",
            target_id=ma_so_hv,
            status="FAILURE",
            new_values={"error": "IntegrityError"},
            request=request,
        )
        db.commit()
        raise HTTPException(409, "Mã số HV đã tồn tại")

    docs = (payload.get("docs") or [])
    for d in docs:
        code = d.get("code") if isinstance(d, dict) else getattr(d, "code", None)
        sl = d.get("so_luong") if isinstance(d, dict) else getattr(d, "so_luong", None)
        if sl in (None, ""):
            continue
        db.add(ApplicantDoc(applicant_ma_so_hv=a.ma_so_hv, code=code, so_luong=int(sl)))

    db.commit()

    # 🆕 Audit CREATE kèm danh mục hồ sơ
    docs_after = _docs_map(db, a.ma_so_hv)
    write_audit(
        db,
        action="CREATE",
        target_type="Applicant",
        target_id=a.ma_so_hv,
        prev_values=prev_snapshot,
        new_values={**snapshot_applicant(a), "docs_after": docs_after},
        status="SUCCESS",
        request=request,
    )
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
    me=Depends(require_roles("Admin", "NhanVien", "CongTacVien", "Manager")),
):
    qn = (q or "").strip() or None

    # Bắt đầu query
    query = db.query(Applicant)

    # Ẩn toàn bộ hồ sơ đã bị xoá mềm (tự động nhận diện cột)
    query = exclude_deleted(Applicant, query)

    # Nếu có từ khoá tìm kiếm
    if qn:
        like = f"%{qn}%"
        # concat tên tách đôi (an toàn nếu cột chưa tồn tại trên DB cũ: dùng getattr)
        name_expr = func.concat(
            func.coalesce(Applicant.ho_dem, ""), literal(" "),  # Sửa ở đây
            func.coalesce(Applicant.ten, "")
        )
        query = query.filter(
            or_(
                Applicant.ho_ten.ilike(like),         # tương thích
                name_expr.ilike(like),                # 🆕 tìm theo ho_dem + ten
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
                "ho_dem": getattr(a, "ho_dem", None),
                "ten": getattr(a, "ten", None),
                "full_name": _display_name(getattr(a, "ho_dem", None), getattr(a, "ten", None), getattr(a, "ho_ten", None)),
                "ho_ten": a.ho_ten,
                "email_hoc_vien": getattr(a, "email_hoc_vien", None),
                "ngay_nhan_hs": a.ngay_nhan_hs.isoformat() if a.ngay_nhan_hs else None,
                "dot": a.dot,
                # ✅ luôn trả về theo key 'nganh_nhap_hoc'
                "nganh_nhap_hoc": getattr(a, "nganh_nhap_hoc", None) if hasattr(a, "nganh_nhap_hoc") else getattr(a, "nganh", None),
                "khoa": getattr(a, "khoa", None),
                "nguoi_nhan_ky_ten": getattr(a, "nguoi_nhan_ky_ten", None),
                # 🆕 giới tính
                "gioi_tinh": getattr(a, "gioi_tinh", None),
                # 🆕 dân tộc
                "dan_toc": getattr(a, "dan_toc", None),
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
    me=Depends(require_roles("Admin", "NhanVien", "CongTacVien", "Manager")),
):
    code = (ma_ho_so or "").strip()
    a = (
        db.query(Applicant)
        .filter(Applicant.ma_ho_so == code)
        .order_by(Applicant.created_at.desc())   # chọn bản mới nhất nếu trùng
        .first()
    )
    if not a:
        raise HTTPException(
            404,
            detail="Không tìm thấy hồ sơ với mã hồ sơ đã nhập."
        )

    # Chặn hồ sơ đã xoá mềm
    if hasattr(Applicant, "deleted_at") and getattr(a, "deleted_at", None):
        raise HTTPException(410, "Hồ sơ đã bị xoá tạm.")

    docs = db.query(ApplicantDoc).filter_by(applicant_ma_so_hv=a.ma_so_hv).all()
    q = db.query(ChecklistItem).filter(ChecklistItem.version_id == a.checklist_version_id)
    q = q.order_by(getattr(ChecklistItem, "order_no", ChecklistItem.id).asc())
    items = q.all()

    return {
        "ma_so_hv": a.ma_so_hv,
        "ma_ho_so": a.ma_ho_so,
        "ngay_nhan_hs": a.ngay_nhan_hs.isoformat() if a.ngay_nhan_hs else None,
        "ho_ten": a.ho_ten,
        "ho_dem": getattr(a, "ho_dem", None),
        "ten": getattr(a, "ten", None),
        "full_name": _display_name(getattr(a, "ho_dem", None), getattr(a, "ten", None), getattr(a, "ho_ten", None)),
        "email_hoc_vien": getattr(a, "email_hoc_vien", None),
        "ngay_sinh": (
            a.ngay_sinh if isinstance(getattr(a, "ngay_sinh", None), str)
            else (a.ngay_sinh.isoformat() if getattr(a, "ngay_sinh", None) else None)
        ) if hasattr(a, "ngay_sinh") else None,
        "so_dt": a.so_dt,
        # ✅ map về key chuẩn 'nganh_nhap_hoc'
        "nganh_nhap_hoc": getattr(a, "nganh_nhap_hoc", None) if hasattr(a, "nganh_nhap_hoc") else getattr(a, "nganh", None),
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
        "gioi_tinh": getattr(a, "gioi_tinh", None),
        "dan_toc": getattr(a, "dan_toc", None),
    }

# ================= UPDATE (có lý do) =================
@router.put("/{ma_so_hv}")
def update_applicant(
    ma_so_hv: str,
    request: Request,
    body: dict = Body(...),
    db: Session = Depends(get_db),
    me=Depends(require_roles("Admin", "NhanVien", "CongTacVien", "Manager")),
):
    ensure_mssv(ma_so_hv)

    # helpers cục bộ cho tên
    def _split_vn_name(fullname: str) -> tuple[str, str]:
        s = " ".join((fullname or "").split())
        if not s:
            return "", ""
        parts = s.split(" ")
        if len(parts) == 1:
            return "", parts[0]
        return " ".join(parts[:-1]), parts[-1]

    def _display_name(ho_dem: Optional[str], ten: Optional[str], fallback_full: Optional[str] = None) -> str:
        ln = (ho_dem or "").strip()
        fn = (ten or "").strip()
        if ln or fn:
            return (ln + " " + fn).strip()
        return (fallback_full or "").strip()

    a = db.query(Applicant).filter(Applicant.ma_so_hv == ma_so_hv).first()
    if not a:
        raise HTTPException(404, "Applicant not found")

    # 🟦 kiểm tra lý do cập nhật (hỗ trợ 2 kiểu truyền)
    reason_payload = body.get("update_reason")
    if not isinstance(reason_payload, dict):
        reason_payload = {
            "key": (body.get("update_reason_key") or "").strip(),
            "text": (body.get("update_reason_text") or "").strip(),
        }
    update_reason = _validate_update_reason(reason_payload)

    # snapshot trước khi sửa
    before = snapshot_applicant(a)
    docs_before = _docs_map(db, a.ma_so_hv)

    def has(k): return k in body
    def get(k, d=None): return body.get(k, d)
    def str_or_none(v):
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            return s if s else None
        return v

    # Cho phép đổi MSSV (và chuyển ApplicantDoc tương ứng)
    if has("ma_so_hv"):
        new_mssv = str(get("ma_so_hv") or "").strip()
        if new_mssv and new_mssv != ma_so_hv:
            existed = db.query(Applicant).filter(Applicant.ma_so_hv == new_mssv).first()
            if existed:
                raise HTTPException(409, "MSSV mới đã tồn tại.")
            a.ma_so_hv = new_mssv
            for d in db.query(ApplicantDoc).filter_by(applicant_ma_so_hv=ma_so_hv).all():
                d.applicant_ma_so_hv = new_mssv
            ma_so_hv = new_mssv

    # Nếu FE gửi ma_ho_so trong body thì không cho để trống
    if has("ma_ho_so"):
        new_code = str(get("ma_ho_so") or "").strip()
        if not new_code:
            raise HTTPException(400, "Mã HS không được trống.")
        a.ma_ho_so = new_code

    # Ngày: "" -> None, hỗ trợ nhiều định dạng
    if has("ngay_nhan_hs"):
        a.ngay_nhan_hs = _parse_date_flexible(get("ngay_nhan_hs"))
    if has("ngay_sinh"):
        a.ngay_sinh = _parse_date_flexible(get("ngay_sinh"))

    # Text fields: "" -> None (ngoại trừ ngành – xử riêng bên dưới)
    for f in ("ho_ten", "email_hoc_vien", "so_dt", "dot", "khoa", "da_tn_truoc_do", "ghi_chu"):
        if has(f):
            setattr(a, f, str_or_none(get(f)))

    # ✅ Ngành học: nhận cả 'nganh_nhap_hoc' hoặc 'nganh', ghi đúng cột hiện có
    if has("nganh_nhap_hoc") or has("nganh"):
        _nganh_val = str_or_none(get("nganh_nhap_hoc", get("nganh")))
        if hasattr(Applicant, "nganh_nhap_hoc"):
            a.nganh_nhap_hoc = _nganh_val
        elif hasattr(Applicant, "nganh"):
            a.nganh = _nganh_val

    # 🆕 cập nhật giới tính (normalize)
    if "gioi_tinh" in body:
        a.gioi_tinh = _normalize_gender(body.get("gioi_tinh"))

    # 🆕 cập nhật dân tộc
    if "dan_toc" in body and hasattr(Applicant, "dan_toc"):
        a.dan_toc = str_or_none(body.get("dan_toc"))

    # 🟦===== CẬP NHẬT TÊN (song song) =====🟦
    any_split_updated = False
    if "ho_dem" in body or "ten" in body:
        # FE mới gửi tách đôi -> cập nhật ưu tiên
        if "ho_dem" in body:
            a.ho_dem = str_or_none(body.get("ho_dem"))
            any_split_updated = True
        if "ten" in body:
            a.ten = str_or_none(body.get("ten"))
            any_split_updated = True

    # Nếu chỉ gửi ho_ten (cũ) và chưa gửi tách -> tách ra để đồng bộ
    if ("ho_ten" in body) and not any_split_updated:
        _full_in = str_or_none(body.get("ho_ten"))
        if _full_in:
            ln, fn = _split_vn_name(_full_in)
            a.ho_dem = ln or None
            a.ten = fn or None

    # Đồng bộ lại ho_ten (full) cho giai đoạn chuyển tiếp
    a.ho_ten = _display_name(getattr(a, "ho_dem", None), getattr(a, "ten", None), getattr(a, "ho_ten", None)) or None
    # 🟦===== HẾT phần tên =====🟦

    # 🆕 TỰ CẤP MÃ HS: khi hồ sơ CHƯA có mã và FE yêu cầu
    auto_assign = bool(body.get("auto_assign_ma_ho_so", False))
    if auto_assign and not (a.ma_ho_so and str(a.ma_ho_so).strip()):
        _khoa = (body.get("khoa") if "khoa" in body else a.khoa)
        _dot  = (body.get("dot")  if "dot"  in body else a.dot)
        a.ma_ho_so = _next_seq4(db, _khoa, _dot)

    # Lưu người cập nhật gần nhất
    a.nguoi_nhan_ky_ten = getattr(me, "full_name", None) or getattr(me, "username", None)

    # Cập nhật docs nếu có gửi
    if has("docs"):
        existing = {
            d.code: d
            for d in db.query(ApplicantDoc).filter_by(applicant_ma_so_hv=a.ma_so_hv).all()
        }
        for d in (get("docs") or []):
            code = (d.get("code") if isinstance(d, dict) else getattr(d, "code", None)) or None
            sl = d.get("so_luong") if isinstance(d, dict) else getattr(d, "so_luong", None)
            if not code:
                continue
            try:
                n = int(sl or 0)
            except Exception:
                n = 0

            if n <= 0:
                if code in existing:
                    db.delete(existing[code])
            else:
                if code in existing:
                    existing[code].so_luong = n
                else:
                    db.add(ApplicantDoc(applicant_ma_so_hv=a.ma_so_hv, code=code, so_luong=n))

    db.commit()

    # tạo diff docs
    docs_after = _docs_map(db, a.ma_so_hv)
    allc = set(docs_before) | set(docs_after)
    docs_diff = [
        {"code": c, "from": docs_before.get(c, 0), "to": docs_after.get(c, 0)}
        for c in sorted(allc)
        if docs_before.get(c, 0) != docs_after.get(c, 0)
    ]

    after = snapshot_applicant(a)

    # Ghi audit đầy đủ
    write_audit(
        db,
        action="UPDATE",
        target_type="Applicant",
        target_id=a.ma_so_hv,
        prev_values={**before, "docs_before": docs_before},
        new_values={
            **after,
            "docs_after": docs_after,
            "docs_diff": docs_diff,
            "update_reason": update_reason,
        },
        status="SUCCESS",
        request=request,
    )
    db.commit()

    return {
        "ok": True,
        "ma_so_hv": a.ma_so_hv,
        "ma_ho_so": a.ma_ho_so,
        "ho_ten": a.ho_ten,
        # trả thêm để FE mới dùng ngay
        "ho_dem": getattr(a, "ho_dem", None),
        "ten": getattr(a, "ten", None),
        "full_name": _display_name(getattr(a, "ho_dem", None), getattr(a, "ten", None), getattr(a, "ho_ten", None)),
    }

# ================= DELETE by MSSV (SOFT-DELETE, chỉ cần lý do) =================
@router.delete("/{ma_so_hv}", status_code=status.HTTP_204_NO_CONTENT)
def delete_applicant(
    ma_so_hv: str,
    request: Request,
    body: dict | None = Body(None, embed=False),
    db: Session = Depends(get_db),
    me=Depends(require_roles("Admin", "NhanVien", "CongTacVien", "Manager")),
):
    """
    Soft-delete: cần {"reason": "..."} trong body.
    Trả 204 No Content để FE ẩn dòng ngay, không cần reload.
    """
    ensure_mssv(ma_so_hv)

    a = db.query(Applicant).filter(Applicant.ma_so_hv == ma_so_hv).first()
    if not a:
        raise HTTPException(404, "Applicant not found")

    # 🟦 Lấy snapshot + DOCS trước khi xóa — để journal có cái hiển thị
    before = snapshot_applicant(a)
    docs_before = _docs_map(db, a.ma_so_hv)

    reason = (body or {}).get("reason") if isinstance(body, dict) else None
    if not reason or not str(reason).strip():
        raise HTTPException(400, "Thiếu lý do xoá (reason)")
    reason = str(reason).strip()[:1000]

    # Idempotent: nếu đã có deleted_at thì chỉ cập nhật lý do/người xoá
    now = datetime.utcnow()
    if not getattr(a, "deleted_at", None):
        a.deleted_at = now

    # Đặt thêm các cờ phổ biến để mọi nơi đều bắt được xoá mềm
    if hasattr(a, "status"):
        a.status = "deleted"
    if hasattr(a, "is_deleted"):
        a.is_deleted = True

    a.deleted_by = getattr(me, "full_name", None) or getattr(me, "username", None) or "ADMIN"
    a.deleted_reason = reason

    db.add(a)
    db.commit()

    # 🧾 Ghi audit đầy đủ (kèm docs_before)
    write_audit(
        db,
        action="DELETE_SOFT",
        target_type="Applicant",
        target_id=ma_so_hv,
        prev_values={**before, "docs_before": docs_before},
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

    # ⛔️ Chặn in nếu đã soft-delete
    if hasattr(Applicant, "deleted_at") and getattr(a, "deleted_at", None):
        raise HTTPException(410, "Hồ sơ đã bị xoá tạm, không thể in.")

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
        write_audit(
            db,
            action="PRINT",
            target_type="Applicant",
            target_id=a.ma_so_hv,
            prev_values={},
            new_values={"printed": True, "a5": a5},
            status="SUCCESS",
            request=request,
        )
        db.commit()

    filename = f"HS_{a.ma_ho_so or a.ma_so_hv}{'_A5' if a5 else ''}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
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
    return [{
        "ma_so_hv": a.ma_so_hv,
        "ma_ho_so": a.ma_ho_so,
        "ho_ten": a.ho_ten,
        "ho_dem": getattr(a, "ho_dem", None),
        "ten": getattr(a, "ten", None),
        "full_name": _display_name(getattr(a, "ho_dem", None), getattr(a, "ten", None), getattr(a, "ho_ten", None)),
    } for a in rows]

@router.get("/{ma_so_hv}")
def get_applicant_detail(
    ma_so_hv: str,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_roles("Admin", "NhanVien", "CongTacVien", "Manager")),
):
    # dùng lại y chang get_by_mshv
    return get_by_mshv(ma_so_hv=ma_so_hv, request=request, db=db, user=user)

