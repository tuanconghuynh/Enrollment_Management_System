# app/routers/batch.py
from __future__ import annotations

from datetime import datetime, timedelta, date
import io

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from starlette.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.session import get_db
from app.models.applicant import Applicant, ApplicantDoc
from app.models.checklist import ChecklistItem
from app.services.pdf_service import render_batch_pdf
from app.utils.soft_delete import exclude_deleted, ensure_not_deleted

# Audit + Auth
from app.routers.auth import require_roles
from app.services.audit import write_audit

router = APIRouter(prefix="/batch", tags=["Batch"])

# ------------------- Audit -------------------
def _audit_print_or_export(
    *,
    request: Request,
    db: Session,
    user,
    action: str,
    scope: str,
    filters: dict,
    count: int,
    status: str,
    error: str | None = None,
    name_mode: str | None = None,
    target_type: str = "ApplicantBatch",
    target_id: str | None = None
):
    payload = {
        "scope": scope,
        "filters": filters or {},
        "count": int(count or 0),
        "name_mode": name_mode,
        "actor_id": getattr(user, "id", None),
        "actor_name": getattr(user, "full_name", None) or getattr(user, "username", None),
    }
    if error:
        payload["error"] = str(error)

    try:
        write_audit(
            db,
            action=action,
            target_type=target_type,
            target_id=target_id,
            prev_values=None,
            new_values=payload,
            status=status,
            request=request,
        )
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass

# ------------------- Helpers -------------------
def _parse_day(raw: str) -> date:
    s = (raw or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    raise HTTPException(
        status_code=400,
        detail="Sai định dạng ngày. Dùng 'date=dd/MM/YYYY' hoặc 'day=YYYY-MM-DD'."
    )

def _fmt_dmy(d: date) -> str:
    return d.strftime("%d/%m/%Y") if d else ""

def _load_items_by_version(db: Session, version_ids):
    items_by_version: dict[int, list[ChecklistItem]] = {}
    for vid in version_ids:
        q = db.query(ChecklistItem).filter(ChecklistItem.version_id == vid)
        if hasattr(ChecklistItem, "order_index"):
            q = q.order_by(getattr(ChecklistItem, "order_index").asc())
        elif hasattr(ChecklistItem, "order_no"):
            q = q.order_by(getattr(ChecklistItem, "order_no").asc())
        else:
            q = q.order_by(ChecklistItem.id.asc())
        items_by_version[vid] = q.all()
    return items_by_version

def _docs_by_mssv(db: Session, mssv_list):
    out: dict[str, list[ApplicantDoc]] = {}
    if not mssv_list:
        return out

    docs = (
        db.query(ApplicantDoc)
        .filter(ApplicantDoc.applicant_ma_so_hv.in_(mssv_list))
        .all()
    )

    for d in docs:
        out.setdefault(d.applicant_ma_so_hv, []).append(d)

    return out

def _is_not_deleted(a: Applicant) -> bool:
    if getattr(a, "deleted_at", None):
        return False
    if getattr(a, "is_deleted", False):
        return False
    if getattr(a, "status", None) == "deleted":
        return False
    return True

def _dedup_latest_by_mssv(apps):
    by: dict[str, Applicant] = {}
    for a in apps:
        k = a.ma_so_hv
        if k not in by or (getattr(a, "created_at", None) or datetime.min) > (
            getattr(by[k], "created_at", None) or datetime.min
        ):
            by[k] = a
    return list(by.values())

def _merge_items(items_by_version: dict) -> list[ChecklistItem]:
    """
    pdf_service.render_batch_pdf đang nhận 1 list items_all,
    ở đây gộp các version lại, ưu tiên giữ thứ tự + không trùng code.
    """
    seen_codes: set[str] = set()
    items_all: list[ChecklistItem] = []
    for _, items in items_by_version.items():
        for it in items:
            code = (getattr(it, "code", None) or "").strip()
            if code and code in seen_codes:
                continue
            items_all.append(it)
            if code:
                seen_codes.add(code)
    return items_all

def _flatten_docs(docs_by_app: dict[str, list[ApplicantDoc]]) -> list[ApplicantDoc]:
    docs_all: list[ApplicantDoc] = []
    for _, docs in docs_by_app.items():
        docs_all.extend(docs or [])
    return docs_all

# ------------------- Print By Day -------------------
@router.get("/print")
def batch_print(
    request: Request,
    day: str | None = Query(None, description="YYYY-MM-DD (tùy chọn)"),
    date_q: str | None = Query(None, alias="date", description="dd/MM/YYYY (khuyến nghị)"),
    print_type: str = Query("A4", alias="type"),
    db: Session = Depends(get_db),
    user=Depends(require_roles("Admin", "NhanVien", "Manager")),
):

    print_type = (print_type or "A4").upper()
    if print_type not in {"A4", "A5", "POSTAL"}:
        print_type = "A4"

    raw = date_q or day
    if not raw:
        _audit_print_or_export(
            request=request,
            db=db,
            user=user,
            action="PRINT",
            scope="day",
            filters={"date": None},
            count=0,
            status="FAIL",
            error="MISSING_DATE",
            name_mode=print_type,
        )
        raise HTTPException(
            status_code=400,
            detail="Thiếu tham số 'date=dd/MM/YYYY' hoặc 'day=YYYY-MM-DD'."
        )

    d = _parse_day(raw)

    d1 = datetime.combine(d, datetime.min.time())
    d2 = d1 + timedelta(days=1)

    q = db.query(Applicant).filter(Applicant.ngay_nhan_hs >= d1, Applicant.ngay_nhan_hs < d2)
    q = exclude_deleted(Applicant, q)
    apps = q.order_by(Applicant.created_at.asc(), Applicant.ma_so_hv.asc()).all()

    if not apps:
        q = exclude_deleted(Applicant, db.query(Applicant).filter(Applicant.ngay_nhan_hs == d))
        apps = q.order_by(Applicant.created_at.asc(), Applicant.ma_so_hv.asc()).all()

    apps = [a for a in apps if _is_not_deleted(a) and ensure_not_deleted(a, raise_http_exception=False)]
    apps = _dedup_latest_by_mssv(apps)

    if not apps:
        _audit_print_or_export(
            request=request,
            db=db,
            user=user,
            action="PRINT",
            scope="day",
            filters={"date": d.isoformat()},
            count=0,
            status="FAIL",
            error="NO_DATA",
            name_mode=print_type,
        )
        raise HTTPException(status_code=404, detail=f"Không có hồ sơ nào trong ngày { _fmt_dmy(d) }")

    
    version_ids = {a.checklist_version_id for a in apps if a.checklist_version_id}
    items_by_version = _load_items_by_version(db, version_ids)
    items_all = _merge_items(items_by_version)

    valid_mssv = {a.ma_so_hv for a in apps}
    docs_by_app = _docs_by_mssv(db, valid_mssv)
    docs_by_app = {m: ds for (m, ds) in docs_by_app.items() if m in valid_mssv}
    docs_all = _flatten_docs(docs_by_app)

    pdf_bytes = render_batch_pdf(
        apps,
        items_all,
        docs_all,
        print_type=print_type,
    )

    _audit_print_or_export(
        request=request,
        db=db,
        user=user,
        action="PRINT",
        scope="day",
        filters={"date": d.isoformat()},
        count=len(apps),
        status="SUCCESS",
        name_mode=print_type,
    )

    filename = f"Batch_{d.strftime('%d-%m-%Y')}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename=\"{filename}\"'},
    )

