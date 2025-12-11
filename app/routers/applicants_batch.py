# app/routers/applicants_batch.py
from __future__ import annotations
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid
import re

from fastapi import APIRouter, Depends, Body, Query, Request, HTTPException
from pydantic import BaseModel, Field, EmailStr, validator
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.routers.auth import require_roles
from app.models.applicant import Applicant
from app.services.audit import write_audit

# ------------------------------------------------------------
router = APIRouter(prefix="/applicants", tags=["Applicants (batch)"])

RequireStaff = Depends(require_roles("Admin", "NhanVien", "Manager"))

PHONE_RE = re.compile(r"^[0-9 +().-]{8,20}$")

def norm_space(s: str | None) -> str:
    return (s or "").replace("\u00A0", " ").strip()

def title_case_vi(s: str | None) -> str:
    s = norm_space(s)
    if not s:
        return ""
    return " ".join(part.capitalize() for part in s.split())

def join_full_name(ho_dem: str, ten: str) -> str:
    ho_dem = norm_space(ho_dem)
    ten = norm_space(ten)
    return " ".join(x for x in [ho_dem, ten] if x)

def is_soft_deleted(a: Applicant) -> bool:
    if getattr(a, "deleted_at", None):
        return True
    if getattr(a, "is_deleted", False):
        return True
    st = str(getattr(a, "status", "")).upper()
    return st in {"DELETED", "ARCHIVED", "INACTIVE"}

# ---------------------- Schemas -----------------------------
ALLOWED_FIELDS = {
    "ho_dem",
    "ten",
    "ho_ten",
    "gioi_tinh",
    "dan_toc",
    "ngay_sinh",
    "so_dt",
    "email_hoc_vien",
    "nganh_nhap_hoc",
    "dot",
    "khoa",
    "ghi_chu",
}

# Nhãn hiển thị đẹp cho FE
FIELD_LABELS = {
    "ho_dem": "Họ đệm",
    "ten": "Tên",
    "ho_ten": "Họ và tên",
    "gioi_tinh": "Giới tính",
    "dan_toc": "Dân tộc",
    "ngay_sinh": "Ngày sinh",
    "so_dt": "Số điện thoại",
    "email_hoc_vien": "Email học viên",
    "nganh_nhap_hoc": "Ngành nhập học",
    "dot": "Đợt",
    "khoa": "Khóa",
    "ghi_chu": "Ghi chú",
}

class BatchUpdateItem(BaseModel):
    ma_so_hv: str = Field(..., description="KHÓA chính để định danh")
    ho_dem: Optional[str] = None
    ten: Optional[str] = None
    ho_ten: Optional[str] = None
    gioi_tinh: Optional[str] = Field(None, description="Nam/Nữ/Khác")
    dan_toc: Optional[str] = None
    ngay_sinh: Optional[str] = Field(None, description="yyyy-mm-dd hoặc dd/mm/yyyy")
    so_dt: Optional[str] = None
    email_hoc_vien: Optional[EmailStr] = None
    nganh_nhap_hoc: Optional[str] = None
    dot: Optional[str] = None
    khoa: Optional[str] = None
    ghi_chu: Optional[str] = None

    @validator("ma_so_hv")
    def _v_mssv(cls, v):
        s = re.sub(r"\D", "", (v or "").strip())
        if not re.match(r"^\d{10}$", s):
            raise ValueError("MSSV phải gồm đúng 10 chữ số.")
        return s

    @validator("so_dt")
    def _v_phone(cls, v):
        if v is None or v == "":
            return v
        v = norm_space(v)
        if not PHONE_RE.match(v):
            raise ValueError("Số điện thoại không hợp lệ")
        return v

    @validator("gioi_tinh")
    def _v_gender(cls, v):
        if not v:
            return v
        v = v.strip()
        if v not in {"Nam", "Nữ", "Khác"}:
            raise ValueError("gioi_tinh phải là Nam/Nữ/Khác")
        return v

    @validator("ngay_sinh")
    def _v_date(cls, v):
        if not v:
            return v
        s = v.strip()
        m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", s)
        if m:  # dd/mm/yyyy -> yyyy-mm-dd
            d, mo, y = m.groups()
            return f"{y}-{mo}-{d}"
        if re.match(r"^\d{4}-\d{2}-\d{2}$", s):  # yyyy-mm-dd
            return s
        raise ValueError("ngay_sinh phải dd/mm/yyyy hoặc yyyy-mm-dd")

