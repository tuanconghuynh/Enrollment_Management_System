# app/routers/export.py
from datetime import datetime, timedelta, date
import io
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from starlette.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..models.applicant import Applicant, ApplicantDoc
from ..models.checklist import ChecklistItem
from ..services.export_service import build_excel_bytes
from ..services.pdf_service import (
    render_single_pdf,        # A4 dọc truyền thống (tuỳ chọn)
    render_single_pdf_a5,     # A5 ngang
    a5_two_up_to_a4           # gộp 2 bản A5 lên 1 trang A4
)

router = APIRouter()  # <-- KHÔNG đặt prefix ở đây

# ----------------- Helpers chung -----------------
def _parse_day(day_str: str) -> date:
    day_str = (day_str or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(day_str, fmt).date()
        except ValueError:
            pass
    raise HTTPException(status_code=400, detail="Sai định dạng 'day'")

def _get_app(db: Session, app_id: int) -> Applicant:
    obj = db.query(Applicant).filter(Applicant.id == app_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Applicant not found")
    return obj

def _get_items_for_app(db: Session, app: Applicant):
    ver_id = getattr(app, "checklist_version_id", None)
    q = db.query(ChecklistItem)
    if ver_id:
        q = q.filter(ChecklistItem.version_id == ver_id)
    # Sắp thứ tự nếu có cột order_index/order_no
    if hasattr(ChecklistItem, "order_index"):
        q = q.order_by(getattr(ChecklistItem, "order_index").asc())
    elif hasattr(ChecklistItem, "order_no"):
        q = q.order_by(getattr(ChecklistItem, "order_no").asc())
    else:
        q = q.order_by(ChecklistItem.id.asc())
    return q.all()

def _get_docs_for_app(db: Session, app_id: int):
    return db.query(ApplicantDoc).filter(ApplicantDoc.applicant_id == app_id).all()

# ----------------- EXPORT EXCEL -----------------
@router.get("/export/excel")
def export_excel(day: str = Query(..., description="YYYY-MM-DD hoặc dd/MM/yyyy"),
                 db: Session = Depends(get_db)):
    d = _parse_day(day)
    d1 = datetime.combine(d, datetime.min.time())
    d2 = d1 + timedelta(days=1)

    apps = (
        db.query(Applicant)
        .filter(Applicant.ngay_nhan_hs >= d1, Applicant.ngay_nhan_hs < d2)
        .order_by(Applicant.id.asc())
        .all()
    )
    if not apps:
        # trường hợp cột DATE
        apps = (
            db.query(Applicant)
            .filter(Applicant.ngay_nhan_hs == d)
            .order_by(Applicant.id.asc())
            .all()
        )
    if not apps:
        raise HTTPException(status_code=404, detail=f"Không có hồ sơ trong ngày {d.strftime('%d/%m/%Y')}")

    app_ids = [a.id for a in apps]
    docs = db.query(ApplicantDoc).filter(ApplicantDoc.applicant_id.in_(app_ids)).all()

    vid = apps[0].checklist_version_id
    q = db.query(ChecklistItem).filter(ChecklistItem.version_id == vid)
    if hasattr(ChecklistItem, "order_index"):
        q = q.order_by(getattr(ChecklistItem, "order_index").asc())
    elif hasattr(ChecklistItem, "order_no"):
        q = q.order_by(getattr(ChecklistItem, "order_no").asc())
    else:
        q = q.order_by(ChecklistItem.id.asc())
    items = q.all()

    xls_bytes = build_excel_bytes(apps, docs, items)
    filename = f"Export_{d.isoformat()}.xlsx"
    return StreamingResponse(
        io.BytesIO(xls_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@router.get("/export/excel-dot")
def export_excel_dot(dot: str = Query(..., description="Ví dụ: 'Đợt 1/2025' hoặc '9'"),
                     db: Session = Depends(get_db)):
    key = (dot or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="Thiếu tham số 'dot'")

    apps = (
        db.query(Applicant)
        .filter(Applicant.dot.isnot(None))
        .filter(Applicant.dot.ilike(f"%{key}%"))
        .order_by(Applicant.id.asc())
        .all()
    )
    if not apps:
        raise HTTPException(status_code=404, detail="Không có hồ sơ nào thuộc đợt đã chọn")

    app_ids = [a.id for a in apps]
    docs = db.query(ApplicantDoc).filter(ApplicantDoc.applicant_id.in_(app_ids)).all()

    # Hợp nhất danh mục của nhiều version
    code_seen = set()
    items_all = []
    ver_ids = {a.checklist_version_id for a in apps}
    for vid in ver_ids:
        q = db.query(ChecklistItem).filter(ChecklistItem.version_id == vid)
        if hasattr(ChecklistItem, "order_index"):
            q = q.order_by(getattr(ChecklistItem, "order_index").asc())
        elif hasattr(ChecklistItem, "order_no"):
            q = q.order_by(getattr(ChecklistItem, "order_no").asc())
        for it in q.all():
            if it.code not in code_seen:
                code_seen.add(it.code)
                items_all.append(it)

    xls_bytes = build_excel_bytes(apps, docs, items_all)
    filename = f"Export_Dot_{key}.xlsx"
    return StreamingResponse(
        io.BytesIO(xls_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

# ----------------- PRINT ROUTES -----------------
@router.get("/print/a5/{app_id}", summary="In 01 hồ sơ A5 (ngang)")
def print_a5(app_id: int, db: Session = Depends(get_db)):
    app = _get_app(db, app_id)
    items = _get_items_for_app(db, app)
    docs  = _get_docs_for_app(db, app_id)
    pdf_bytes = render_single_pdf_a5(app, items, docs)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename=\"{app.ma_ho_so or app_id}_A5.pdf\"'}
    )

@router.get("/print/a4-two-up/{app_id}", summary="In 01 hồ sơ A4 (2-up)")
def print_a4_two_up(app_id: int, db: Session = Depends(get_db)):
    app = _get_app(db, app_id)
    items = _get_items_for_app(db, app)
    docs  = _get_docs_for_app(db, app_id)
    a5_pdf = render_single_pdf_a5(app, items, docs)
    a4_pdf = a5_two_up_to_a4(a5_pdf)
    return Response(
        content=a4_pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename=\"{app.ma_ho_so or app_id}_A4_2up.pdf\"'}
    )

# (tuỳ chọn) A4 dọc truyền thống
@router.get("/print/a4/{app_id}", summary="In 01 hồ sơ A4 (dọc)")
def print_a4(app_id: int, db: Session = Depends(get_db)):
    app = _get_app(db, app_id)
    items = _get_items_for_app(db, app)
    docs  = _get_docs_for_app(db, app_id)
    pdf_bytes = render_single_pdf(app, items, docs)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename=\"{app.ma_ho_so or app_id}_A4.pdf\"'}
    )

@router.get("/print/a4-two-up/{app_id}")
def print_a4_two_up_single(app_id: int, db: Session = Depends(get_db)):
    a = db.query(Applicant).get(app_id)
    if not a:
        raise HTTPException(status_code=404, detail="Applicant not found")

    # Lấy items + docs theo version của hồ sơ
    items = db.query(ChecklistItem).filter(ChecklistItem.version_id == a.checklist_version_id).all()
    docs  = db.query(ApplicantDoc).filter(ApplicantDoc.applicant_id == a.id).all()

    # Tạo A5 của chính hồ sơ này
    a4_bytes = render_single_pdf_a5(a, items, docs)

    # Nhân đôi & ghép 2-up ra A4 dọc
    a4_bytes = a5_two_up_to_a4(a4_bytes)

    return StreamingResponse(
        io.BytesIO(a4_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="A4_2up_{a.ma_ho_so or a.id}.pdf"'}
    )
