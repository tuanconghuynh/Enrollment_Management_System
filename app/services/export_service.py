
# ================================
# app/services/export_service.py (updated, no pandas)
# ================================
from typing import List
from io import BytesIO
from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from ..models import Applicant, ApplicantDoc, ChecklistItem
from datetime import date, datetime
from openpyxl.styles import Alignment

DOC_PREFIX = "doc_"  # column prefix for document quantities


def build_excel_bytes(apps: List[Applicant], docs: List[ApplicantDoc], items: List[ChecklistItem]) -> bytes:
    # Map docs by applicant_id -> {code: qty}
    by_app = {}
    for d in docs:
        by_app.setdefault(d.applicant_id, {})[d.code] = d.so_luong

    # Define columns
    base_cols = [
        "Ngày nhận HS","Niên Khóa","Mã hồ sơ", "Mã số HV", "Họ tên", "Ngày sinh", "Số ĐT",
        "Ngành nhập học", "Đợt", "Đối tượng", "Ghi chú", "Printed"
    ]
    doc_columns = [f"{DOC_PREFIX}{it.code}" for it in items] if items else []
    headers = base_cols + doc_columns

    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Data_Tongngay"

    # Write header
    ws.append(headers)

    # Write rows
    for a in apps:
        row = [
            a.ngay_nhan_hs.isoformat() if a.ngay_nhan_hs else "",
            a.khoa or "",
            a.ma_ho_so,
            a.ma_so_hv,
            a.ho_ten,
            a.ngay_sinh or "",
            a.so_dt or "",
            a.nganh_nhap_hoc or "",
            a.dot or "",
            a.da_tn_truoc_do or "",
            a.ghi_chu or "",
            a.printed,
        ]
        doc_map = by_app.get(a.id, {})
        for col in doc_columns:
            code = col[len(DOC_PREFIX):]
            qty = int(by_app.get(a.id, {}).get(code, 0) or 0)
            row.append("" if qty == 0 else qty)
        ws.append(row)

    # Optional: set column widths a bit wider
    for i, header in enumerate(headers, start=1):
        ws.column_dimensions[get_column_letter(i)].width = max(12, len(header) + 2)

    # Save to bytes
    output = BytesIO()
    wb.save(output)
    return output.getvalue()

def _to_date(v):
    if v is None or v == "": return None
    if isinstance(v, (date, datetime)): return v.date() if isinstance(v, datetime) else v
    s = str(v)
    # yyyy-mm-dd...
    try:
        return date.fromisoformat(s[:10])
    except Exception:
        # dd/mm/yyyy
        try:
            d, m, y = s.split("/")[:3]
            return date(int(y), int(m), int(d))
        except Exception:
            return None

def build_excel_bytes(rows):
    """
    rows: list[Applicant-like] hoặc dict có keys: ngay_nhan_hs, ngay_sinh, ...
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "TongHop"

    headers = ["Mã HS","Họ tên","MSHV","Ngày nhận HS","Ngày sinh","Ngành","Đợt","Khóa","Người nhận","Ghi chú"]
    ws.append(headers)

    for a in rows:
        ws.append([
            a.ma_ho_so, a.ho_ten, a.ma_so_hv,
            _to_date(getattr(a, "ngay_nhan_hs", None)),
            _to_date(getattr(a, "ngay_sinh", None)),
            getattr(a,"nganh_nhap_hoc",None),
            getattr(a,"dot",None),
            getattr(a,"khoa",None),
            getattr(a,"nguoi_nhan_ky_ten",None),
            getattr(a,"ghi_chu",None),
        ])

    # set format dd/mm/yyyy cho 2 cột ngày: "Ngày nhận HS"(4) & "Ngày sinh"(5)
    for row in ws.iter_rows(min_row=2, min_col=4, max_col=5):
        for cell in row:
            if cell.value:
                cell.number_format = "dd/mm/yyyy"
                cell.alignment = Alignment(horizontal="center")

    # autosize đơn giản
    for col in ws.columns:
        w = max(10, *(len(str(c.value)) if c.value is not None else 0 for c in col)) + 2
        ws.column_dimensions[col[0].column_letter].width = min(w, 40)

    from io import BytesIO
    out = BytesIO()
    wb.save(out); out.seek(0)
    return out.getvalue()