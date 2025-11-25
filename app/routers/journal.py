# app/routers/journal.py
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Body
from fastapi.encoders import jsonable_encoder
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.routers.auth import require_roles

from app.models.audit import AuditLog, DeletionRequest
from app.services.audit import write_audit
from pydantic import BaseModel, Field
from sqlalchemy import delete, not_


# (liên quan hard-delete Applicant)
from app.models.applicant import Applicant, ApplicantDoc

router = APIRouter(prefix="/journal", tags=["Journal"])

# Chỉ Admin hoặc Nhân viên được phép thao tác với nhật ký
RequireAdmin = Depends(require_roles("Admin", "NhanVien"))

# ---------------- helpers tên ----------------
def _display_name_from_obj(a: Applicant) -> str:
    hd = (getattr(a, "ho_dem", None) or "").strip()
    t = (getattr(a, "ten", None) or "").strip()
    if hd or t:
        return f"{hd} {t}".strip()
    return (getattr(a, "ho_ten", None) or "").strip()

def _sync_full_name(a: Applicant):
    """
    Đồng bộ ho_ten từ ho_dem + ten (giai đoạn chuyển tiếp).
    Không raise nếu model chưa có cột tách.
    """
    if hasattr(a, "ho_dem") and hasattr(a, "ten") and hasattr(a, "ho_ten"):
        a.ho_ten = _display_name_from_obj(a) or None

# ===================== LIST =====================
@router.get("/", dependencies=[RequireAdmin])
def list_logs(
    db: Session = Depends(get_db),
    # bộ lọc cũ (giữ tương thích)
    action: Optional[str] = Query(None),
    target_type: Optional[str] = Query(None),
    target_id: Optional[str] = Query(None),
    # bộ lọc mới
    q: Optional[str] = Query(None, description="keyword: actor_name, path, ip, correlation_id, action, target_id"),
    actor: Optional[str] = Query(None, description="filter by actor_name contains"),
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    # ẩn bớt các log “rác”
    exclude_noise: bool = Query(
        True,
        description="Nếu True: ẩn các log tra cứu / lỗi hệ thống / mở email / preview batch..."
    ),
    exclude_actions: Optional[str] = Query(
        None,
        description="Danh sách action cần ẩn, ngăn cách bởi dấu phẩy, vd: 'READ,EXCEPTION'"
    ),
    # phân trang + sắp xếp
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    sort: Optional[str] = Query(None, description="field:dir, vd occurred_at:desc"),
):
    qset = db.query(AuditLog)

    # Lọc cũ
    if action:
        qset = qset.filter(AuditLog.action == action)
    if target_type:
        qset = qset.filter(AuditLog.target_type == target_type)
    if target_id:
        qset = qset.filter(AuditLog.target_id == target_id)
    # Keyword (nhiều cột)
    if q:
        like = f"%{q.strip()}%"
        qset = qset.filter(
            (AuditLog.actor_name.ilike(like)) |
            (AuditLog.path.ilike(like)) |
            (AuditLog.ip_address.ilike(like)) |
            (AuditLog.correlation_id.ilike(like)) |
            (AuditLog.action.ilike(like)) |
            (AuditLog.target_id.ilike(like))
        )
    # Người thao tác
    if actor:
        qset = qset.filter(AuditLog.actor_name.ilike(f"%{actor.strip()}%"))
    # Khoảng ngày theo occurred_at (ISO yyyy-mm-dd)
    from_dt = None
    to_dt = None
    try:
        if from_:
            from_dt = datetime.fromisoformat(from_)
    except Exception:
        pass
    try:
        if to:
            to_dt = datetime.fromisoformat(to) + timedelta(days=1)  # upper-bound exclusive
    except Exception:
        pass
    if from_dt:
        qset = qset.filter(AuditLog.occurred_at >= from_dt)
    if to_dt:
        qset = qset.filter(AuditLog.occurred_at < to_dt)
    
        # Ẩn bớt các action không phải chức năng chính
    noise_set = set()

    if exclude_noise:
        noise_set.update({
            "READ",               # Tra cứu
            "EXCEPTION",          # Lỗi hệ thống
            "EMAIL_DRAFT_OPEN",   # Mở màn hình soạn email
            "EMAIL_PREVIEW",      # Xem trước email
            "EMAIL_TEMPLATE_VIEW",
            "BATCH_UPDATE_PREVIEW",  # Xem trước batch, không thay đổi dữ liệu
        })

    if exclude_actions:
        extra = [a.strip().upper() for a in exclude_actions.split(",") if a.strip()]
        noise_set.update(extra)

    if noise_set:
        # dùng not_() hoặc ~ để phủ định IN
        qset = qset.filter(~AuditLog.action.in_(noise_set))
        # hoặc: qset = qset.filter(AuditLog.action.notin_(noise_set))

    # Sắp xếp
    order_col = AuditLog.occurred_at
    order_dir = "desc"
    if sort:
        try:
            field, dir_ = (sort.split(":") + [""])[:2]
            field = (field or "").strip()
            dir_ = (dir_ or "").strip().lower()
            col = {
                "id": AuditLog.id,
                "occurred_at": AuditLog.occurred_at,
                "actor_name": AuditLog.actor_name,
                "action": AuditLog.action,
                "status": AuditLog.status,
                "target_id": AuditLog.target_id,
            }.get(field, AuditLog.occurred_at)
            order_col = col
            order_dir = "asc" if dir_ == "asc" else "desc"
        except Exception:
            pass
    total = qset.count()
    qset = qset.order_by(order_col.asc() if order_dir == "asc" else order_col.desc())
    items = (
        qset.offset((page - 1) * page_size)
           .limit(page_size)
           .all()
    )
    return {
        "total": total,
        "page": page,
        "size": page_size,
        "items": [i.to_dict() for i in items],
    }

