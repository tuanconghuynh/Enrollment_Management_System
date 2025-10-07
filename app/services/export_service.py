# ================================
# app/services/export_service.py
# ================================
from __future__ import annotations
from typing import List, Dict, Iterable, Any, Optional
from io import BytesIO
from datetime import date, datetime

from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from openpyxl.styles import Alignment

from ..models import Applicant, ApplicantDoc, ChecklistItem

DOC_PREFIX = "doc_"


# ---------- Helper ----------
def _parse_to_date(v: Optional[object]) -> Optional[date]:
    if v in (None, ""):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None

def _autosize(ws):
    ws.freeze_panes = "A2"
    for col in ws.columns:
        w = max(10, *(len(str(c.value)) if c.value else 0 for c in col)) + 2
        ws.column_dimensions[col[0].column_letter].width = min(w, 40)


# ---------- Export 1: có cột checklist ----------
def build_excel_bytes_by_items(apps: List[Applicant], docs: List[ApplicantDoc], items: List[ChecklistItem]) -> bytes:
    docs_by_mssv: Dict[str, Dict[str, int]] = {}
    for d in docs:
        docs_by_mssv.setdefault(d.applicant_ma_so_hv, {})[d.code] = int(d.so_luong or 0)

    base_headers = [
        "Ngày nhận HS", "Niên Khóa", "Mã hồ sơ", "Mã số HV", "Họ tên",
        "Email học viên", "Ngày sinh", "Số ĐT", "Ngành nhập học",
        "Đợt", "Đối tượng", "Ghi chú", "Printed"
    ]
    doc_headers = [f"{DOC_PREFIX}{it.code}" for it in items or []]
    headers = base_headers + doc_headers

    wb = Workbook()
    ws = wb.active
    ws.title = "Data_TongNgay"
    ws.append(headers)

    for a in apps:
        dm = docs_by_mssv.get(a.ma_so_hv, {})
        row = [
            _parse_to_date(a.ngay_nhan_hs),
            getattr(a, "khoa", ""),
            a.ma_ho_so or "",
            a.ma_so_hv or "",
            a.ho_ten or "",
            getattr(a, "email_hoc_vien", "") or "",
            _parse_to_date(a.ngay_sinh),
            a.so_dt or "",
            a.nganh_nhap_hoc or "",
            a.dot or "",
            a.da_tn_truoc_do or "",
            a.ghi_chu or "",
            bool(a.printed),
        ]
        for it in items or []:
            qty = int(dm.get(it.code, 0))
            row.append("" if qty == 0 else qty)
        ws.append(row)

    # format cột ngày
    for col in (1, 7):
        for cell in ws.iter_cols(min_col=col, max_col=col, min_row=2):
            for c in cell:
                if isinstance(c.value, (date, datetime)):
                    c.number_format = "dd/mm/yyyy"
                    c.alignment = Alignment(horizontal="center")

    _autosize(ws)
    out = BytesIO()
    wb.save(out)
    out.seek(0)
    return out.getvalue()


# ---------- Export 2: bảng đơn giản ----------
def build_excel_bytes_simple(rows: Iterable[Any]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "TongHop"

    headers = [
        "Mã HS", "Họ tên", "MSHV", "Email học viên",
        "Ngày nhận HS", "Ngày sinh", "Ngành", "Đợt",
        "Khóa", "Người nhận", "Ghi chú"
    ]
    ws.append(headers)

    for a in rows:
        get = a.get if isinstance(a, dict) else lambda k, d=None: getattr(a, k, d)
        ws.append([
            get("ma_ho_so"),
            get("ho_ten"),
            get("ma_so_hv"),
            get("email_hoc_vien", ""),
            _parse_to_date(get("ngay_nhan_hs")),
            _parse_to_date(get("ngay_sinh")),
            get("nganh_nhap_hoc"),
            get("dot"),
            get("khoa"),
            get("nguoi_nhan_ky_ten"),
            get("ghi_chu"),
        ])

    for col in (5, 6):
        for cell in ws.iter_cols(min_col=col, max_col=col, min_row=2):
            for c in cell:
                if isinstance(c.value, (date, datetime)):
                    c.number_format = "dd/mm/yyyy"
                    c.alignment = Alignment(horizontal="center")

    _autosize(ws)
    out = BytesIO()
    wb.save(out)
    out.seek(0)
    return out.getvalue()
