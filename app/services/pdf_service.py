# app/services/pdf_service.py
from __future__ import annotations

import io
import os
import re
from datetime import datetime, date
from typing import List, Optional, Dict, Tuple

from PyPDF2 import PdfMerger

from reportlab.lib.pagesizes import A4
from reportlab.lib.pagesizes import A5, landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from app.models.applicant import Applicant, ApplicantDoc
from app.models.checklist import ChecklistItem


def merge_pdfs(pdf_list: list[bytes]) -> bytes:
    merger = PdfMerger()
    for pdf_bytes in pdf_list:
        merger.append(io.BytesIO(pdf_bytes))

    output = io.BytesIO()
    merger.write(output)
    merger.close()
    return output.getvalue()

def save_receipt_pdf_file(a, items, docs, out_dir: str, a5: bool = False) -> str:

    if a5:
        data = render_student_receipt_pdf_a5(a, docs)
        fname = f"{a.ma_so_hv}_bien_nhan_A5.pdf"
    else:
        data = render_single_pdf(a, items, docs)
        fname = f"{a.ma_so_hv}_bien_nhan_A4.pdf"

    full = os.path.join(out_dir, fname)
    with open(full, "wb") as f:
        f.write(data)
    return full

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

FONT_SIZE = 10

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
def _get_khoa(app: Applicant) -> str:
    return (getattr(app, "khoa", None) or "").strip()

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

def _items_for_app(app: Applicant, items_all):
    """
    Trả về list ChecklistItem tương ứng với 1 hồ sơ.
    - Nếu items_all là dict {version_id: [ChecklistItem]} -> lấy theo checklist_version_id
    - Nếu là list -> dùng chung cho tất cả (giữ tương thích cũ)
    """
    if isinstance(items_all, dict):
        vid = getattr(app, "checklist_version_id", None)
        return items_all.get(vid, []) or []
    # backward-compatible: cũ truyền nguyên list
    return items_all or []


def _docs_for_app(app: Applicant, docs_all):
    """
    Trả về list ApplicantDoc tương ứng với 1 hồ sơ.
    - Nếu docs_all là dict {ma_so_hv: [ApplicantDoc]} -> lấy theo MSHV
    - Nếu là list -> lọc theo applicant_ma_so_hv (giữ tương thích cũ)
    """
    mssv = str(getattr(app, "ma_so_hv", "") or "").strip()
    if not mssv:
        return []

    # Trường hợp router mới: dict theo MSHV
    if isinstance(docs_all, dict):
        return docs_all.get(mssv, []) or []

    # Trường hợp cũ: list => lọc
    out = []
    for d in (docs_all or []):
        key = str(getattr(d, "applicant_ma_so_hv", "") or "").strip()
        if key == mssv:
            out.append(d)
    return out

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
    c.drawRightString(page_w - RM, y_top - 9 * mm, f"Ngày nhận HS: {received_date}")

    c.setFont(FONT_BOLD, FONT_SIZE)
    c.drawCentredString(page_w / 2, y_top - 14 * mm, subline)

    return y_top - 19 * mm

def _draw_info_block(c: canvas.Canvas, page_w: float, y: float, *, app: Applicant) -> float:
    full_name = _get_full_name(app)
    sdt = (getattr(app, "so_dt", None) or getattr(app, "so_dien_thoai", None) or "").strip()
    ma_sv = (getattr(app, "ma_so_hv", None) or "").strip()
    email = (getattr(app, "email_hoc_vien", None) or getattr(app, "email", None) or "").strip()
    ngay_sinh = _fmt_dmy(getattr(app, "ngay_sinh", None))
    nganh = (getattr(app, "nganh_nhap_hoc", None) or getattr(app, "nganh", None) or "").strip()
    dot = (getattr(app, "dot", None) or "").strip()
    da_tn = (getattr(app, "da_tn_truoc_do", None) or "").strip()

    lh = 4.3 * mm
    x_left = LM
    x_mid  = page_w/2

    # Hàng 1
    c.setFont(FONT_BOLD, FONT_SIZE)
    c.drawString(x_left, y, "Họ và tên:")
    c.setFont(FONT_NAME, FONT_SIZE)
    c.drawString(x_left+20*mm, y, full_name)

    c.setFont(FONT_BOLD, FONT_SIZE)
    c.drawString(x_mid, y, "Ngày sinh:")
    c.setFont(FONT_NAME, FONT_SIZE)
    c.drawString(x_mid+18*mm, y, ngay_sinh)

    c.setFont(FONT_BOLD, FONT_SIZE)
    c.drawRightString(page_w - RM - 24*mm, y, "SĐT:")
    c.setFont(FONT_NAME, FONT_SIZE)
    c.drawRightString(page_w - RM, y, sdt)

    y -= lh

    # Hàng 2
    c.setFont(FONT_BOLD, FONT_SIZE)
    c.drawString(x_left, y, "Mã số HV:")
    c.setFont(FONT_NAME, FONT_SIZE)
    c.drawString(x_left+20*mm, y, ma_sv)

    c.setFont(FONT_BOLD, FONT_SIZE)
    c.drawString(x_mid, y, "Email:")
    c.setFont(FONT_NAME, FONT_SIZE)
    c.drawString(x_mid+18*mm, y, email)

    y -= lh

    # Hàng 3
    c.setFont(FONT_BOLD, FONT_SIZE)
    c.drawString(x_left, y, "Ngành nhập học:")
    c.setFont(FONT_NAME, FONT_SIZE)
    c.drawString(x_left+30*mm, y, nganh)

    c.setFont(FONT_BOLD, FONT_SIZE)
    c.drawString(x_mid, y, "Đợt:")
    c.setFont(FONT_NAME, FONT_SIZE)
    c.drawString(x_mid+10*mm, y, dot)

    c.setFont(FONT_BOLD, FONT_SIZE)
    c.drawRightString(page_w - RM -24*mm, y, "Đã TN:")
    c.setFont(FONT_NAME, FONT_SIZE)
    c.drawRightString(page_w - RM, y, da_tn)

    return y - 5 * mm

