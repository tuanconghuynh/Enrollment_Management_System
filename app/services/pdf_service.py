# app/services/pdf_service.py
from __future__ import annotations

import io
import os
import re
from datetime import datetime, date
from typing import List, Optional, Dict, Tuple

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from app.models.applicant import Applicant, ApplicantDoc
from app.models.checklist import ChecklistItem

DOC_DISPLAY_NAME = {
    "so_yeu_ly_lich": "Sơ yếu lý lịch",
    "bang_tot_nghiep_thpt": "Bằng tốt nghiệp THPT (hoặc tương đương)",
    "hoc_ba_thpt": "Học bạ THPT (hoặc Bảng điểm THPT)",

    "bang_tot_nghiep_trung_cap": "Bằng tốt nghiệp Trung cấp",
    "bang_diem_trung_cap": "Bảng điểm Trung cấp",

    "bang_tot_nghiep_cao_dang": "Bằng tốt nghiệp Cao đẳng",
    "bang_diem_cao_dang": "Bảng điểm Cao đẳng",

    "bang_tot_nghiep_dai_hoc": "Bằng tốt nghiệp Đại học",
    "bang_diem_dai_hoc": "Bảng điểm Đại học",

    "can_cuoc_cong_dan": "Căn cước công dân",
    "giay_kham_suc_khoe": "Giấy khám sức khỏe",
    "anh_3x4": "Ảnh 3x4",

    "don_mien_giam": "Đơn xin miễn giảm học phần",
}
# ==============================
# Layout constants (A4 Portrait)
# ==============================
# Anh muốn sát mép trên hơn + cân lề trái/phải:
LM = 12 * mm     # giảm thụt trái
RM = 12 * mm     # cân lại lề phải
TM = 3 * mm      # sát mép trên hơn
BM = 12 * mm

FONT_SIZE = 12

# ==============================
# Font setup (Vietnamese support)
# ==============================
_FONT_REG = False
FONT_NAME = "TimesVN"
FONT_BOLD = "TimesVN-Bold"
FONT_ITALIC = "TimesVN-Italic"

def _try_register_font(font_name: str, path: str) -> bool:
    try:
        if path and os.path.exists(path):
            pdfmetrics.registerFont(TTFont(font_name, path))
            return True
    except Exception:
        return False
    return False


def _ensure_fonts():
    global _FONT_REG
    if _FONT_REG:
        return

    win = os.environ.get("WINDIR", r"C:\Windows")
    tnr = os.path.join(win, "Fonts", "times.ttf")
    tnr_b = os.path.join(win, "Fonts", "timesbd.ttf")
    tnr_i = os.path.join(win, "Fonts", "timesi.ttf")

    ok = (
        _try_register_font(FONT_NAME, tnr)
        and _try_register_font(FONT_BOLD, tnr_b)
        and _try_register_font(FONT_ITALIC, tnr_i)
    )

    if not ok:
        # Linux fallback
        _try_register_font(FONT_NAME, "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf")
        _try_register_font(FONT_BOLD, "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf")
        _try_register_font(FONT_ITALIC, "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf")

    _FONT_REG = True


# ==============================
# Text helpers
# ==============================
def _fmt_dmy(v) -> str:
    if not v:
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
            pass
    return s


def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def _get_full_name(app: Applicant) -> str:
    hd = (getattr(app, "ho_dem", None) or "").strip()
    ten = (getattr(app, "ten", None) or "").strip()
    if hd or ten:
        return f"{hd} {ten}".strip()
    return (getattr(app, "ho_ten", None) or getattr(app, "full_name", None) or "").strip()

def _get_ghi_chu(app: Applicant) -> str:
    return (getattr(app, "ghi_chu", None) or getattr(app, "note", None) or "").strip()

def _item_label(it: ChecklistItem) -> str:
    for k in ("label", "ten", "name", "noi_dung", "ten_tai_lieu", "mo_ta", "title"):
        v = getattr(it, k, None)
        if v:
            return str(v).strip()
    return ""


# ==============================
# Miễn giảm rules (theo yêu cầu anh)
# ==============================
MIEN_LABEL_KEYS = [
    "đơn miễn giảm",
    "bang diem trung cap",
    "bảng điểm trung cấp",
    "bang diem cao dang",
    "bảng điểm cao đẳng",
    "bang diem dai hoc",
    "bảng điểm đại học",
    "bang tot nghiep trung cap",
    "bằng tốt nghiệp trung cấp",
    "bang tot nghiep cao dang",
    "bằng tốt nghiệp cao đẳng",
    "bang tot nghiep dai hoc",
    "bằng tốt nghiệp đại học",
    "bằng trung cấp",
    "bằng cao đẳng",
    "bằng đại học",
]

