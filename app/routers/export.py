# app/routers/export.py
from __future__ import annotations

from datetime import datetime, timedelta, date
import io
from typing import List, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from starlette.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.routers.auth import require_roles
from app.db.session import get_db
from app.models.applicant import Applicant, ApplicantDoc
from app.models.checklist import ChecklistItem
from app.services.pdf_service import (
    render_single_pdf,
    render_single_pdf_a5,
    render_batch_pdf,  # (giữ import nếu dùng nơi khác)
)

from openpyxl import Workbook
from openpyxl.utils import get_column_letter

from app.utils.soft_delete import exclude_deleted, ensure_not_deleted

router = APIRouter()  # không prefix; main sẽ mount /api


# ================= Helpers chung =================
def _parse_day_any(raw: str) -> date:
    """
    Ưu tiên 'dd/MM/YYYY', chấp nhận 'YYYY-MM-DD'.
    """
    s = (raw or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    raise HTTPException(
        status_code=400,
        detail="Sai định dạng ngày. Dùng 'date=dd/MM/YYYY' (khuyến nghị) hoặc 'day=YYYY-MM-DD'.",
    )


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


def _docs_map_by_mssv(docs: List[ApplicantDoc]) -> Dict[str, Dict[str, int]]:
    """
    Nhóm theo MSSV:
      -> { ma_so_hv: { code: so_luong, ... }, ... }
    """
    out: Dict[str, Dict[str, int]] = {}
    for d in docs:
        out.setdefault(d.applicant_ma_so_hv, {})[d.code] = int(d.so_luong or 0)
    return out


def _fmt_date_excel(v: Optional[object]) -> str:
    """
    Chuẩn hoá output Excel về dd/MM/YYYY.
    """
    if v is None or v == "":
        return ""
    if isinstance(v, datetime):
        v = v.date()
    if isinstance(v, date):
        return v.strftime("%d/%m/%Y")
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s[:10], fmt).strftime("%d/%m/%Y")
        except Exception:
            continue
    return s