def _draw_list_rows(c: canvas.Canvas, page_w: float, y: float, rows: List[Tuple[int, int, str]], *, limit: bool = False) -> float:
    if not rows:
        rows = [(1, 1, "")]

    y -= 0.5 * mm
    x_stt   = LM
    x_qty   = LM + 12 * mm
    x_label = LM + 24 * mm

    row_h = 4.8 * mm

    box_w = 6 * mm
    box_h = 4 * mm
    box_x = x_qty - 0.8 * mm
    box_y_offset = 0.6 * mm

    for stt, qty, label in rows:

        # nếu không bật limit → giữ cắt trang ở block trên
        if not limit and y < BM + 30 * mm:
            break

        c.setFont(FONT_NAME, FONT_SIZE)
        c.drawString(x_stt, y, f"{stt}")

        # qty
        c.rect(box_x, y - box_y_offset, box_w, box_h, stroke=1, fill=0)
        c.setFont(FONT_BOLD, FONT_SIZE)
        c.drawCentredString(box_x + box_w/2, y, f"{qty}")

        # label
        c.setFont(FONT_NAME, FONT_SIZE)
        c.drawString(x_label, y, label)

        y -= row_h

    return y - 2 * mm

def _draw_signatures(c: canvas.Canvas, page_w: float, y: float, *, nguoi_nop: str, nguoi_nhan: str) -> float:
    # 2 cột ký tên
    col_gap = 50 * mm
    col_w = (page_w - LM - RM - col_gap) / 2
    x_left = LM
    x_right = LM + col_w + col_gap

    c.setFont(FONT_BOLD, FONT_SIZE)
    c.drawCentredString(x_left + col_w / 2, y, "Người nộp")
    c.drawCentredString(x_right + col_w / 2, y, "Người nhận")

    c.setFont(FONT_BOLD, FONT_SIZE)
    c.drawCentredString(x_left + col_w / 2, y - 14 * mm, nguoi_nop or "")
    c.drawCentredString(x_right + col_w / 2, y - 14 * mm, nguoi_nhan or "")

    y2 = y - 22 * mm
    return y2

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
    return y - 4 * mm