MIEN_GIAM_CODES = {
    "don_mien_giam",
}

MIEN_GIAM_CODES = {"don_mien_giam"}

MIEN_MON_EXTRA_CODES = {
    # Bằng
    "bang_tot_nghiep_trung_cap",
    "bang_tot_nghiep_cao_dang",
    "bang_tot_nghiep_dai_hoc",
    # Bảng điểm
    "bang_diem_trung_cap",
    "bang_diem_cao_dang",
    "bang_diem_dai_hoc",
}

def _is_mien_by_label(label: str) -> bool:
    t = _norm(label)
    # match mềm: chỉ cần chứa cụm chính
    return any(k in t for k in MIEN_LABEL_KEYS)

def _build_code_to_label(items: List[ChecklistItem], docs: List[ApplicantDoc] | None = None) -> Dict[str, str]:
    out: Dict[str, str] = {}

    # 1. Ưu tiên map cứng (chuẩn in ấn)
    for code, name in DOC_DISPLAY_NAME.items():
        out[code] = name

    # 2. ChecklistItem (nếu sau này DB có tên)
    for it in (items or []):
        code = (getattr(it, "code", None) or "").strip()
        if not code:
            continue
        label = _item_label(it)
        if label:
            out[code] = label

    # 3. ApplicantDoc (fallback cuối)
    for d in (docs or []):
        code = (getattr(d, "code", None) or "").strip()
        if not code:
            continue
        for k in ("ten_tai_lieu", "ten", "label", "name"):
            v = getattr(d, k, None)
            if v:
                out.setdefault(code, str(v).strip())
                break

    return out

def _is_doc_mien_giam(d: ApplicantDoc) -> bool:
    """
    Ưu tiên lấy theo flag/nhóm đã có trong DB (đúng logic export.py).
    Fallback: nếu không có field thì chỉ coi don_mien_giam là miễn giảm.
    """
    # Các tên field hay gặp
    for k in ("is_mien_giam", "mien_giam", "ho_so_mien_giam", "is_exempt", "exempt"):
        v = getattr(d, k, None)
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, str)) and str(v).strip() in ("1", "true", "True", "YES", "yes"):
            return True

    # Một số hệ thống lưu dạng group/nhom
    for k in ("group", "nhom", "category", "loai_ho_so", "sheet"):
        v = (getattr(d, k, None) or "").strip().lower()
        if v in ("mien_giam", "miễn giảm", "miengiam", "exempt", "free", "hoso_mien_giam"):
            return True

    # Fallback cuối: chỉ riêng đơn miễn giảm
    code = (getattr(d, "code", None) or "").strip()
    return code in MIEN_GIAM_CODES

def _docs_map_by_type(
    docs: List[ApplicantDoc],
    code_to_label: Dict[str, str],
) -> Tuple[Dict[str, int], Dict[str, int]]:
    """
    normal_map: hồ sơ nhập học
    mien_map:   hồ sơ xét miễn môn

    Rule theo anh:
    - don_mien_giam: chỉ ở mien_map (không nằm normal_map)
    - Bằng + bảng điểm TC/CD/ĐH:
        + normal_map = 1 (nếu qty>0)
        + mien_map   = qty - 1 (nếu >0)
    - Các hồ sơ khác: normal_map = qty, mien_map = 0
    """
    normal: Dict[str, int] = {}
    mien: Dict[str, int] = {}

    for d in (docs or []):
        code = (getattr(d, "code", None) or "").strip()
        if not code:
            continue

        qty = int(getattr(d, "so_luong", 0) or 0)
        if qty <= 0:
            continue

        label = code_to_label.get(code, code)

        # 1) Đơn miễn giảm: chỉ hiện ở hồ sơ xét miễn môn
        if code in MIEN_GIAM_CODES or _is_mien_by_label(label) and code == "don_mien_giam":
            mien[code] = qty
            continue

        # 2) Nhóm bằng/bảng điểm: chia 1 vào nhập học, còn lại vào miễn môn
        if code in MIEN_MON_EXTRA_CODES or _is_mien_by_label(label):
            # nhập học luôn lấy 1 (nếu có)
            normal[code] = 1
            # phần còn lại qua miễn môn
            remain = qty - 1
            if remain > 0:
                mien[code] = remain
            continue

        # 3) Còn lại: để hết ở hồ sơ nhập học
        normal[code] = qty

    return normal, mien

