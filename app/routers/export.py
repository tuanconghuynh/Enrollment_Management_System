# app/routers/export.py
from datetime import datetime, timedelta, date
import io
from typing import List, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from starlette.responses import StreamingResponse
from sqlalchemy.orm import Session

from .auth import require_roles
from ..db.session import get_db
from ..models.applicant import Applicant, ApplicantDoc
from ..models.checklist import ChecklistItem
from ..services.pdf_service import (
    render_single_pdf,
    render_single_pdf_a5,
    a5_two_up_to_a4,
)

# NEW: build Excel trực tiếp (khỏi lệ thuộc export_service cũ)
from openpyxl import Workbook
from openpyxl.utils import get_column_letter

router = APIRouter()  # không prefix; main sẽ mount /api

# ================= Helpers chung =================
def _parse_day_any(raw: str) -> date:
    s = (raw or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    raise HTTPException(status_code=400, detail="Sai định dạng ngày. Dùng 'day=YYYY-MM-DD' hoặc 'date=dd/MM/yyyy'.")

def _items_merged_by_versions(db: Session, version_ids: set) -> List[ChecklistItem]:
    code_seen = set()
    items: List[ChecklistItem] = []
    for vid in version_ids:
        q = db.query(ChecklistItem).filter(ChecklistItem.version_id == vid)
        if hasattr(ChecklistItem, "order_index"):
            q = q.order_by(getattr(ChecklistItem, "order_index").asc())
        elif hasattr(ChecklistItem, "order_no"):
            q = q.order_by(getattr(ChecklistItem, "order_no").asc())
        else:
            q = q.order_by(ChecklistItem.id.asc())
        for it in q.all():
            if it.code not in code_seen:
                code_seen.add(it.code)
                items.append(it)
    return items

def _docs_map(docs: List[ApplicantDoc]) -> Dict[int, Dict[str, int]]:
    """
    -> { applicant_id: { code: so_luong, ... }, ... }
    """
    out: Dict[int, Dict[str, int]] = {}
    for d in docs:
        out.setdefault(d.applicant_id, {})[d.code] = int(d.so_luong or 0)
    return out

def _fmt_date_excel(v):
    if v is None or v == "":
        return ""
    if isinstance(v, datetime):
        v = v.date()
    if isinstance(v, date):
        return v.strftime("%d/%m/%Y")
    # chuỗi: cố gắng chuẩn hoá 2025-10-02 -> 02/10/2025
    s = str(v).strip()
    m = None
    try:
        # YYYY-MM-DD
        m = datetime.strptime(s[:10], "%Y-%m-%d").date()
        return m.strftime("%d/%m/%Y")
    except Exception:
        return s

def _build_excel_bytes_compat(apps: List[Applicant], docs: List[ApplicantDoc], items_all: List[ChecklistItem]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Ho so"

    # Header cố định
    base_headers = [
        "STT", "Mã hồ sơ", "Ngày nhận", "Họ tên", "MSHV",
        "Ngày sinh", "Số ĐT", "Ngành nhập học", "Đợt", "Khóa",
        "Đã TN trước đó", "Ghi chú", "Người nhận (ký tên)"
    ]
    # Thêm cột checklist
    item_headers = [getattr(it, "display_name", getattr(it, "code", "")) or it.code for it in items_all]
    headers = base_headers + item_headers
    ws.append(headers)

    # Dữ liệu
    docs_by_app = _docs_map(docs)

    for idx, a in enumerate(apps, start=1):
        base_row = [
            idx,
            a.ma_ho_so or "",
            _fmt_date_excel(getattr(a, "ngay_nhan_hs", None)),
            a.ho_ten or "",
            a.ma_so_hv or "",
            _fmt_date_excel(getattr(a, "ngay_sinh", None)),
            a.so_dt or "",
            a.nganh_nhap_hoc or "",
            a.dot or "",
            getattr(a, "khoa", "") or "",
            a.da_tn_truoc_do or "",
            a.ghi_chu or "",
            a.nguoi_nhan_ky_ten or "",
        ]
        dm = docs_by_app.get(a.id, {})
        doc_row = [int(dm.get(it.code, 0)) for it in items_all]
        ws.append(base_row + doc_row)

    # Freeze header & auto width tương đối
    ws.freeze_panes = "A2"
    for col in range(1, len(headers) + 1):
        letter = get_column_letter(col)
        max_len = 0
        for cell in ws[letter]:
            val = "" if cell.value is None else str(cell.value)
            if len(val) > max_len:
                max_len = len(val)
        ws.column_dimensions[letter].width = min(max(10, max_len + 2), 40)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

def _get_app(db: Session, app_id: int) -> Applicant:
    a = db.query(Applicant).filter(Applicant.id == app_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Applicant not found")
    return a

def _get_items_for_app(db: Session, app: Applicant):
    ver_id = getattr(app, "checklist_version_id", None)
    q = db.query(ChecklistItem)
    if ver_id:
        q = q.filter(ChecklistItem.version_id == ver_id)
    if hasattr(ChecklistItem, "order_index"):
        q = q.order_by(getattr(ChecklistItem, "order_index").asc())
    elif hasattr(ChecklistItem, "order_no"):
        q = q.order_by(getattr(ChecklistItem, "order_no").asc())
    else:
        q = q.order_by(ChecklistItem.id.asc())
    return q.all()

def _get_docs_for_app(db: Session, app_id: int):
    return db.query(ApplicantDoc).filter(ApplicantDoc.applicant_id == app_id).all()

# ================= EXPORT EXCEL THEO NGÀY =================
@router.get("/export/excel")
def export_excel(
    day: str | None = Query(None, description="YYYY-MM-DD"),
    date_q: str | None = Query(None, alias="date", description="dd/MM/yyyy"),
    db: Session = Depends(get_db),
    user=Depends(require_roles("Admin", "NhanVien")),
):
    raw = day or date_q
    if not raw:
        raise HTTPException(status_code=400, detail="Thiếu tham số 'day' hoặc 'date'")
    d = _parse_day_any(raw)

    # Bao phủ DATE lẫn DATETIME
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
        raise HTTPException(status_code=404, detail=f"Không có hồ sơ trong ngày {d.strftime('%d/%m/%Y')}")

    app_ids = [a.id for a in apps]
    docs = db.query(ApplicantDoc).filter(ApplicantDoc.applicant_id.in_(app_ids)).all()
    version_ids = {a.checklist_version_id for a in apps if a.checklist_version_id}
    items_all = _items_merged_by_versions(db, version_ids) if version_ids else []

    xls_bytes = _build_excel_bytes_compat(apps, docs, items_all)
    filename = f"Export_{d.isoformat()}.xlsx"
    return StreamingResponse(
        io.BytesIO(xls_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

# ================= EXPORT EXCEL THEO ĐỢT =================
@router.get("/export/excel-dot")
def export_excel_dot(
    dot: str = Query(..., description="Ví dụ: 'Đợt 1/2025' hoặc '9'"),
    db: Session = Depends(get_db),
    user=Depends(require_roles("Admin", "NhanVien")),
):
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
        raise HTTPException(status_code=404, detail=f"Không có hồ sơ nào thuộc đợt '{key}'")

    app_ids = [a.id for a in apps]
    docs = db.query(ApplicantDoc).filter(ApplicantDoc.applicant_id.in_(app_ids)).all()
    version_ids = {a.checklist_version_id for a in apps if a.checklist_version_id}
    items_all = _items_merged_by_versions(db, version_ids) if version_ids else []

    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in key)
    xls_bytes = _build_excel_bytes_compat(apps, docs, items_all)
    filename = f"Export_Dot_{safe}.xlsx"
    return StreamingResponse(
        io.BytesIO(xls_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

# ================= PRINT 1 HỒ SƠ =================
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
# ================= PRINT BATCH =================