# ------------------- Print By Dot -------------------
@router.get("/print-dot")
def batch_print_dot(
    request: Request,
    dot: str = Query(..., description="Tên đợt"),
    print_type: str = Query("A4", alias="type"),
    khoa: str | None = Query(None, description="(Tuỳ chọn) Khóa"),
    db: Session = Depends(get_db),
    user=Depends(require_roles("Admin", "NhanVien", "Manager")),
):

    print_type = (print_type or "A4").upper()
    if print_type not in {"A4", "A5", "POSTAL"}:
        print_type = "A4"

    dot_norm = (dot or "").strip()
    if not dot_norm:
        _audit_print_or_export(
            request=request,
            db=db,
            user=user,
            action="PRINT",
            scope="dot",
            filters={"dot": None, "khoa": (khoa or "")},
            count=0,
            status="FAIL",
            error="MISSING_DOT",
            name_mode=print_type,
        )
        raise HTTPException(status_code=400, detail="Thiếu tham số dot.")

    q = (
        db.query(Applicant)
        .filter(Applicant.dot.isnot(None))
        .filter(Applicant.dot.ilike(f"%{dot_norm}%"))
    )

    if (khoa or "").strip():
        k = khoa.strip().lower()
        q = q.filter(Applicant.khoa.isnot(None)).filter(func.lower(func.trim(Applicant.khoa)) == k)

    q = exclude_deleted(Applicant, q)
    apps = q.order_by(Applicant.created_at.asc(), Applicant.ma_so_hv.asc()).all()

    apps = [a for a in apps if _is_not_deleted(a) and ensure_not_deleted(a, raise_http_exception=False)]
    apps = _dedup_latest_by_mssv(apps)

    if not apps:
        _audit_print_or_export(
            request=request,
            db=db,
            user=user,
            action="PRINT",
            scope="dot",
            filters={"dot": dot_norm, "khoa": (khoa or "")},
            count=0,
            status="FAIL",
            error="NO_DATA",
            name_mode=print_type,
        )
        raise HTTPException(status_code=404, detail="Không có hồ sơ nào thuộc đợt đã chọn.")

    version_ids = {a.checklist_version_id for a in apps if a.checklist_version_id}
    items_by_version = _load_items_by_version(db, version_ids)
    items_all = _merge_items(items_by_version)

    valid_mssv = {a.ma_so_hv for a in apps}
    docs_by_app = _docs_by_mssv(db, valid_mssv)
    docs_by_app = {m: ds for (m, ds) in docs_by_app.items() if m in valid_mssv}
    docs_all = _flatten_docs(docs_by_app)

    pdf_bytes = render_batch_pdf(
        apps,
        items_all,
        docs_all,
        print_type=print_type,
    )

    _audit_print_or_export(
        request=request,
        db=db,
        user=user,
        action="PRINT",
        scope="dot",
        filters={"dot": dot_norm, "khoa": (khoa or "")},
        count=len(apps),
        status="SUCCESS",
        name_mode=print_type,
    )

    safe_dot = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in dot_norm)
    safe_khoa = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in (khoa or ""))

    suffix = f"{safe_dot}" + (f"_Khoa_{safe_khoa}" if safe_khoa else "")
    filename = f"Batch_Dot_{suffix}.pdf"

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename=\"{filename}\"'},
    )

# ------------------- Compatible Router -------------------
@router.get("/print-by-dot")
def batch_print_by_dot_compat(
    request: Request,
    dot: str = Query(..., description="Tên đợt cũ"),
    db: Session = Depends(get_db),
    user=Depends(require_roles("Admin", "NhanVien", "Manager")),
):
    return batch_print_dot(request=request, dot=dot, db=db, user=user)
# ===========================================================