# ===================== DETAIL =====================
@router.get("/detail/{log_id}", dependencies=[RequireAdmin])
def log_detail(log_id: int, db: Session = Depends(get_db)):
    row = db.query(AuditLog).get(log_id)
    if not row:
        raise HTTPException(404, "Không tìm thấy log")

    data = row.to_dict()

    # cờ đã xóa vĩnh viễn cho cùng target
    already_hard = False
    if row.target_id:
        already_hard = db.query(AuditLog).filter(
            AuditLog.target_type == row.target_type,
            AuditLog.target_id == row.target_id,
            AuditLog.action == "DELETE_HARD",
        ).count() > 0

    data["already_hard_deleted_target"] = already_hard
    return data
# ===================== RESTORE =====================
@router.post("/restore/{log_id}", dependencies=[RequireAdmin])
def restore_from_log(
    log_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    log = db.query(AuditLog).get(log_id)
    if not log:
        raise HTTPException(404, "Không tìm thấy log")
    if not log.target_type or not log.target_id:
        raise HTTPException(400, "Log này không gắn với đối tượng dữ liệu")

    # Nếu là hard-delete thì chặn
    nv = (log.new_values or {}) or {}
    if log.action in ("DELETE_HARD", "DELETE") or nv.get("hard_deleted") is True:
        raise HTTPException(410, detail={
            "message": "Dữ liệu đã bị xóa vĩnh viễn, không thể khôi phục.",
            "reason": "hard_deleted",
        })

    if log.target_type != "Applicant":
        raise HTTPException(400, f"Chưa hỗ trợ khôi phục cho {log.target_type}")

    obj = db.query(Applicant).get(log.target_id)
    if not obj:
        raise HTTPException(404, "Không tìm thấy dữ liệu để khôi phục")

    prev = (log.prev_values or {})  # snapshot trước khi thao tác

    # Clear cờ xóa mềm & KHÔNG ép status="saved"
    apply_values = dict(prev)  # copy
    if log.action in ("DELETE_SOFT", "DELETE_REQUEST") or ("deleted_at" in nv):
        apply_values.update({
            "deleted_at": None,
            "deleted_by": None,
            "deleted_reason": None,
        })
        if hasattr(obj, "is_deleted"):
            apply_values["is_deleted"] = False
    # Áp lại giá trị
    for k, v in apply_values.items():
        if hasattr(obj, k):
            setattr(obj, k, v)
    # Đồng bộ lại ho_ten từ ho_dem + ten nếu có
    _sync_full_name(obj)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    # Huỷ DeletionRequest liên quan (nếu có)
    try:
        reqs = (
            db.query(DeletionRequest)
              .filter(
                  DeletionRequest.target_type == log.target_type,
                  DeletionRequest.target_id == str(log.target_id),
                  DeletionRequest.status.in_(["PENDING", "REQUESTED"])
              ).all()
        )
        if reqs:
            for r in reqs:
                r.status = "CANCELLED"
            db.commit()
    except Exception:
        pass  # không chặn luồng nếu lỗi nhỏ
    # Ghi audit
    write_audit(
        db,
        action="RESTORE",
        target_type=log.target_type,
        target_id=log.target_id,
        prev_values=log.new_values,
        new_values=apply_values,
        status="SUCCESS",
        request=request,
    )
    db.commit()
    db.refresh(obj)

    # ✅ Trả về item đã được encode JSON an toàn
    return {"ok": True, "item": jsonable_encoder(obj)}

# ===================== (OPTIONAL) Deletion Requests =====================
@router.get("/deletion-requests", dependencies=[RequireAdmin])
def list_deletion_requests(
    db: Session = Depends(get_db),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=500),
):
    q = db.query(DeletionRequest)
    if status:
        q = q.filter(DeletionRequest.status == status)
    total = q.count()
    rows = (
        q.order_by(DeletionRequest.id.desc())
         .offset((page - 1) * size)
         .limit(size)
         .all()
    )
    def to_dict(r):
        return {
            "id": r.id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "actor_id": r.actor_id,
            "actor_name": r.actor_name,
            "target_type": r.target_type,
            "target_id": r.target_id,
            "reason": r.reason,
            "confirmed_by": r.confirmed_by,
            "confirmed_at": r.confirmed_at.isoformat() if r.confirmed_at else None,
            "status": r.status,
            "audit_log_id": r.audit_log_id,
        }

    return {"total": total, "page": page, "size": size, "items": [to_dict(r) for r in rows]}