def _draw_mien_mon_block(
    c: canvas.Canvas,
    page_w: float,
    page_h: float,
    start_y: float,
    *,
    app: Applicant,
    rows_normal: List[Tuple[int, int, str]],
    rows_mien: List[Tuple[int, int, str]],
):

    # ===== TỌA ĐỘ =====
    y = start_y - 13*mm

    # ========= ĐƯỜNG CẮT NÉT ĐỨT =========
    # vị trí đường cắt nét đứt
    x1 = LM + 10*mm
    x2 = page_w - RM - 10*mm

    # icon kéo ✂
    scissor = "✂"

    # vẽ icon kéo bên trái
    c.setFont(FONT_BOLD, FONT_SIZE + 2)      # tăng size cho dễ nhìn
    c.drawString(x1 - 6*mm, y - 1*mm, scissor)

    # vẽ icon kéo bên phải
    c.drawRightString(x2 + 6*mm, y - 1*mm, scissor)

    # vẽ đường nét đứt
    _cut_line(c, x1, x2, y)

    y -= 6*mm

    # ========= HEADER =========
    khoa = _get_khoa(app)
    title = f"BIÊN NHẬN HỒ SƠ NHẬP HỌC CHƯƠNG TRÌNH ĐÀO TẠO TỪ XA KHÓA 20{khoa}"
    received_date = _fmt_dmy(getattr(app, "ngay_nhan_hs", None)) or _fmt_dmy(getattr(app, "created_at", None))

    c.setFont(FONT_BOLD, FONT_SIZE)
    c.drawCentredString(page_w/2, y, title)

    c.setFont(FONT_BOLD, FONT_SIZE)
    c.drawRightString(page_w - RM, y - 5*mm, f"Ngày nhận HS: {received_date}")

    subline = (
        f"Viện Hợp tác và Phát triển Đào tạo HUTECH xác nhận đã nhận hồ sơ "
        f"nhập học khóa 20{khoa} của Anh/Chị:"
    )
    c.setFont(FONT_BOLD, FONT_SIZE)
    c.drawCentredString(page_w/2, y - 10*mm, subline)

    # ========= THÔNG TIN HỌC VIÊN =========
    y -= 18*mm
    y = _draw_info_block(c, page_w, y, app=app)

    # ========= HỒ SƠ NHẬP HỌC =========
    c.setFont(FONT_BOLD, FONT_SIZE)
    c.drawString(LM, y, "Hồ sơ gồm có :")

    y -= 3*mm
    y = _draw_list_rows(c, page_w, y, rows_normal)
    ghi_chu = _get_ghi_chu(app)
    y = _draw_note(c, y, ghi_chu)

    # ========= ĐƯỜNG KẺ TRÊN =========
    _hline(c, LM, page_w - RM, y + 2*mm, w=0.7)

    # ========= TIÊU ĐỀ MIỄN MÔN =========
    y -= 4*mm
    c.setFont(FONT_BOLD, FONT_SIZE)
    c.drawCentredString(page_w/2, y, "HỒ SƠ XÉT MIỄN MÔN")

    # ========= SUBLINE MIỄN MÔN =========
    # khoa = _get_khoa(app)
    # sub_free = f"Viện Hợp tác và Phát triển Đào tạo HUTECH xác nhận đã nhận hồ sơ miễn môn 20{khoa} của Anh/Chị:"
    # c.setFont(FONT_BOLD, FONT_SIZE)
    # c.drawCentredString(page_w/2, y - 6*mm, sub_free)

    # # hạ vị trí xuống trước list
    # y -= 3.5*mm

    # ========= THÔNG TIN HỌC VIÊN =========
    y -= 5*mm
    y = _draw_info_block(c, page_w, y, app=app)

    y -= 0.5*mm
    c.setFont(FONT_BOLD, FONT_SIZE)
    c.drawString(LM, y, "Hồ sơ gồm có :")
    y -= 3*mm
    y = _draw_list_rows(c, page_w, y, rows_mien, limit=True)

    ghi_chu = _get_ghi_chu(app)
    y = _draw_note(c, y, ghi_chu)
    # ký tên

    nguoi_nop  = _get_full_name(app)
    nguoi_nhan = (getattr(app, "nguoi_nhan_ky_ten", None) or "").strip()
    _draw_signatures(c, page_w, y, nguoi_nop=nguoi_nop, nguoi_nhan=nguoi_nhan)

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

    # Set PDF title
    full_name = _get_full_name(app)
    ma = getattr(app, "ma_so_hv", "") or ""
    safe = f"{ma}_{full_name}".replace(" ", "_")
    c.setTitle(safe)

    khoa = _get_khoa(app)
    title = f"BIÊN NHẬN HỒ SƠ NHẬP HỌC CHƯƠNG TRÌNH ĐÀO TẠO TỪ XA KHÓA 20{khoa}"

    received_date = _fmt_dmy(getattr(app, "ngay_nhan_hs", None)) or _fmt_dmy(getattr(app, "created_at", None))
    khoa = _get_khoa(app)
    subline = f"Viện Hợp tác và Phát triển Đào tạo HUTECH xác nhận đã nhận hồ sơ nhập học khóa 20{khoa} của Anh/Chị:"

    y = _draw_header(c, page_w, page_h, title=title, received_date=received_date, subline=subline)

    # Info
    y = _draw_info_block(c, page_w, y, app=app)

    code_to_label = _build_code_to_label(items, docs)
    normal_map, mien_map = _docs_map_by_type(docs, code_to_label)

    rows_normal = _build_rows_by_items(items, normal_map)
    rows_mien = _build_rows_by_items(items, mien_map)

    # Hồ sơ gồm có
    y -= 1 * mm
    c.setFont(FONT_BOLD, FONT_SIZE)
    c.drawString(LM, y, "Hồ sơ gồm có :")
    y -= 3.5 * mm
    y = _draw_list_rows(c, page_w, y, rows_normal)

    # Ghi chú (nếu có)
    ghi_chu = _get_ghi_chu(app)
    y = _draw_note(c, y, ghi_chu)

    # Hồ sơ xét miễn môn
    c.setFont(FONT_BOLD, FONT_SIZE)
    c.drawCentredString(page_w / 2, y, "HỒ SƠ XÉT MIỄN MÔN")
    y -= 3.5 * mm
    y = _draw_list_rows(c, page_w, y, rows_mien)

    ghi_chu = _get_ghi_chu(app)
    y = _draw_note(c, y, ghi_chu)

    # ký tên
    nguoi_nop = _get_full_name(app)
    nguoi_nhan = (getattr(app, "nguoi_nhan", None) or getattr(app, "nguoi_nhan_ky_ten", None) or "").strip()
    _draw_signatures(c, page_w, y, nguoi_nop=nguoi_nop, nguoi_nhan=nguoi_nhan)

    # đường cắt cách vùng ký trên ~5mm
    cut_y = y - 5 * mm

    _draw_mien_mon_block(
        c, page_w, page_h,
        start_y=cut_y,
        app=app,
        rows_normal=rows_normal,
        rows_mien=rows_mien,
    )

    c.showPage()
    c.save()
    return buf.getvalue()