class BatchUpdateRequest(BaseModel):
    items: List[BatchUpdateItem]
    stop_on_error: bool = False

class BatchUpdateRowResult(BaseModel):
    ma_so_hv: str
    status: str  # UPDATED|SKIPPED|NOT_FOUND|SOFT_DELETED|INVALID
    changed_fields: Dict[str, Any] | None = None
    errors: List[str] | None = None

class BatchUpdateResponse(BaseModel):
    ok: bool
    correlation_id: str
    total: int
    updated: int
    skipped: int
    not_found: int
    soft_deleted: int
    invalid: int
    results: List[BatchUpdateRowResult]

# ---------------------- Helpers -----------------------------
def _diff_and_normalize(a: Applicant, data: Dict[str, Any]) -> Dict[str, Any]:
    ho_dem_in = data.get("ho_dem")
    ten_in = data.get("ten")
    ho_ten_in = data.get("ho_ten")

    # Chuẩn hoá input của 2 cột tách
    new_ho_dem = title_case_vi(ho_dem_in) if ho_dem_in is not None else norm_space(getattr(a, "ho_dem", "") or "")
    new_ten    = title_case_vi(ten_in)    if ten_in    is not None else norm_space(getattr(a, "ten", "") or "")

    norm: Dict[str, Any] = {}

    # Các field khác (ngoài tên)
    for k in ALLOWED_FIELDS:
        if k in {"ho_dem", "ten", "ho_ten"}:
            continue
        if k in data and data[k] is not None:
            norm[k] = norm_space(str(data[k]))

    # Ghi lại 2 cột tách nếu có trong file
    if ho_dem_in is not None:
        norm["ho_dem"] = new_ho_dem
    if ten_in is not None:
        norm["ten"] = new_ten

    # Đồng bộ ho_ten:
    # - Nếu file batch có cột ho_ten -> dùng đúng giá trị đó (đã title-case)
    # - Nếu KHÔNG có cột ho_ten -> tự build từ (new_ho_dem, new_ten)
    if ho_ten_in is None and (ho_dem_in is not None or ten_in is not None):
        norm["ho_ten"] = title_case_vi(join_full_name(new_ho_dem, new_ten))
    else:
        # luôn sync để đảm bảo nhất quán dữ liệu
        norm["ho_ten"] = title_case_vi(join_full_name(new_ho_dem, new_ten))

    # So sánh với DB -> chỉ trả những field thực sự thay đổi
    changed: Dict[str, Any] = {}
    for k, v in norm.items():
        if hasattr(a, k):
            cur = getattr(a, k)
            cur_s = "" if cur is None else str(cur).strip()
            new_s = "" if v   is None else str(v).strip()
            if cur_s != new_s:
                changed[k] = v
    return changed

def _safe_write_audit(
    db: Session,
    *,
    request: Request,
    corr: str,
    target_id: str,
    prev: Dict[str, Any],
    changes: Dict[str, Any],
    dry_run: bool,
):
    """Ghi audit tương thích nhiều version (có/không correlation_id)."""
    try:
        write_audit(
            db,
            action="BATCH_UPDATE" if not dry_run else "BATCH_UPDATE_PREVIEW",
            target_type="Applicant",
            target_id=target_id,
            prev_values=prev,
            new_values=changes,
            status="SUCCESS",
            request=request,
            correlation_id=corr,
        )
    except TypeError:
        write_audit(
            db,
            action="BATCH_UPDATE" if not dry_run else "BATCH_UPDATE_PREVIEW",
            target_type="Applicant",
            target_id=target_id,
            prev_values=prev,
            new_values=changes,
            status="SUCCESS",
            request=request,
        )