# ===================== HARD DELETE (NO KEY) =====================
@router.post("/hard-delete", dependencies=[RequireAdmin])
def hard_delete(
    request: Request,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
):
    """
    Xóa VĨNH VIỄN dữ liệu (không cần admin key bổ sung).

    Payload mới (UI mới - RECOMMENDED):
      {
        "log_id": 123,
        "target_type": "Applicant",
        "target_id": "2310000040",
        "confirm": "CONFIRM_DELETE",     # bắt buộc
        "reason_code": "TRUNG_LAP" | "NHAM_MSSV" | "YEU_CAU_NGUOI_DUNG" | "TEST_DATA" | "OTHER",  # bắt buộc
        "reason": "… (bắt buộc nếu reason_code=OTHER, ngược lại là mô tả auto)"
      }

    Tương thích ngược (UI cũ):
      - Nếu không gửi reason_code mà chỉ có reason: vẫn chấp nhận,
        sẽ map reason_code = "OTHER" nếu không nhận diện được.
    """
    # ----------- Lấy tham số cơ bản -----------
    log_id = payload.get("log_id")
    ttype = (payload.get("target_type") or "").strip() or "Applicant"
    tid = str(payload.get("target_id") or "").strip()
    confirm = (payload.get("confirm") or "").strip()

    if not log_id or not ttype or not tid:
        raise HTTPException(400, "Thiếu tham số")

    if confirm != "CONFIRM_DELETE":
        raise HTTPException(400, "Bạn chưa xác nhận xóa vĩnh viễn")

    if ttype != "Applicant":
        raise HTTPException(400, f"Chưa hỗ trợ hard-delete cho {ttype}")

    # ----------- Xử lý reason_code + reason -----------
    raw_code = (payload.get("reason_code") or "").strip().upper()
    raw_text = (payload.get("reason") or "").strip()

    # Map mã -> mô tả mặc định
    REASON_MAP = {
        "TRUNG_LAP": "Hồ sơ trùng lặp",
        "NHAM_MSSV": "Nhầm MSSV/mục tiêu",
        "YEU_CAU_NGUOI_DUNG": "Yêu cầu người dùng xóa dữ liệu",
        "TEST_DATA": "Dữ liệu thử nghiệm",
        "OTHER": "Lý do khác",
    }

    if not raw_code:
        # Tương thích ngược: nếu UI cũ chỉ gửi 'reason', auto OTHER
        raw_code = "OTHER" if raw_text else ""
    if not raw_code:
        raise HTTPException(400, "Vui lòng chọn lý do xóa (reason_code).")

    # Nếu chọn OTHER thì bắt buộc có text người dùng nhập
    if raw_code == "OTHER" and not raw_text:
        raise HTTPException(400, "Vui lòng nhập lý do khác (reason).")

    # Chuẩn hóa final_text: nếu không phải OTHER, lấy mô tả default
    final_text = raw_text if raw_code == "OTHER" else REASON_MAP.get(raw_code, raw_code)

    # ----------- Tải đối tượng & snapshot -----------
    a = db.query(Applicant).get(tid)
    if not a:
        raise HTTPException(404, "Không tìm thấy bản ghi")

    def iso(v):
        if not v:
            return None
        if isinstance(v, datetime):
            return v.isoformat()
        if hasattr(v, "isoformat"):
            return v.isoformat()
        return str(v)

    before = {
        "ma_so_hv": a.ma_so_hv,
        "ma_ho_so": a.ma_ho_so,
        "ho_ten": a.ho_ten,
        "ho_dem": getattr(a, "ho_dem", None),
        "ten": getattr(a, "ten", None),
        "full_name": _display_name_from_obj(a),
        "email_hoc_vien": getattr(a, "email_hoc_vien", None),
        "ngay_nhan_hs": iso(getattr(a, "ngay_nhan_hs", None)),
        "ngay_sinh": iso(getattr(a, "ngay_sinh", None)),
        "so_dt": a.so_dt,
        "nganh_nhap_hoc": getattr(a, "nganh_nhap_hoc", None) if hasattr(a, "nganh_nhap_hoc") else getattr(a, "nganh", None),
        "dot": getattr(a, "dot", None),
        "khoa": getattr(a, "khoa", None),
        "da_tn_truoc_do": getattr(a, "da_tn_truoc_do", None),
        "ghi_chu": getattr(a, "ghi_chu", None),
        "nguoi_nhan_ky_ten": getattr(a, "nguoi_nhan_ky_ten", None),
        "status": getattr(a, "status", None),
        "printed": getattr(a, "printed", None),
        "gioi_tinh": getattr(a, "gioi_tinh", None),
        "dan_toc": getattr(a, "dan_toc", None),
        "checklist_version_id": getattr(a, "checklist_version_id", None),
    }

    # ----------- Xóa dữ liệu + chi tiết (nếu không có CASCADE) -----------
    db.execute(delete(ApplicantDoc).where(ApplicantDoc.applicant_ma_so_hv == a.ma_so_hv))
    db.delete(a)
    db.commit()

    # ----------- Ghi audit với cấu trúc mới -----------
    new_values = {
        "hard_deleted": True,
        "reason_code": raw_code,  # <-- mã lý do
        "reason": final_text,     # <-- mô tả cuối cùng
        # giữ tương thích (UI/BE cũ nếu có đọc 'delete_reason'):
        "deleted_reason": final_text,
    }

    write_audit(
        db,
        action="DELETE_HARD",
        target_type="Applicant",
        target_id=tid,
        prev_values=before,
        new_values=new_values,
        status="SUCCESS",
        request=request,
    )
    db.commit()

    return {"ok": True, "target_type": ttype, "target_id": tid, "reason_code": raw_code}