def _build_rows_by_items(items: List[ChecklistItem], doc_map: Dict[str, int]) -> List[Tuple[int, int, str]]:
    """
    Dùng ChecklistItem để giữ thứ tự + lấy tên.
    Chỉ đưa vào những code có qty > 0 trong doc_map.
    """
    code_to_label = _build_code_to_label(items)
    ordered_codes: List[str] = []
    for it in (items or []):
        code = (getattr(it, "code", None) or "").strip()
        if code:
            ordered_codes.append(code)

    rows: List[Tuple[int, int, str]] = []

    for code in ordered_codes:
        if code in doc_map:
            rows.append((0, doc_map[code], code_to_label.get(code, code)))

    # extra codes (nếu có)
    extras = [c for c in doc_map.keys() if c not in set(ordered_codes)]
    for code in extras:
        rows.append((0, doc_map[code], code))

    # đánh STT
    rows = [(i + 1, qty, label) for i, (_, qty, label) in enumerate(rows)]
    return rows

# ==============================
# Drawing helpers
# ==============================
def _hline(c: canvas.Canvas, x1, x2, y, w=0.7):
    c.setLineWidth(w)
    c.line(x1, y, x2, y)

def _draw_header(c: canvas.Canvas, page_w: float, page_h: float, *, title: str, received_date: str, subline: str):
    y_top = page_h - TM

    c.setFont(FONT_BOLD, FONT_SIZE)
    c.drawCentredString(page_w / 2, y_top - 4 * mm, title)

    c.setFont(FONT_BOLD, FONT_SIZE)
    c.drawRightString(page_w - RM, y_top - 9 * mm, f"Ngày nhận HS   {received_date}")

    c.setFont(FONT_ITALIC, FONT_SIZE)
    c.drawString(LM, y_top - 14 * mm, subline)

    return y_top - 19 * mm

def _draw_info_block(c: canvas.Canvas, page_w: float, y: float, *, app: Applicant) -> float:
    full_name = _get_full_name(app)
    ma_sv = (getattr(app, "ma_so_hv", None) or "").strip()
    sdt = (getattr(app, "so_dt", None) or getattr(app, "so_dien_thoai", None) or "").strip()
    email = (getattr(app, "email_hoc_vien", None) or getattr(app, "email", None) or "").strip()
    ngay_sinh = _fmt_dmy(getattr(app, "ngay_sinh", None))
    gioi_tinh = (getattr(app, "gioi_tinh", None) or "").strip()
    nganh = (getattr(app, "nganh_nhap_hoc", None) or getattr(app, "nganh", None) or "").strip()
    dot = (getattr(app, "dot", None) or "").strip()

    lh = 6.2 * mm
    xL = LM
    xR = page_w / 2 + 6 * mm

    c.setFont(FONT_BOLD, FONT_SIZE); c.drawString(xL, y, "Họ tên:")
    c.setFont(FONT_NAME, FONT_SIZE); c.drawString(xL + 22 * mm, y, full_name)

    c.setFont(FONT_BOLD, FONT_SIZE); c.drawString(xL, y - lh, "Mã số SV:")
    c.setFont(FONT_NAME, FONT_SIZE); c.drawString(xL + 22 * mm, y - lh, ma_sv)

    c.setFont(FONT_BOLD, FONT_SIZE); c.drawString(xL, y - 2 * lh, "Ngành nhập học:")
    c.setFont(FONT_NAME, FONT_SIZE); c.drawString(xL + 34 * mm, y - 2 * lh, nganh)

    c.setFont(FONT_BOLD, FONT_SIZE); c.drawString(xR, y, "Ngày sinh:")
    c.setFont(FONT_NAME, FONT_SIZE); c.drawString(xR + 24 * mm, y, ngay_sinh)

    c.setFont(FONT_BOLD, FONT_SIZE); c.drawString(xR, y - lh, "Số ĐT:")
    c.setFont(FONT_NAME, FONT_SIZE); c.drawString(xR + 16 * mm, y - lh, sdt)

    c.setFont(FONT_BOLD, FONT_SIZE); c.drawString(xR, y - 2 * lh, "Email:")
    c.setFont(FONT_NAME, FONT_SIZE); c.drawString(xR + 16 * mm, y - 2 * lh, email)

    # --- cột nhỏ bên phải ---
    x_label_r = page_w - RM - 22 * mm   # vị trí chữ "Giới tính:", "ĐỢT:"
    x_value_r = page_w - RM             # giá trị căn phải sát lề phải

    c.setFont(FONT_BOLD, FONT_SIZE); c.drawRightString(x_label_r, y, "Giới tính:")
    c.setFont(FONT_NAME, FONT_SIZE); c.drawRightString(x_value_r, y, gioi_tinh)

    c.setFont(FONT_BOLD, FONT_SIZE); c.drawRightString(x_label_r, y - lh, "ĐỢT:")
    c.setFont(FONT_NAME, FONT_SIZE); c.drawRightString(x_value_r, y - lh, dot)

    return y - 3.2 * lh