def render_batch_pdf(
    apps: List[Applicant],
    items_all,
    docs_all,
    print_type: str = "A4"
) -> bytes:
    """
    In gộp:
    - A4: nhiều hồ sơ, mỗi hồ sơ 1 block (như hiện tại)
    - A5 / POSTAL: chỉ in được 1 hồ sơ/lần (dùng layout riêng)
      (các route đơn lẻ /print/a5/{mshv}, /postal-print vẫn hoạt động bình thường)
    """
    _ensure_fonts()
    print_type = (print_type or "A4").upper()

    # ===== A5: biên nhận A5=====
    if print_type == "A5":
        outputs = []
        for a in apps:
            docs = _docs_for_app(a, docs_all)
            pdf = render_student_receipt_pdf_a5(a, docs)
            outputs.append(pdf)

        return merge_pdfs(outputs)

    # ===== POSTAL: phiếu bưu điện (1 hồ sơ) =====
    if print_type == "POSTAL":
        outputs = []
        for a in apps:
            pdf = render_postal_pdf(a, items_all, docs_all)
            outputs.append(pdf)

        return merge_pdfs(outputs)

    # ===== Mặc định: batch A4 =====
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle("Danh_sach_bien_nhan")
    page_w, page_h = A4

    for app in (apps or []):
        # Lấy checklist & docs đúng cho từng hồ sơ
        items = _items_for_app(app, items_all)
        docs  = _docs_for_app(app, docs_all)

        khoa = _get_khoa(app)
        title = f"BIÊN NHẬN HỒ SƠ NHẬP HỌC CHƯƠNG TRÌNH ĐÀO TẠO TỪ XA KHÓA 20{khoa}"

        received_date = _fmt_dmy(getattr(app, "ngay_nhan_hs", None)) or _fmt_dmy(getattr(app, "created_at", None))
        subline = (
            f"Viện Hợp tác và Phát triển Đào tạo HUTECH xác nhận đã nhận hồ sơ "
            f"nhập học khóa 20{khoa} của Anh/Chị:"
        )

        y = _draw_header(c, page_w, page_h, title=title, received_date=received_date, subline=subline)
        y = _draw_info_block(c, page_w, y, app=app)

        # Map code -> label theo checklist + docs của riêng hồ sơ này
        code_to_label = _build_code_to_label(items, docs)
        normal_map, mien_map = _docs_map_by_type(docs, code_to_label)

        rows_normal = _build_rows_by_items(items, normal_map)
        rows_mien   = _build_rows_by_items(items, mien_map)

        # Hồ sơ gồm có
        y -= 1 * mm
        c.setFont(FONT_BOLD, FONT_SIZE)
        c.drawString(LM, y, "Hồ sơ gồm có :")
        y -= 7 * mm
        y = _draw_list_rows(c, page_w, y, rows_normal)

        # Hồ sơ xét miễn môn
        c.setFont(FONT_BOLD, FONT_SIZE)
        c.drawCentredString(page_w / 2, y, "HỒ SƠ XÉT MIỄN MÔN")
        y -= 9 * mm
        y = _draw_list_rows(c, page_w, y, rows_mien)

        # Ghi chú
        ghi_chu = _get_ghi_chu(app)
        y = _draw_note(c, y, ghi_chu)

        # Ký tên
        nguoi_nop = _get_full_name(app)
        nguoi_nhan = (getattr(app, "nguoi_nhan", None) or getattr(app, "nguoi_nhan_ky_ten", None) or "").strip()
        _draw_signatures(c, page_w, y, nguoi_nop=nguoi_nop, nguoi_nhan=nguoi_nhan)

        # Khối thứ 2 “Hồ sơ nhập học / hồ sơ xét miễn môn” sau đường cắt
        cut_y = y - 5 * mm
        _draw_mien_mon_block(
            c, page_w, page_h,
            start_y=cut_y,
            app=app,
            rows_normal=rows_normal,
            rows_mien=rows_mien,
        )

        c.showPage()

    c.save()
    return buf.getvalue()

