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

def _parse_day(day_str: str) -> date:
    """
    Hỗ trợ cả 'YYYY-MM-DD' (từ <input type=date>) và 'dd/MM/yyyy' (người dùng gõ tay).
    """
    day_str = (day_str or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(day_str, fmt).date()
        except ValueError:
            pass
    raise HTTPException(status_code=400, detail="Sai định dạng 'day' (chấp nhận YYYY-MM-DD hoặc dd/MM/yyyy)")

@router.get("/print")
def batch_print(day: str = Query(..., description="YYYY-MM-DD hoặc dd/MM/yyyy"),
                db: Session = Depends(get_db)):
    # Parse ngày
    d = _parse_day(day)

    # Lấy hồ sơ trong ngày (cover cả kiểu DATE lẫn DATETIME)
    d1 = datetime.combine(d, datetime.min.time())
    d2 = d1 + timedelta(days=1)

    apps = (
        db.query(Applicant)
        .filter(Applicant.ngay_nhan_hs >= d1, Applicant.ngay_nhan_hs < d2)
        .order_by(Applicant.id.asc())
        .all()
    )
    if not apps:
        # Fallback nếu cột là DATE
        apps = (
            db.query(Applicant)
            .filter(Applicant.ngay_nhan_hs == d)
            .order_by(Applicant.id.asc())
            .all()
        )
    if not apps:
        # Thông báo có kèm ngày dd/MM/yyyy
        raise HTTPException(
            status_code=404,
            detail=f"Không có hồ sơ nào trong ngày {d.strftime('%d/%m/%Y')}"
        )

    # Lấy danh mục theo version (sắp xếp linh hoạt: order_index -> order_no -> id)
    version_ids = {a.checklist_version_id for a in apps}
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

    # Map doc theo applicant_id
    app_ids = [a.id for a in apps]
    docs = db.query(ApplicantDoc).filter(ApplicantDoc.applicant_id.in_(app_ids)).all()
    docs_by_app = {}
    for ddoc in docs:
        docs_by_app.setdefault(ddoc.applicant_id, []).append(ddoc)

    pdf_bytes = render_batch_pdf(apps, items_by_version, docs_by_app)
    filename = f"Batch_{d.isoformat()}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )

@router.get("/print-by-dot")
def batch_print_by_dot(dot: str = Query(..., min_length=1), db: Session = Depends(get_db)):
    dot_norm = (dot or "").strip()
    if not dot_norm:
        raise HTTPException(status_code=400, detail="Thiếu tham số 'dot'")

    # Lấy toàn bộ hồ sơ thuộc đợt (không phân biệt hoa/thường)
    apps = (
        db.query(Applicant)
        .filter(func.lower(Applicant.dot) == dot_norm.lower())
        .order_by(Applicant.id.asc())
        .all()
    )
    if not apps:
        raise HTTPException(status_code=404, detail=f"Không có hồ sơ nào thuộc đợt '{dot_norm}'")

    # Lấy danh mục theo version (y như /batch/print)
    version_ids = {a.checklist_version_id for a in apps}
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

    # Map doc theo applicant_id
    app_ids = [a.id for a in apps]
    docs = db.query(ApplicantDoc).filter(ApplicantDoc.applicant_id.in_(app_ids)).all()
    docs_by_app = {}
    for ddoc in docs:
        docs_by_app.setdefault(ddoc.applicant_id, []).append(ddoc)

    pdf_bytes = render_batch_pdf(apps, items_by_version, docs_by_app)

    # filename an toàn
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in dot_norm)
    filename = f"Batch_Dot_{safe}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
@router.get("/print")
def batch_print(day: str = Query(..., description="YYYY-MM-DD"), db: Session = Depends(get_db)):
    try:
        d = datetime.strptime(day, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Sai định dạng 'day' (YYYY-MM-DD)")

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
        raise HTTPException(status_code=404, detail="Không có hồ sơ nào trong ngày đã chọn")

    version_ids = {a.checklist_version_id for a in apps}
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

    app_ids = [a.id for a in apps]
    docs = db.query(ApplicantDoc).filter(ApplicantDoc.applicant_id.in_(app_ids)).all()
    docs_by_app = {}
    for ddoc in docs:
        docs_by_app.setdefault(ddoc.applicant_id, []).append(ddoc)

    pdf_bytes = render_batch_pdf(apps, items_by_version, docs_by_app)
    filename = f"Batch_{d.isoformat()}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )

# ---------------- NEW: In PDF gộp theo ĐỢT ----------------
@router.get("/print-dot")
def batch_print_dot(dot: str = Query(..., description="Tên đợt, ví dụ: 'Đợt 1/2025' hoặc '9'"),
                    db: Session = Depends(get_db)):
    key = (dot or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="Thiếu tham số 'dot'")

    # linh hoạt: so khớp chứa chuỗi (case-insensitive)
    apps = (
        db.query(Applicant)
        .filter(Applicant.dot.isnot(None))
        .filter(Applicant.dot.ilike(f"%{key}%"))
        .order_by(Applicant.id.asc())
        .all()
    )
    if not apps:
        raise HTTPException(status_code=404, detail="Không có hồ sơ nào thuộc đợt đã chọn")

    # chuẩn bị danh mục theo version
    version_ids = {a.checklist_version_id for a in apps}
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

    app_ids = [a.id for a in apps]
    docs = db.query(ApplicantDoc).filter(ApplicantDoc.applicant_id.in_(app_ids)).all()
    docs_by_app = {}
    for ddoc in docs:
        docs_by_app.setdefault(ddoc.applicant_id, []).append(ddoc)

    pdf_bytes = render_batch_pdf(apps, items_by_version, docs_by_app)
    filename = f"Batch_Dot_{key}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )