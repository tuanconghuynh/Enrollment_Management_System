# app/routers/batch.py
from datetime import datetime, timedelta, date
import io
from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.session import get_db
from app.models.applicant import Applicant, ApplicantDoc
from app.models.checklist import ChecklistItem
from app.services.pdf_service import render_batch_pdf

router = APIRouter(prefix="/batch", tags=["Batch"])

# -------- helpers --------
def _parse_day(raw: str) -> date:
    """
    Ưu tiên 'dd/MM/YYYY' (theo yêu cầu), vẫn chấp nhận 'YYYY-MM-DD' (input type=date).
    """
    s = (raw or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    raise HTTPException(
        status_code=400,
        detail="Sai định dạng ngày. Dùng 'date=dd/MM/YYYY' (ưu tiên) hoặc 'day=YYYY-MM-DD'."
    )

def _fmt_dmy(d: date) -> str:
    return d.strftime("%d/%m/%Y") if d else ""

def _load_items_by_version(db: Session, version_ids):
    items_by_version = {}
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
    """
    Trả về dict { ma_so_hv: [ApplicantDoc, ...] }
    (Đã đổi sang khóa bằng MSSV thay cho applicant_id cũ)
    """
    out = {}
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

# -------- In PDF gộp theo NGÀY --------
@router.get("/print")
def batch_print(
    day: str | None = Query(None, description="YYYY-MM-DD (tùy chọn)"),
    date_q: str | None = Query(None, alias="date", description="dd/MM/YYYY (khuyến nghị)"),
    db: Session = Depends(get_db),
):
    raw = date_q or day
    if not raw:
        raise HTTPException(status_code=400, detail="Thiếu tham số 'date=dd/MM/YYYY' hoặc 'day=YYYY-MM-DD'.")

    d = _parse_day(raw)  # trả về datetime.date

    # LỌC THEO NGÀY: dùng DATE(...) để tương thích cả DATE lẫn DATETIME
    apps = (
        db.query(Applicant)
        .filter(func.date(Applicant.ngay_nhan_hs) == d)
        .order_by(Applicant.created_at.asc(), Applicant.ma_so_hv.asc())
        .all()
    )
    if not apps:
        raise HTTPException(
            status_code=404,
            detail=f"Không có hồ sơ nào trong ngày { _fmt_dmy(d) }"
        )

    version_ids = {a.checklist_version_id for a in apps if a.checklist_version_id is not None}
    items_by_version = _load_items_by_version(db, version_ids)

    mssv_list = [a.ma_so_hv for a in apps]
    docs_by_app = _docs_by_mssv(db, mssv_list)

    pdf_bytes = render_batch_pdf(apps, items_by_version, docs_by_app)

    filename = f"Batch_{d.strftime('%d-%m-%Y')}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename=\"{filename}\"'},
    )
# -------- In PDF gộp theo ĐỢT --------
@router.get("/print-dot")
def batch_print_dot(
    dot: str = Query(..., description="Tên đợt, ví dụ: 'Đợt 1/2025' hoặc '9'"),
    khoa: str | None = Query(None, description="(Tuỳ chọn) Lọc theo Khóa, ví dụ: '27'"),
    db: Session = Depends(get_db),
):
    dot_norm = (dot or "").strip()
    if not dot_norm:
        raise HTTPException(status_code=400, detail="Thiếu tham số 'dot'.")

    q = (
        db.query(Applicant)
        .filter(Applicant.dot.isnot(None))
        .filter(Applicant.dot.ilike(f"%{dot_norm}%"))
    )

    if (khoa or "").strip():
        k = khoa.strip()
        q = q.filter(Applicant.khoa.isnot(None)).filter(func.lower(func.trim(Applicant.khoa)) == k.lower())

    apps = q.order_by(Applicant.created_at.asc(), Applicant.ma_so_hv.asc()).all()
    if not apps:
        raise HTTPException(status_code=404, detail="Không có hồ sơ nào thuộc đợt đã chọn.")

    version_ids = {a.checklist_version_id for a in apps if a.checklist_version_id is not None}
    items_by_version = _load_items_by_version(db, version_ids)

    mssv_list = [a.ma_so_hv for a in apps]
    docs_by_app = _docs_by_mssv(db, mssv_list)

    pdf_bytes = render_batch_pdf(apps, items_by_version, docs_by_app)

    # tên file an toàn
    safe_dot = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in dot_norm)
    safe_khoa = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in (khoa or ""))
    suffix = f"{safe_dot}" + (f"_Khoa_{safe_khoa}" if safe_khoa else "")
    filename = f"Batch_Dot_{suffix}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename=\"{filename}\"'},
    )

# -------- Giữ route cũ để tương thích --------
@router.get("/print-by-dot")
def batch_print_by_dot_compat(
    dot: str = Query(..., description="Tên đợt cũ"),
    db: Session = Depends(get_db),
):
    return batch_print_dot(dot=dot, db=db)