def _draw_list_rows(c: canvas.Canvas, page_w: float, y: float, rows: List[Tuple[int, int, str]]) -> float:
    if not rows:
        rows = [(1, 1, "")]

    x_stt   = LM
    x_qty   = LM + 12 * mm
    x_label = LM + 24 * mm

    row_h = 6.5 * mm

    box_w = 8 * mm
    box_h = 5.5 * mm
    box_x = x_qty - 1.5 * mm
    box_y_offset = 1.2 * mm

    for stt, qty, label in rows:
        # STT
        c.setFont(FONT_NAME, FONT_SIZE)
        c.drawString(x_stt, y, f"{stt}")

        # qty: vẽ ô vuông + số đậm căn giữa
        c.rect(box_x, y - box_y_offset, box_w, box_h, stroke=1, fill=0)
        c.setFont(FONT_BOLD, FONT_SIZE)
        c.drawCentredString(box_x + box_w/2, y, f"{qty}")

        # label
        c.setFont(FONT_NAME, FONT_SIZE)
        c.drawString(x_label, y, label)

        y -= row_h
        if y < BM + 30 * mm:
            break

    return y - 2 * mm

def _draw_signatures(c: canvas.Canvas, page_w: float, y: float, *, nguoi_nop: str, nguoi_nhan: str) -> float:
    # 2 cột ký tên
    col_gap = 50 * mm
    col_w = (page_w - LM - RM - col_gap) / 2
    x_left = LM
    x_right = LM + col_w + col_gap

    c.setFont(FONT_BOLD, FONT_SIZE)
    c.drawCentredString(x_left + col_w / 2, y, "Người nộp")
    c.drawCentredString(x_right + col_w / 2, y, "Người nhận:")

    c.setFont(FONT_BOLD, FONT_SIZE)
    c.drawCentredString(x_left + col_w / 2, y - 14 * mm, nguoi_nop or "")
    c.drawCentredString(x_right + col_w / 2, y - 14 * mm, nguoi_nhan or "")

    y2 = y - 22 * mm
    _hline(c, LM, page_w - RM, y2, w=0.7)
    return y2 - 3 * mm

def _cut_line(c: canvas.Canvas, x1, x2, y, w=0.7):
    c.setLineWidth(w)
    c.setDash(2, 2)      # nét đứt
    c.line(x1, y, x2, y)
    c.setDash()          # reset về nét liền

def _draw_note(c: canvas.Canvas, y: float, note: str) -> float:
    """
    Luôn hiển thị chữ 'GHI CHÚ:'.
    Nếu note rỗng thì để trống sau dấu ':'.
    """
    note = (note or "").strip()
    c.setFont(FONT_BOLD, FONT_SIZE)
    c.drawString(LM, y, "GHI CHÚ:")
    c.setFont(FONT_NAME, FONT_SIZE)
    c.drawString(LM + 22 * mm, y, note)  # có thì điền, không có thì trống
    return y - 7 * mm

def _draw_mien_mon_block(
    c: canvas.Canvas,
    page_w: float,
    page_h: float,
    *,
    app: Applicant,
    rows_normal: List[Tuple[int, int, str]],
    rows_mien: List[Tuple[int, int, str]],
):
    """
    Block nửa dưới để cắt đưa học viên: gồm 2 phần
    (1) Biên nhận hồ sơ nhập học
    (2) Hồ sơ xét miễn môn
    """
    # Vị trí bắt đầu nửa dưới (anh chỉnh lên/xuống ở đây)
    y = (page_h / 2) - 10 * mm # vị trí bắt đầu nửa dưới

    # đường cắt (nét đứt)
    _cut_line(c, LM, page_w - RM, y + 10 * mm, w=0.7)

    # ===== (1) BIÊN NHẬN HỒ SƠ NHẬP HỌC =====
    title = "BIÊN NHẬN HỒ SƠ NHẬP HỌC CHƯƠNG TRÌNH ĐÀO TẠO TỪ XA KHÓA 25"
    received_date = _fmt_dmy(getattr(app, "ngay_nhan_hs", None)) or _fmt_dmy(getattr(app, "created_at", None))
    subline = "Viện Hợp tác và Phát triển Đào tạo HUTECH xác nhận đã nhận hồ sơ nhập học khóa 2025 của Anh/Chị:"

    # Header rút gọn cho block dưới (không dùng _draw_header để khỏi “đè” theo TM)
    c.setFont(FONT_BOLD, FONT_SIZE)
    c.drawCentredString(page_w / 2, y, title)
    c.setFont(FONT_BOLD, FONT_SIZE)
    c.drawRightString(page_w - RM, y - 5 * mm, f"Ngày nhận HS   {received_date}")
    c.setFont(FONT_ITALIC, FONT_SIZE)
    c.drawString(LM, y - 10 * mm, subline)

    y2 = y - 16 * mm
    y2 = _draw_info_block(c, page_w, y2, app=app)

    c.setFont(FONT_BOLD, FONT_SIZE)
    c.drawString(LM, y2, "Hồ sơ gồm có :")
    y2 -= 7 * mm
    y2 = _draw_list_rows(c, page_w, y2, rows_normal)

    ghi_chu = _get_ghi_chu(app)
    y2 = _draw_note(c, y2, ghi_chu)

    # đường phân cách giữa 2 nội dung (giống mẫu scan)
    _hline(c, LM, page_w - RM, y2 - 2 * mm, w=0.7)
    y2 -= 10 * mm

    # ===== (2) HỒ SƠ XÉT MIỄN MÔN =====
    c.setFont(FONT_BOLD, FONT_SIZE)
    c.drawCentredString(page_w / 2, y2 + 4 * mm, "HỒ SƠ XÉT MIỄN MÔN")

    c.setFont(FONT_ITALIC, FONT_SIZE)
    c.drawString(LM, y2 - 2 * mm, subline)

    y3 = y2 - 10 * mm
    y3 = _draw_info_block(c, page_w, y3, app=app)

    c.setFont(FONT_BOLD, FONT_SIZE)
    c.drawString(LM, y3, "Hồ sơ gồm có :")
    y3 -= 7 * mm
    y3 = _draw_list_rows(c, page_w, y3, rows_mien)

    ghi_chu = _get_ghi_chu(app)
    y3 = _draw_note(c, y3, ghi_chu)

    # ký tên
    nguoi_nop = _get_full_name(app)
    nguoi_nhan = (getattr(app, "nguoi_nhan", None) or getattr(app, "nguoi_nhan_ky_ten", None) or "").strip()
    _draw_signatures(c, page_w, y3, nguoi_nop=nguoi_nop, nguoi_nhan=nguoi_nhan)

# ==============================
# Public API
# ==============================
def render_single_pdf(app: Applicant, items: List[ChecklistItem], docs: List[ApplicantDoc]) -> bytes:
    """
    A4 portrait - list style, no table borders.
    Docs chia: nhập học vs miễn giảm theo 3 danh mục anh chốt.
    """
    _ensure_fonts()

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    page_w, page_h = A4

    title = "BIÊN NHẬN HỒ SƠ NHẬP HỌC CHƯƠNG TRÌNH ĐÀO TẠO TỪ XA KHÓA 25"
    received_date = _fmt_dmy(getattr(app, "ngay_nhan_hs", None)) or _fmt_dmy(getattr(app, "created_at", None))
    subline = "Viện Hợp tác và Phát triển Đào tạo HUTECH xác nhận đã nhận hồ sơ nhập học khóa 2025 của Anh/Chị:"

    y = _draw_header(c, page_w, page_h, title=title, received_date=received_date, subline=subline)

    # Info
    y = _draw_info_block(c, page_w, y, app=app)

    code_to_label = _build_code_to_label(items, docs)
    normal_map, mien_map = _docs_map_by_type(docs, code_to_label)

    rows_normal = _build_rows_by_items(items, normal_map)
    rows_mien = _build_rows_by_items(items, mien_map)

    # Hồ sơ gồm có
    c.setFont(FONT_BOLD, FONT_SIZE)
    c.drawString(LM, y, "Hồ sơ gồm có :")
    y -= 7 * mm
    y = _draw_list_rows(c, page_w, y, rows_normal)

    # Ghi chú (nếu có)
    ghi_chu = _get_ghi_chu(app)
    y = _draw_note(c, y, ghi_chu)

    # Hồ sơ xét miễn môn
    c.setFont(FONT_BOLD, FONT_SIZE)
    c.drawCentredString(page_w / 2, y, "HỒ SƠ XÉT MIỄN MÔN")
    y -= 9 * mm
    y = _draw_list_rows(c, page_w, y, rows_mien)

    ghi_chu = _get_ghi_chu(app)
    y = _draw_note(c, y, ghi_chu)

    # ký tên
    nguoi_nop = _get_full_name(app)
    nguoi_nhan = (getattr(app, "nguoi_nhan", None) or getattr(app, "nguoi_nhan_ky_ten", None) or "").strip()
    _draw_signatures(c, page_w, y, nguoi_nop=nguoi_nop, nguoi_nhan=nguoi_nhan)

    _draw_mien_mon_block(
        c, page_w, page_h,
        app=app,
        rows_normal=rows_normal,
        rows_mien=rows_mien
    )
    c.showPage()
    c.save()
    return buf.getvalue()