# ==============================
# Postal PDF
fixed_labels = [
    "Sơ yếu lý lịch",
    "Bằng tốt nghiệp THPT (hoặc tương đương)",
    "Học bạ THPT (hoặc Bảng điểm THPT)",
    "Bằng tốt nghiệp Đại học",
    "Bảng điểm Đại học",
    "Bằng tốt nghiệp Cao đẳng",
    "Bảng điểm Cao đẳng",
    "Bằng tốt nghiệp Trung cấp",
    "Bằng điểm Trung cấp",
    "Căn cước công dân",
    "Đơn xin miễn giảm học phần",
]
def render_postal_pdf(app: Applicant, items: List[ChecklistItem], docs: List[ApplicantDoc]) -> bytes:
    _ensure_fonts()

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    page_w, page_h = A4
    
    # Set PDF title
    full_name = _get_full_name(app)
    ma = getattr(app, "ma_so_hv", "") or ""
    safe = f"{ma}_{full_name}_postal".replace(" ", "_")
    c.setTitle(safe)

    FS = 13
    LH = 6*mm

    # lề giấy
    LM = 18*mm
    RM = 18*mm
    TM = 18*mm

    # ----------------------- DATA -----------------------
    full_name  = _get_full_name(app)
    ngay_sinh  = _fmt_dmy(getattr(app, "ngay_sinh", None))
    gioi_tinh  = (getattr(app, "gioi_tinh", "") or "").strip()
    ma_hs      = getattr(app, "ma_ho_so", "") or ""
    ma_sv      = getattr(app, "ma_so_hv", "") or ""
    nganh      = (getattr(app, "nganh_nhap_hoc", "") or getattr(app, "nganh", "") or "").strip()
    email      = (getattr(app, "email_hoc_vien", "") or getattr(app, "email", "") or "").strip()
    sdt        = (getattr(app, "so_dt", "") or getattr(app, "so_dien_thoai", "") or "").strip()
    dot        = (getattr(app, "dot", "") or "").strip()
    ghi_chu    = _get_ghi_chu(app)
    khoa       = _get_khoa(app)
    ngay_nhan  = _fmt_dmy(getattr(app, "ngay_nhan_hs", None))
    nguoi_nhan = (getattr(app, "nguoi_nhan", "") or getattr(app, "nguoi_nhan_ky_ten", "") or "").strip()

    # hồ sơ
    code_to_label = _build_code_to_label(items, docs)
    # luôn đủ 11 hàng hồ sơ
    listed_docs = []

    for idx, name in enumerate(fixed_labels, start=1):

        qty = 0

        # kiểm tra trong docs xem có khớp tên không
        for d in docs:
            label = code_to_label.get((getattr(d, "code", "") or "").strip(), "")
            if label == name:
                qty = int(getattr(d, "so_luong", 0) or 0)
                break

        listed_docs.append((idx, name, qty))


    if not listed_docs:
        listed_docs = [(1, "Không có hồ sơ", 0)]

    # =====================================================
    # KHUNG THÔNG TIN GÓC PHẢI
    # =====================================================
    from reportlab.platypus import Paragraph
    from reportlab.lib.styles import ParagraphStyle

    # ====== KHUNG THÔNG TIN GÓC PHẢI =======
    box_w = 70*mm
    box_h = 35*mm

    box_x = page_w - RM - box_w + 10*mm      # giữ nguyên canh phải
    box_y = page_h - TM - box_h + 12*mm      # ↓ hạ xuống 6mm

    c.setLineWidth(1)
    c.roundRect(box_x, box_y, box_w, box_h, 5*mm)

    c.setFont(FONT_BOLD, FS)
    cx = box_x + box_w/2

    c.drawCentredString(cx, box_y + box_h - 9*mm,  f"MÃ HS : {ma_hs}")
    c.drawCentredString(cx, box_y + box_h - 18*mm, f"MSHV : {ma_sv}")

    # xử lý ngành dài
    style_center = ParagraphStyle(
        name="center_box",
        fontName=FONT_BOLD,
        fontSize=FS,
        leading=FS + 2,
        alignment=1
    )

    p = Paragraph(f"Ngành: {nganh}", style_center)
    pw, ph = p.wrap(box_w - 6*mm, box_h - 20*mm)

    p.drawOn(
        c,
        box_x + 6*mm,
        box_y + box_h - 23*mm - ph
    )

    # =====================================================
    # TIÊU ĐỀ
    # =====================================================
    title_y = page_h - TM - 28*mm     # GIÃN XUỐNG TRÁNH ĐÈ
    c.setFont(FONT_BOLD, FS+3)
    c.drawCentredString(page_w/2, title_y, "BIÊN NHẬN HỒ SƠ NHẬP HỌC")

    y = title_y - 8*mm
    c.setFont(FONT_BOLD, FS+2)
    c.drawCentredString(page_w/2, y, f"CHƯƠNG TRÌNH ĐÀO TẠO TỪ XA KHÓA 20{khoa}")

    # ngày nhận HS
    y -= 12*mm
    c.setFont(FONT_BOLD, FS)
    c.drawRightString(page_w - RM, y, f"Ngày nhận HS: {ngay_nhan}")

    # =====================================================
    # CÂU XÁC NHẬN
    # =====================================================

    y -= 12*mm
    c.setFont(FONT_NAME, FS)
    c.drawString(LM, y, f"Viện Hợp tác và Phát triển Đào tạo HUTECH xác nhận đã nhận hồ sơ nhập học khóa 20{khoa} của Anh/Chị:")

    # =====================================================
    # THÔNG TIN SINH VIÊN
    # =====================================================

    LH = 9*mm     # khoảng cách dòng

    # Hàng 1: Họ tên – Ngày sinh
    y -= LH
    c.setFont(FONT_BOLD, FS); c.drawString(LM, y, "Họ và tên:")
    c.setFont(FONT_NAME, FS); c.drawString(LM + 28*mm, y, full_name)

    c.setFont(FONT_BOLD, FS); c.drawString(page_w/2 + 10*mm, y, "Ngày sinh:")
    c.setFont(FONT_NAME, FS); c.drawString(page_w/2 + 38*mm, y, ngay_sinh)


    # Hàng 2: Mã HV – Đợt – Giới tính
    y -= LH
    c.setFont(FONT_BOLD, FS); c.drawString(LM, y, "Mã số HV:")
    c.setFont(FONT_NAME, FS); c.drawString(LM + 28*mm, y, ma_sv)

    c.setFont(FONT_BOLD, FS); c.drawString(page_w/2 + 10*mm, y, "Giới tính:")
    c.setFont(FONT_NAME, FS); c.drawString(page_w/2 + 32*mm, y, gioi_tinh)


    # Hàng 3: SĐT – Email
    y -= LH
    c.setFont(FONT_BOLD, FS); c.drawString(LM, y, "Số điện thoại:")
    c.setFont(FONT_NAME, FS); c.drawString(LM + 32*mm, y, sdt)

    c.setFont(FONT_BOLD, FS); c.drawString(page_w/2 + 10*mm, y, "Email:")
    c.setFont(FONT_NAME, FS); c.drawString(page_w/2 + 25*mm, y, email)


    # Hàng 4: Ngành nhập học
    y -= LH

    c.setFont(FONT_BOLD, FS); c.drawString(LM, y, "Ngành nhập học:")
    c.setFont(FONT_NAME, FS); c.drawString(LM + 35*mm, y, nganh)

    c.setFont(FONT_BOLD, FS); c.drawString(page_w/2 + 20*mm, y, "Đợt:")
    c.setFont(FONT_NAME, FS); c.drawString(page_w/2 + 35*mm, y, dot)

    c.setFont(FONT_BOLD, FS); c.drawString(page_w - RM - 40*mm, y, "Đã TN:")
    c.setFont(FONT_NAME, FS); c.drawString(page_w - RM - 12*mm, y, da_tn_truoc_do := (getattr(app, "da_tn_truoc_do", "") or "").strip())

    # =====================================================
    # TIÊU ĐỀ TRƯỚC BẢNG HỒ SƠ
    # =====================================================
    c.setFont(FONT_BOLD, FS)
    c.drawString(LM, y - 10*mm, "Hồ sơ gồm có:")
    y -= 1*mm

    # =====================================================
    # BẢNG HỒ SƠ – FULL WIDTH – 3 CỘT
    # =====================================================

    y -= 15*mm

    table_w = page_w - LM - RM
    row_h = 8*mm

    col1 = LM
    col2 = LM + 20*mm
    col3 = page_w - RM - 20*mm

    # header
    c.setFont(FONT_BOLD, FS)
    c.rect(LM, y - row_h, table_w, row_h)
    c.rect(col1, y - row_h, 20*mm, row_h)
    c.rect(col3, y - row_h, 20*mm, row_h)

    c.drawCentredString(col1 + 10*mm, y - 5*mm, "STT")
    c.drawCentredString((col1 + col3)/2, y - 5*mm, "Danh mục hồ sơ")
    c.drawCentredString(col3 + 10*mm, y - 5*mm, "SL")

    y -= row_h

    c.setFont(FONT_NAME, FS)

    for stt, label, qty in listed_docs:

        if y < 70*mm:
            break

        c.rect(LM, y - row_h, table_w, row_h)
        c.rect(col1, y - row_h, 20*mm, row_h)
        c.rect(col3, y - row_h, 20*mm, row_h)

        c.drawCentredString(col1 + 10*mm, y - 5*mm, str(stt))

        # ---- đẩy nội dung tránh sát lề ----
        c.drawString(col2 + 2*mm, y - 5*mm, label)

        c.drawCentredString(col3 + 10*mm, y - 5*mm, str(qty))

        y -= row_h

    # =====================================================
    # GHI CHÚ
    # =====================================================
    y -= 10*mm
    c.setFont(FONT_BOLD, FS); c.drawString(LM, y, "Ghi chú:")
    c.setFont(FONT_NAME, FS); c.drawString(LM + 20*mm, y, ghi_chu)

    # =====================================================
    # KÝ TÊN
    # =====================================================
    y -= 25*mm

    c.setFont(FONT_BOLD, FS)
    c.drawCentredString(LM + table_w/4, y, "Người nộp hồ sơ")
    c.drawCentredString(LM + 3*table_w/4, y, "Người nhận hồ sơ")

    y -= 22*mm
    c.setFont(FONT_NAME, FS)
    c.drawCentredString(LM + table_w/4, y, full_name)
    c.drawCentredString(LM + 3*table_w/4, y, nguoi_nhan)

    # =====================================================
    c.showPage()
    c.save()
    return buf.getvalue()

