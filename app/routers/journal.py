# app/routers/journal.py
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Body
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.routers.auth import require_roles

from app.models.audit import AuditLog, DeletionRequest
from app.services.audit import write_audit

# (liên quan hard-delete Applicant)
from app.models.applicant import Applicant, ApplicantDoc

router = APIRouter(prefix="/journal", tags=["Journal"])

# Chỉ Admin được phép thao tác với nhật ký
RequireAdmin = Depends(require_roles("Admin", "NhanVien"))

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
    return row.to_dict()

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

    # Nếu là hard-delete thì chặn (giống patch trước)
    nv = (log.new_values or {}) or {}
    if log.action in ("DELETE_HARD", "DELETE") or nv.get("hard_deleted") is True:
        raise HTTPException(410, detail={
            "message": "Dữ liệu đã bị xóa vĩnh viễn, không thể khôi phục.",
            "reason": "hard_deleted",
        })

    obj = db.query(Applicant).get(log.target_id)
    if not obj:
        raise HTTPException(404, "Không tìm thấy dữ liệu để khôi phục")

    prev = (log.prev_values or {})  # snapshot trước khi thao tác

    # ⚠️ Quan trọng: clear cờ xóa mềm nếu log là DELETE_SOFT (hoặc có deleted_at trong new_values)
    apply_values = dict(prev)  # copy để không đụng prev gốc
    if log.action in ("DELETE_SOFT", "DELETE_REQUEST") or ("deleted_at" in nv):
        apply_values.update({
            "deleted_at": None,
            "deleted_by": None,
            "deleted_reason": None,
        })
        # 🟢 BỔ SUNG: reset đầy đủ các cờ để khôi phục hiển thị bình thường
        if hasattr(obj, "status"):
            apply_values["status"] = "saved"
        if hasattr(obj, "is_deleted"):
            apply_values["is_deleted"] = False

    # Áp lại giá trị
    for k, v in apply_values.items():
        if hasattr(obj, k):
            setattr(obj, k, v)

    db.add(obj)
    db.commit()
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
    return {"ok": True}

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
    Xoá VĨNH VIỄN dữ liệu mà không cần admin key.
    Body:
      {
        "log_id": 123,
        "target_type": "Applicant",
        "target_id": "2310000040",
        "confirm": "CONFIRM_DELETE",      # <== bắt buộc
        "reason": "Lý do ..."              # tuỳ chọn
      }
    """
    log_id = payload.get("log_id")
    ttype = (payload.get("target_type") or "").strip() or "Applicant"
    tid = str(payload.get("target_id") or "").strip()
    confirm = (payload.get("confirm") or "").strip()
    reason = (payload.get("reason") or "").strip()

    if not log_id or not ttype or not tid:
        raise HTTPException(400, "Thiếu tham số")

    # xác nhận từ dropdown ở client
    if confirm != "CONFIRM_DELETE":
        raise HTTPException(400, "Bạn chưa xác nhận xóa vĩnh viễn")

    if ttype != "Applicant":
        raise HTTPException(400, f"Chưa hỗ trợ hard-delete cho {ttype}")

    a = db.query(Applicant).get(tid)
    if not a:
        raise HTTPException(404, "Không tìm thấy bản ghi")

    # snapshot trước khi xoá để ghi audit
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
        "email_hoc_vien": getattr(a, "email_hoc_vien", None),
        "ngay_nhan_hs": iso(getattr(a, "ngay_nhan_hs", None)),
        "ngay_sinh": iso(getattr(a, "ngay_sinh", None)),
        "so_dt": a.so_dt,
        "nganh_nhap_hoc": getattr(a, "nganh_nhap_hoc", None),
        "dot": getattr(a, "dot", None),
        "khoa": getattr(a, "khoa", None),
        "status": getattr(a, "status", None),
        "printed": getattr(a, "printed", None),
    }

    # Xoá chi tiết trước (nếu DB không ON DELETE CASCADE)
    db.execute(delete(ApplicantDoc).where(ApplicantDoc.applicant_ma_so_hv == a.ma_so_hv))
    db.delete(a)
    db.commit()

    # Ghi audit
    write_audit(
        db,
        action="DELETE_HARD",
        target_type="Applicant",
        target_id=tid,
        prev_values=before,
        new_values={"hard_deleted": True, "reason": reason},
        status="SUCCESS",
        request=request,
    )
    db.commit()

    return {"ok": True, "target_type": ttype, "target_id": tid}