def _build_excel_bytes(apps: List[Applicant], docs: List[ApplicantDoc], items_all: List[ChecklistItem]) -> bytes:
    """
    Xuất 1 sheet duy nhất 'Ho so' theo header cố định + các cột checklist.
    Group tài liệu theo MSSV.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Ho so"

    # Header cố định (+ Dân tộc)
    base_headers = [
        "STT", "Mã hồ sơ", "Ngày nhận", "Email học viên", "Họ tên",
        "MSHV", "Ngày sinh", "Số ĐT", "Ngành nhập học", "Đợt", "Khóa",
        "Đã TN trước đó", "Ghi chú", "Người nhận (ký tên)",
        "Dân tộc",  # ✅ thêm cột Dân tộc
    ]
    # Thêm cột checklist
    item_headers = [getattr(it, "display_name", None) or it.code for it in items_all]
    headers = base_headers + item_headers
    ws.append(headers)

    # Data
    docs_by_mssv = _docs_map_by_mssv(docs)

    for idx, a in enumerate(apps, start=1):
        base_row = [
            idx,
            a.ma_ho_so or "",
            _fmt_date_excel(getattr(a, "ngay_nhan_hs", None)),
            a.email_hoc_vien or "",
            a.ho_ten or "",
            a.ma_so_hv or "",
            _fmt_date_excel(getattr(a, "ngay_sinh", None)),
            a.so_dt or "",
            getattr(a, "nganh_nhap_hoc", None) or getattr(a, "nganh", None) or "",
            a.dot or "",
            getattr(a, "khoa", "") or "",
            a.da_tn_truoc_do or "",
            a.ghi_chu or "",
            a.nguoi_nhan_ky_ten or "",
            getattr(a, "dan_toc", None) or "",  # ✅ giá trị Dân tộc
        ]
        dm = docs_by_mssv.get(a.ma_so_hv, {})
        doc_row = [int(dm.get(it.code, 0)) for it in items_all]
        ws.append(base_row + doc_row)

    # Freeze header & auto width
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


def _get_app_by_mssv(db: Session, ma_so_hv: str) -> Applicant:
    a = db.query(Applicant).filter(Applicant.ma_so_hv == ma_so_hv).first()
    if not a:
        raise HTTPException(status_code=404, detail="Applicant not found")
    ensure_not_deleted(a)  # 🔒 hồ sơ xoá -> 410
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


def _get_docs_for_mssv(db: Session, ma_so_hv: str):
    return db.query(ApplicantDoc).filter(ApplicantDoc.applicant_ma_so_hv == ma_so_hv).all()


# ================= EXPORT EXCEL THEO NGÀY =================
@router.get("/export/excel")
def export_excel(
    day: str | None = Query(None, description="YYYY-MM-DD"),
    date_q: str | None = Query(None, alias="date", description="dd/MM/YYYY"),
    db: Session = Depends(get_db),
    user=Depends(require_roles("Admin", "NhanVien")),
):
    raw = date_q or day
    if not raw:
        raise HTTPException(status_code=400, detail="Thiếu tham số 'date=dd/MM/YYYY' hoặc 'day=YYYY-MM-DD'")
    d = _parse_day_any(raw)

    d1 = datetime.combine(d, datetime.min.time())
    d2 = d1 + timedelta(days=1)

    # Lọc theo khoảng thời gian (datetime) trước
    q = db.query(Applicant).filter(Applicant.ngay_nhan_hs >= d1, Applicant.ngay_nhan_hs < d2)
    q = exclude_deleted(Applicant, q)
    apps = q.order_by(Applicant.created_at.asc(), Applicant.ma_so_hv.asc()).all()

    # Fallback nếu cột trong DB là DATE (không có time)
    if not apps:
        q = exclude_deleted(Applicant, db.query(Applicant).filter(Applicant.ngay_nhan_hs == d))
        apps = q.order_by(Applicant.created_at.asc(), Applicant.ma_so_hv.asc()).all()

    apps = [a for a in apps if ensure_not_deleted(a, raise_http_exception=False)]
    if not apps:
        raise HTTPException(status_code=404, detail=f"Không có hồ sơ trong ngày {d.strftime('%d/%m/%Y')}")

    mssv_list = [a.ma_so_hv for a in apps]
    docs = db.query(ApplicantDoc).filter(ApplicantDoc.applicant_ma_so_hv.in_(mssv_list)).all()

    version_ids = {a.checklist_version_id for a in apps if a.checklist_version_id}
    items_all = _items_merged_by_versions(db, version_ids) if version_ids else []

    xls_bytes = _build_excel_bytes(apps, docs, items_all)
    filename = f"Export_{d.strftime('%d-%m-%Y')}.xlsx"
    return StreamingResponse(
        io.BytesIO(xls_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename=\"{filename}\"'},
    )


# ================= EXPORT EXCEL THEO ĐỢT =================
@router.get("/export/excel-dot")
def export_excel_dot(
    dot: str = Query(..., description="Ví dụ: 'Đợt 1/2025' hoặc '9'"),
    khoa: str | None = Query(None, description="(Tuỳ chọn) Lọc theo Khóa, ví dụ: '27'"),
    db: Session = Depends(get_db),
    user=Depends(require_roles("Admin", "NhanVien")),
):
    key = (dot or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="Thiếu tham số 'dot'")

    q = (
        db.query(Applicant)
        .filter(Applicant.dot.isnot(None))
        .filter(Applicant.dot.ilike(f"%{key}%"))
    )
    if (khoa or "").strip():
        k = khoa.strip()
        q = q.filter(Applicant.khoa.isnot(None)).filter(func.lower(func.trim(Applicant.khoa)) == k.lower())

    q = exclude_deleted(Applicant, q)

    apps = q.order_by(Applicant.created_at.asc(), Applicant.ma_so_hv.asc()).all()
    apps = [a for a in apps if ensure_not_deleted(a, raise_http_exception=False)]
    if not apps:
        raise HTTPException(status_code=404, detail="Không có hồ sơ nào phù hợp")

    mssv_list = [a.ma_so_hv for a in apps]
    docs = db.query(ApplicantDoc).filter(ApplicantDoc.applicant_ma_so_hv.in_(mssv_list)).all()

    # Hợp nhất danh mục nhiều version
    items_all = _items_merged_by_versions(db, {a.checklist_version_id for a in apps if a.checklist_version_id})

    xls_bytes = _build_excel_bytes(apps, docs, items_all)
    safe_dot = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in key)
    safe_khoa = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in (khoa or ""))
    suffix = f"{safe_dot}" + (f"_Khoa_{safe_khoa}" if safe_khoa else "")
    filename = f"Export_Dot_{suffix}.xlsx"
    return StreamingResponse(
        io.BytesIO(xls_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename=\"{filename}\"'},
    )


# ================= PRINT 1 HỒ SƠ (theo MSSV) =================
@router.get("/print/a5/{ma_so_hv}", summary="In 01 hồ sơ A5 (ngang) theo MSSV")
def print_a5(ma_so_hv: str, db: Session = Depends(get_db)):
    app = _get_app_by_mssv(db, ma_so_hv)  # đã chặn deleted
    items = _get_items_for_app(db, app)
    docs = _get_docs_for_mssv(db, ma_so_hv)
    pdf_bytes = render_single_pdf_a5(app, items, docs)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename=\"{app.ma_ho_so or ma_so_hv}_A5.pdf\"'},
    )


@router.get("/print/a4/{ma_so_hv}", summary="In 01 hồ sơ A4 (dọc) theo MSSV")
def print_a4(ma_so_hv: str, db: Session = Depends(get_db)):
    app = _get_app_by_mssv(db, ma_so_hv)
    items = _get_items_for_app(db, app)
    docs = _get_docs_for_mssv(db, ma_so_hv)
    pdf_bytes = render_single_pdf(app, items, docs)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename=\"{app.ma_ho_so or ma_so_hv}_A4.pdf\"'},
    )