# ==============================
# A5 Receipt PDF
def render_student_receipt_pdf_a5(a, docs) -> bytes:
    from reportlab.lib.pagesizes import A5, landscape
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    from datetime import datetime, timedelta
    import io

    _ensure_fonts()

    FONT = FONT_NAME
    FONT_B = FONT_BOLD
    SIZE = 10

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=landscape(A5))
    page_w, page_h = landscape(A5)

    # Set document title
    full_name = getattr(a, "full_name", "") or ""
    ma = getattr(a, "ma_so_hv", "") or ""
    safe = f"{ma}_{full_name}".replace(" ", "_")
    c.setTitle(safe)

    LM = 15 * mm
    RM = 15 * mm
    TM = 10 * mm
    y = page_h - TM

    # HEADER
    khoa = getattr(a, "khoa", "") or ""
    title = f"BIÊN NHẬN HỒ SƠ NHẬP HỌC CHƯƠNG TRÌNH ĐÀO TẠO TỪ XA KHÓA 20{khoa}"

    c.setFont(FONT_B, SIZE + 4)
    c.drawCentredString(page_w/2, y, title)

    y -= 6*mm

    # SUB
    # subline = (
    #     f"Viện Hợp tác và Phát triển Đào tạo HUTECH xác nhận đã nhận hồ sơ nhập học "
    #     f"khóa 20{khoa} của Anh/Chị đã gửi theo hình thức BƯU ĐIỆN:"
    # )
    # c.setFont(FONT, SIZE)
    # c.drawCentredString(page_w/2, y, subline)
    # y -= 6 * mm

    c.setFont(FONT, SIZE)
    normal_1 = f"Viện Hợp tác và Phát triển Đào tạo HUTECH xác nhận đã nhận hồ sơ nhập học khóa 20{khoa} của Anh/Chị đã gửi theo hình thức "
    normal_2 = ":"
    bold_text = "BƯU ĐIỆN"

    # canh giữa nguyên câu cần tính width
    w = c.stringWidth(normal_1 + bold_text + normal_2, FONT, SIZE)
    center_x = page_w/2 - w/2

    # in từng phần
    c.setFont(FONT, SIZE)
    c.drawString(center_x, y, normal_1)

    x2 = center_x + c.stringWidth(normal_1, FONT, SIZE)

    c.setFont(FONT_B, SIZE)
    c.drawString(x2, y, bold_text)

    x3 = x2 + c.stringWidth(bold_text, FONT_B, SIZE)

    c.setFont(FONT, SIZE)
    c.drawString(x3, y, normal_2)

    y -= 6*mm

    # INFO BLOCK
    lh = 5.0 * mm

    full_name = getattr(a, "full_name", "")
    dob = a.ngay_sinh.strftime('%d/%m/%Y') if a.ngay_sinh else ""
    sdt = getattr(a, "so_dt", "") or ""
    email = getattr(a, "email_hoc_vien", None) or getattr(a, "email", "") or ""
    masv = getattr(a, "ma_so_hv", "") or ""
    dot = getattr(a, "dot", "") or ""
    nganh = getattr(a, "nganh_nhap_hoc", "") or getattr(a, "nganh", "") or ""
    da_tn = getattr(a, "da_tn_truoc_do", "") or ""

    c.setFont(FONT_B, SIZE); c.drawString(LM, y, "Họ và tên:")
    c.setFont(FONT, SIZE);   c.drawString(LM+28*mm, y, full_name)

    c.setFont(FONT_B, SIZE); c.drawString(LM+92*mm, y, "Ngày sinh:")
    c.setFont(FONT, SIZE);   c.drawString(LM+118*mm, y, dob)

    c.setFont(FONT_B, SIZE); c.drawString(page_w - RM - 30*mm, y, "SĐT:")
    c.setFont(FONT, SIZE);   c.drawString(page_w - RM - 15*mm, y, sdt)

    y -= lh

    c.setFont(FONT_B, SIZE); c.drawString(LM, y, "Mã số HV:")
    c.setFont(FONT, SIZE);   c.drawString(LM+28*mm, y, masv)

    c.setFont(FONT_B, SIZE); c.drawString(LM+92*mm, y, "Email:")
    c.setFont(FONT, SIZE);   c.drawString(LM+118*mm, y, email)
    y -= lh

    c.setFont(FONT_B, SIZE); c.drawString(LM, y, "Ngành nhập học:")
    c.setFont(FONT, SIZE);   c.drawString(LM+32*mm, y, nganh)

    c.setFont(FONT_B, SIZE); c.drawString(LM+92*mm, y, "Đợt:")
    c.setFont(FONT, SIZE);   c.drawString(LM+103*mm, y, dot)

    c.setFont(FONT_B, SIZE); c.drawRightString(page_w - RM - 28*mm, y, "Đã TN:")
    c.setFont(FONT, SIZE);   c.drawRightString(page_w - RM - 2*mm, y, da_tn)

    y -= 6*mm

    # TABLE TITLE
    c.setFont(FONT_B, SIZE)
    c.drawString(LM, y, "Hồ sơ gồm có:")
    y -= 2 * mm

    # TABLE COORD
    table_w = page_w - LM - RM
    row_h = 5 * mm

    col_stt = LM
    col_stt_w = 12*mm

    col_qty_w = 15*mm
    col_qty = page_w - RM - col_qty_w

    col_name = col_stt + col_stt_w
    col_name_w = table_w - col_stt_w - col_qty_w

    # HEADER ROW
    c.setFont(FONT_B, SIZE)
    c.rect(LM, y - row_h, table_w, row_h)  
    c.rect(col_stt, y - row_h, col_stt_w, row_h)
    c.rect(col_qty, y - row_h, col_qty_w, row_h)

    c.drawCentredString(col_stt + col_stt_w/2, y - 4*mm, "STT")
    c.drawCentredString(col_name + col_name_w/2, y - 4*mm, "Danh mục hồ sơ")
    c.drawCentredString(col_qty + col_qty_w/2, y - 4*mm, "Số lượng")

    y -= row_h

    # DATA
    # lấy label Việt Nam hợp lệ
    from app.services.pdf_service import DOC_DISPLAY_NAME

    c.setFont(FONT, SIZE)

    stt = 1
    # luôn in đủ 11 danh mục hồ sơ cố định
    fixed_labels = [
        "Sơ yếu lý lịch",
        "Bằng tốt nghiệp THPT (hoặc tương đương)",
        "Học bạ THPT (hoặc Bảng điểm THPT)",
        "Bằng tốt nghiệp Đại học",
        "Bảng điểm Đại học",
        "Bằng tốt nghiệp Cao đẳng",
        "Bảng điểm Cao đẳng",
        "Bằng tốt nghiệp Trung cấp",
        "Bảng điểm Trung cấp",
        "Căn cước công dân",
        "Đơn xin miễn giảm học phần",
    ]

    # tạo mapping code -> qty từ docs thật
    qty_map = {}
    for d in docs:
        code = (getattr(d, "code", "") or "").lower()
        qty_map[code] = int(getattr(d, "so_luong", 0) or 0)

    stt = 1
    c.setFont(FONT, SIZE)
    for name in fixed_labels:

        if y < 35*mm:
            break

        # lấy qty nếu có, không có thì 0
        qty = 0
        for d in docs:
            code = (getattr(d, "code", "") or "").lower()
            label = DOC_DISPLAY_NAME.get(code, code)
            if label == name:
                qty = int(getattr(d, "so_luong", 0) or 0)
                break

        # vẽ 1 row
        c.rect(LM, y - row_h, table_w, row_h)
        c.rect(col_stt, y - row_h, col_stt_w, row_h)
        c.rect(col_qty, y - row_h, col_qty_w, row_h)

        c.drawCentredString(col_stt + col_stt_w/2, y - 4.5*mm, str(stt))
        c.drawString(col_name + 1*mm, y - 4.5*mm, name)
        c.drawCentredString(col_qty + col_qty_w/2, y - 4.5*mm, str(qty))

        y -= row_h
        stt += 1

    # GHI CHÚ
    y -= 4*mm
    c.setFont(FONT_B, SIZE)
    c.drawString(LM, y, "Ghi chú:")

    y -= 2 * mm

    # DATE
    # ===== SIGNATURE AREA =====
    vn_now = datetime.utcnow() + timedelta(hours=7)
    date_text = f"TP. Hồ Chí Minh, ngày {vn_now.day:02d} tháng {vn_now.month:02d} năm {vn_now.year}"

    # Date line
    y -= 6 * mm
    c.setFont(FONT, SIZE)
    c.drawRightString(page_w - RM, y, date_text)

    # coordinates
    y -= 5 * mm  # move signatures up/down
    sig_y = y

    # names
    nguoi_gui = getattr(a, "full_name", "") or ""
    nguoi_nhan = getattr(a, "nguoi_nhan_ky_ten", None) or ""

    # LEFT SIGN BOX (centered block)
    left_x = LM + 35*mm   # lùi vào trong

    c.setFont(FONT_B, SIZE)
    c.drawCentredString(left_x, sig_y, "Người gửi")

    c.setFont(FONT_ITALIC, SIZE)
    c.drawCentredString(left_x, sig_y - 5*mm, "")

    c.setFont(FONT_B, SIZE)
    c.drawCentredString(left_x, sig_y - 12*mm, nguoi_gui)

    # RIGHT SIGN BOX (centered block)
    right_x = page_w - RM - 35*mm   # lùi vào trong

    c.setFont(FONT_B, SIZE)
    c.drawCentredString(right_x, sig_y, "Người nhận")

    c.setFont(FONT_ITALIC, SIZE)
    c.drawCentredString(right_x, sig_y - 5*mm, "(đã ký)")

    c.setFont(FONT_B, SIZE)
    c.drawCentredString(right_x, sig_y - 12*mm, nguoi_nhan)

    c.save()
    return buf.getvalue()

    # =====================================================