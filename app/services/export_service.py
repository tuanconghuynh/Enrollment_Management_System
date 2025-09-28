
# ================================
# app/services/export_service.py (updated, no pandas)
# ================================
from typing import List
from io import BytesIO
from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from ..models import Applicant, ApplicantDoc, ChecklistItem

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
