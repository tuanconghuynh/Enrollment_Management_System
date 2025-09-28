# app/routers/export.py
from datetime import datetime, timedelta, date
import io
from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..models.applicant import Applicant, ApplicantDoc
from ..models.checklist import ChecklistItem
from ..services.export_service import build_excel_bytes

router = APIRouter(prefix="/export", tags=["export"])

def _parse_day(day_str: str) -> date:
    """
    Hỗ trợ cả 'YYYY-MM-DD' (input type=date) và 'dd/MM/yyyy' (người dùng gõ tay).
    """
    day_str = (day_str or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(day_str, fmt).date()
        except ValueError:
            pass
    raise HTTPException(
        status_code=400,
        detail="Sai định dạng 'day' (chấp nhận YYYY-MM-DD hoặc dd/MM/yyyy)"
    )

@router.get("/excel")
def export_excel(
    day: str = Query(..., description="YYYY-MM-DD hoặc dd/MM/yyyy"),
    db: Session = Depends(get_db),
):
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
        raise HTTPException(
            status_code=404,
            detail=f"Không có hồ sơ nào trong ngày {d.strftime('%d/%m/%Y')}"
        )

    # Lấy danh mục để làm header doc_* theo đúng thứ tự (nếu có cột)
    vid = apps[0].checklist_version_id
    q = db.query(ChecklistItem).filter(ChecklistItem.version_id == vid)
    if hasattr(ChecklistItem, "order_index"):
        q = q.order_by(getattr(ChecklistItem, "order_index").asc())
    elif hasattr(ChecklistItem, "order_no"):
        q = q.order_by(getattr(ChecklistItem, "order_no").asc())
    else:
        q = q.order_by(ChecklistItem.id.asc())
    items = q.all()

    # Gom docs theo applicant
    app_ids = [a.id for a in apps]
    docs = db.query(ApplicantDoc).filter(ApplicantDoc.applicant_id.in_(app_ids)).all()

    # Xuất Excel
    xls_bytes = build_excel_bytes(apps, docs, items)
    filename = f"Export_{d.isoformat()}.xlsx"
    return StreamingResponse(
        io.BytesIO(xls_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
@router.get("/excel")
def export_excel(day: str = Query(..., description="YYYY-MM-DD"), db: Session = Depends(get_db)):
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

    app_ids = [a.id for a in apps]
    docs = db.query(ApplicantDoc).filter(ApplicantDoc.applicant_id.in_(app_ids)).all()

    vid = apps[0].checklist_version_id
    items_q = db.query(ChecklistItem).filter(ChecklistItem.version_id == vid)
    items = items_q.all()

    xls_bytes = build_excel_bytes(apps, docs, items)
    filename = f"Export_{d.isoformat()}.xlsx"
    return StreamingResponse(
        io.BytesIO(xls_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

# ---------------- NEW: Xuất Excel theo ĐỢT ----------------
@router.get("/excel-dot")
def export_excel_dot(dot: str = Query(..., description="Tên đợt, ví dụ: 'Đợt 1/2025' hoặc '9'"),
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

    # Hợp nhất danh mục của TẤT CẢ version trong đợt để không mất cột
    version_ids = {a.checklist_version_id for a in apps}
    code_seen = {}
    items_all = []
    for vid in version_ids:
        q = db.query(ChecklistItem).filter(ChecklistItem.version_id == vid)
        if hasattr(ChecklistItem, "order_no"):
            q = q.order_by(ChecklistItem.order_no.asc())
        else:
            q = q.order_by(ChecklistItem.id.asc())
        for it in q.all():
            if it.code not in code_seen:
                code_seen[it.code] = True
                items_all.append(it)

    xls_bytes = build_excel_bytes(apps, docs, items_all)
    filename = f"Export_Dot_{key}.xlsx"
    return StreamingResponse(
        io.BytesIO(xls_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )