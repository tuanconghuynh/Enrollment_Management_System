from datetime import datetime, timedelta, date
import io
from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..models.applicant import Applicant, ApplicantDoc
from ..models.checklist import ChecklistItem
from ..services.pdf_service import render_batch_pdf
from sqlalchemy import func


router = APIRouter(prefix="/batch", tags=["batch"])

# -------- helpers --------
def _parse_day(raw: str) -> date:
    """
    Hỗ trợ 'YYYY-MM-DD' (input type=date) và 'dd/MM/yyyy' (gõ tay).
    """
    s = (raw or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    raise HTTPException(
        status_code=400,
        detail="Sai định dạng ngày. Dùng 'day=YYYY-MM-DD' hoặc 'date=dd/MM/yyyy'."
    )

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

def _docs_by_applicant(db: Session, app_ids):
    out = {}
    if not app_ids:
        return out
    docs = db.query(ApplicantDoc).filter(ApplicantDoc.applicant_id.in_(app_ids)).all()
    for d in docs:
        out.setdefault(d.applicant_id, []).append(d)
    return out

# -------- In PDF gộp theo NGÀY --------
@router.get("/print")
def batch_print(
    day: str | None = Query(None, description="YYYY-MM-DD"),
    date_q: str | None = Query(None, alias="date", description="dd/MM/yyyy"),
    db: Session = Depends(get_db),
):
    # Chấp nhận cả 'day' hoặc 'date'
    raw = day or date_q
    if not raw:
        raise HTTPException(status_code=400, detail="Thiếu tham số 'day' hoặc 'date'")

    d = _parse_day(raw)

    # Cover cả cột kiểu DATETIME lẫn DATE
    d1 = datetime.combine(d, datetime.min.time())
    d2 = d1 + timedelta(days=1)

    apps = (
        db.query(Applicant)
        .filter(Applicant.ngay_nhan_hs >= d1, Applicant.ngay_nhan_hs < d2)
        .order_by(Applicant.id.asc())
        .all()
    )
    if not apps:
        apps = (
            db.query(Applicant)
            .filter(Applicant.ngay_nhan_hs == d)
            .order_by(Applicant.id.asc())
            .all()
        )
    if not apps:
        raise HTTPException(
            status_code=404,
            detail=f"Không có hồ sơ nào trong ngày {d.strftime('%d/%m/%Y')}"
        )

    version_ids = {a.checklist_version_id for a in apps}
    items_by_version = _load_items_by_version(db, version_ids)
    docs_by_app = _docs_by_applicant(db, [a.id for a in apps])

    pdf_bytes = render_batch_pdf(apps, items_by_version, docs_by_app)
    filename = f"Batch_{d.isoformat()}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )

# -------- In PDF gộp theo ĐỢT (mới) --------
@router.get("/print-dot")
def batch_print_dot(
    dot: str = Query(..., description="Tên đợt, ví dụ: 'Đợt 1/2025' hoặc '9'"),
    khoa: str | None = Query(None, description="(Tuỳ chọn) Lọc theo Khóa, ví dụ: '27'"),
    db: Session = Depends(get_db),
):
    dot_norm = (dot or "").strip()
    if not dot_norm:
        raise HTTPException(status_code=400, detail="Thiếu tham số 'dot'")

    q = (
        db.query(Applicant)
        .filter(Applicant.dot.isnot(None))
        .filter(Applicant.dot.ilike(f"%{dot_norm}%"))
    )

    # nếu có truyền khóa thì lọc thêm theo khóa
    if (khoa or "").strip():
        k = khoa.strip()
        q = (
            q.filter(Applicant.khoa.isnot(None))
             .filter(func.lower(func.trim(Applicant.khoa)) == k.lower())
        )

    apps = q.order_by(Applicant.id.asc()).all()
    if not apps:
        raise HTTPException(status_code=404, detail="Không có hồ sơ nào thuộc đợt đã chọn")

    # lấy danh mục theo version
    version_ids = {a.checklist_version_id for a in apps}
    items_by_version = {}
    for vid in version_ids:
        qitems = db.query(ChecklistItem).filter(ChecklistItem.version_id == vid)
        if hasattr(ChecklistItem, "order_index"):
            qitems = qitems.order_by(getattr(ChecklistItem, "order_index").asc())
        elif hasattr(ChecklistItem, "order_no"):
            qitems = qitems.order_by(getattr(ChecklistItem, "order_no").asc())
        else:
            qitems = qitems.order_by(ChecklistItem.id.asc())
        items_by_version[vid] = qitems.all()

    # map docs theo applicant
    app_ids = [a.id for a in apps]
    docs = db.query(ApplicantDoc).filter(ApplicantDoc.applicant_id.in_(app_ids)).all()
    docs_by_app = {}
    for ddoc in docs:
        docs_by_app.setdefault(ddoc.applicant_id, []).append(ddoc)

    pdf_bytes = render_batch_pdf(apps, items_by_version, docs_by_app)

    # tên file an toàn
    safe_dot = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in dot_norm)
    safe_khoa = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in (khoa or ""))
    suffix = f"{safe_dot}" + (f"_Khoa_{safe_khoa}" if safe_khoa else "")
    filename = f"Batch_Dot_{suffix}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )

# -------- Giữ route cũ để tương thích (trỏ sang /print-dot) --------
@router.get("/print-by-dot")
def batch_print_by_dot_compat(
    dot: str = Query(..., description="Tên đợt cũ"),
    db: Session = Depends(get_db),
):
    return batch_print_dot(dot=dot, db=db)