# ====== Pydantic payload cho POST /journal/track ======
class JournalTrackDetail(BaseModel):
    scope: str | None = Field(None, description="'ALL' | 'FILTERED' | 'SELECTED' | 'SINGLE' ...")
    name_mode: str | None = Field(None, description="A4 | A5 | default | ...")
    count: int | None = Field(None, description="số lượng mục liên quan")
    # filters gốc để truy vết, VD chứa mshv, dot, khoa...
    filters: dict | None = None
    # có thể truyền thẳng định danh mục tiêu (nếu có)
    target_type: str | None = None
    target_id: str | None = None

class JournalTrackIn(BaseModel):
    action: str = Field(..., description="Ví dụ: 'PRINT_IN' hoặc 'EXPORT'")
    detail: JournalTrackDetail | None = None

    # 👇 thêm 2 field để nhận từ FE
    target_type: str | None = Field(
        None,
        description="Applicant | ApplicantBatch | Batch | ... (tùy FE gửi)"
    )
    target_id: str | None = Field(
        None,
        description="MSSV hoặc ID mục tiêu"
    )

# ====== Ghi log thao tác in/xuất ======
@router.post("/track")
def track_action(
    payload: JournalTrackIn,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Dùng cho FE ghi nhận các thao tác In/Xuất.
    - action: 'PRINT_IN' | 'EXPORT' | ...
    - detail: metadata (scope, name_mode, count, filters, target_type, target_id)
    """
    action = (payload.action or "").strip().upper()
    if action not in {"PRINT_IN", "EXPORT", "PRINT_EXPORT"}:
        # vẫn cho ghi, nhưng khuyến nghị hai giá trị chính
        pass

    d = payload.detail.dict() if payload.detail else {}

    # ƯU TIÊN lấy từ top-level (FE đang gửi target_type/target_id ở đây)
    target_type = (
        (payload.target_type or "").strip()
        or (d.get("target_type") or "").strip()
        or "Batch"
    )
    target_id = (
        (payload.target_id or "").strip()
        or (d.get("target_id") or "").strip()
        or (d.get("filters") or {}).get("mshv")
        or None
    )

    # new_values lưu toàn bộ chi tiết để xem ở trang "Chi tiết"
    new_values = {
        "scope": d.get("scope"),
        "name_mode": d.get("name_mode"),
        "count": d.get("count"),
        "filters": d.get("filters") or {},
    }

    write_audit(
        db,
        action=action,                   # <-- 'PRINT_IN' hoặc 'EXPORT'
        target_type=target_type,         # 'Batch' hoặc 'Applicant'
        target_id=str(target_id) if target_id else None,
        prev_values=None,
        new_values=new_values,
        status="SUCCESS",
        request=request,
    )
    db.commit()
    # Không cần body, 204 cho gọn
    return {"ok": True}

# ====== Fallback GET /journal/track?action=...&mshv=... ======
@router.get("/track")
def track_action_get(
    request: Request,
    db: Session = Depends(get_db),
    action: str = Query(..., description="PRINT_IN | EXPORT"),
    scope: str | None = None,
    name_mode: str | None = None,
    count: int | None = None,
    mshv: str | None = None,
):
    new_values = {"scope": scope, "name_mode": name_mode, "count": count, "filters": {"mshv": mshv} if mshv else {}}
    write_audit(
        db,
        action=(action or "").upper(),
        target_type="Applicant" if mshv else "Batch",
        target_id=mshv,
        prev_values=None,
        new_values=new_values,
        status="SUCCESS",
        request=request,
    )
    db.commit()
    return {"ok": True}