def render_single_pdf_a5(app: Applicant, items: List[ChecklistItem], docs: List[ApplicantDoc]) -> bytes:
    """
    Deprecated: anh bỏ A5.
    Giữ hàm để không lỗi route cũ, nhưng trả A4.
    """
    return render_single_pdf(app, items, docs)


def render_batch_pdf(apps: List[Applicant], items_all: List[ChecklistItem], docs_all: List[ApplicantDoc]) -> bytes:
    """
    Batch: mỗi hồ sơ 1 trang A4.
    """
    _ensure_fonts()

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    page_w, page_h = A4

    # group docs by MSSV
    docs_by_mssv: Dict[str, List[ApplicantDoc]] = {}
    for d in (docs_all or []):
        mssv = getattr(d, "applicant_ma_so_hv", None)
        if not mssv:
            continue
        docs_by_mssv.setdefault(str(mssv), []).append(d)

    for app in (apps or []):
        title = "BIÊN NHẬN HỒ SƠ NHẬP HỌC CHƯƠNG TRÌNH ĐÀO TẠO TỪ XA KHÓA 25"
        received_date = _fmt_dmy(getattr(app, "ngay_nhan_hs", None)) or _fmt_dmy(getattr(app, "created_at", None))
        subline = "Viện Hợp tác và Phát triển Đào tạo HUTECH xác nhận đã nhận hồ sơ nhập học khóa 2025 của Anh/Chị:"

        y = _draw_header(c, page_w, page_h, title=title, received_date=received_date, subline=subline)
        y = _draw_info_block(c, page_w, y, app=app)

        docs = docs_by_mssv.get(str(getattr(app, "ma_so_hv", "")).strip(), [])
        code_to_label = _build_code_to_label(items_all, docs)

        normal_map, mien_map = _docs_map_by_type(docs, code_to_label)

        rows_normal = _build_rows_by_items(items_all, normal_map)
        rows_mien   = _build_rows_by_items(items_all, mien_map)

        ghi_chu = _get_ghi_chu(app)
        y = _draw_note(c, y, ghi_chu)

        # Hồ sơ gồm có

        c.setFont(FONT_BOLD, FONT_SIZE)
        c.drawString(LM, y, "Hồ sơ gồm có :")
        y -= 7 * mm
        y = _draw_list_rows(c, page_w, y, rows_normal)

        # Hồ sơ xét miễn môn
        c.setFont(FONT_BOLD, FONT_SIZE)
        c.drawCentredString(page_w / 2, y, "HỒ SƠ XÉT MIỄN MÔN")
        y -= 9 * mm
        y = _draw_list_rows(c, page_w, y, rows_mien)

        ghi_chu = _get_ghi_chu(app)
        y = _draw_note(c, y, ghi_chu)

        nguoi_nop = _get_full_name(app)
        nguoi_nhan = (getattr(app, "nguoi_nhan", None) or getattr(app, "nguoi_nhan_ky_ten", None) or "").strip()
        _draw_signatures(c, page_w, y, nguoi_nop=nguoi_nop, nguoi_nhan=nguoi_nhan)

        _draw_mien_mon_block(
            c, page_w, page_h,
            app=app,
            rows_normal=rows_normal,
            rows_mien=rows_mien
        )
        c.showPage()

    c.save()
    return buf.getvalue()