# ---------------------- Core handler ------------------------
def _handle_batch_update(
    request: Request,
    payload: BatchUpdateRequest,
    dry_run: bool,
    db: Session,
) -> BatchUpdateResponse:
    if not payload.items:
        raise HTTPException(400, "Danh sách rỗng")

    corr = str(uuid.uuid4())
    results: List[BatchUpdateRowResult] = []
    n_up = n_skip = n_nf = n_sd = n_inv = 0

    for item in payload.items:
        mshv = item.ma_so_hv.strip()
        try:
            a: Applicant | None = db.get(Applicant, mshv)
            if not a:
                n_nf += 1
                results.append(BatchUpdateRowResult(ma_so_hv=mshv, status="NOT_FOUND"))
                if payload.stop_on_error:
                    raise RuntimeError("stop_on_error")
                continue

            if is_soft_deleted(a):
                n_sd += 1
                results.append(BatchUpdateRowResult(ma_so_hv=mshv, status="SOFT_DELETED"))
                continue

            changes = _diff_and_normalize(a, item.dict(exclude_unset=True))
            if not changes:
                n_skip += 1
                results.append(
                    BatchUpdateRowResult(
                        ma_so_hv=mshv, status="SKIPPED", changed_fields={}
                    )
                )
                continue

            prev = {k: getattr(a, k, None) for k in changes.keys()}

            if not dry_run:
                for k, v in changes.items():
                    setattr(a, k, v)
                if hasattr(a, "updated_at"):
                    setattr(a, "updated_at", datetime.utcnow())
                db.add(a)

            # Audit dùng key raw
            _safe_write_audit(
                db,
                request=request,
                corr=corr,
                target_id=mshv,
                prev=prev,
                changes=changes,
                dry_run=dry_run,
            )

            # FE hiển thị nhãn đẹp
            readable_fields = {FIELD_LABELS.get(k, k): v for k, v in changes.items()}

            if dry_run:
                results.append(
                    BatchUpdateRowResult(
                        ma_so_hv=mshv, status="UPDATED", changed_fields=readable_fields
                    )
                )
            else:
                n_up += 1
                results.append(
                    BatchUpdateRowResult(
                        ma_so_hv=mshv, status="UPDATED", changed_fields=readable_fields
                    )
                )

        except Exception as e:
            n_inv += 1
            results.append(
                BatchUpdateRowResult(
                    ma_so_hv=item.ma_so_hv, status="INVALID", errors=[str(e)]
                )
            )
            if payload.stop_on_error:
                db.rollback()
                return BatchUpdateResponse(
                    ok=False,
                    correlation_id=corr,
                    total=len(payload.items),
                    updated=n_up,
                    skipped=n_skip,
                    not_found=n_nf,
                    soft_deleted=n_sd,
                    invalid=n_inv,
                    results=results,
                )

    if not dry_run:
        db.commit()

    return BatchUpdateResponse(
        ok=True,
        correlation_id=corr,
        total=len(payload.items),
        updated=(0 if dry_run else n_up),
        skipped=(
            n_skip
            if not dry_run
            else len([r for r in results if r.status in {"SKIPPED", "UPDATED"}])
        ),
        not_found=n_nf,
        soft_deleted=n_sd,
        invalid=n_inv,
        results=results,
    )

# ---------------------- Routes (multi-method) ---------------
@router.post("/batch-update", response_model=BatchUpdateResponse, dependencies=[RequireStaff])
@router.post("/batch-update/", response_model=BatchUpdateResponse, dependencies=[RequireStaff])
@router.put("/batch-update", response_model=BatchUpdateResponse, dependencies=[RequireStaff])
@router.put("/batch-update/", response_model=BatchUpdateResponse, dependencies=[RequireStaff])
@router.patch("/batch-update", response_model=BatchUpdateResponse, dependencies=[RequireStaff])
@router.patch("/batch-update/", response_model=BatchUpdateResponse, dependencies=[RequireStaff])
def applicants_batch_update(
    request: Request,
    payload: BatchUpdateRequest = Body(...),
    dry_run: bool = Query(False),
    db: Session = Depends(get_db),
):
    return _handle_batch_update(request, payload, dry_run, db)
