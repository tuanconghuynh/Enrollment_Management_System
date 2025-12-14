# app/services/pdf_service.py
from datetime import datetime, date, timedelta
import io, os, re, unicodedata
from typing import List, Dict, Any
from pathlib import Path

from reportlab.lib.pagesizes import A4, A5, landscape
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import Table, TableStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import stringWidth

from ..core.config import settings
from ..models.applicant import Applicant, ApplicantDoc
from ..models.checklist import ChecklistItem

from reportlab.platypus import (
    Table, TableStyle, BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer
)
from reportlab.lib.styles import getSampleStyleSheet

# === Giờ Việt Nam (Asia/Ho_Chi_Minh) ===
try:
    from zoneinfo import ZoneInfo  # Python 3.9+
    _VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
    def _now_vn() -> datetime:
        return datetime.now(_VN_TZ)
except Exception:
    # Fallback khi không có zoneinfo (hiếm): cộng tay +7h
    def _now_vn() -> datetime:
        return datetime.utcnow() + timedelta(hours=7)


# ================== cấu hình chữ & lề ==================
TITLE_SIZE = 13
TEXT_SIZE  = 12

# Lề trang gọn hơn theo yêu cầu
LM, RM, TM, BM = 15*mm, 15*mm, 18*mm, 18*mm

# Dãn dòng
PARA_LEADING = 6.2 * mm
KV_STEP      = 6.5 * mm

# Font mặc định (sẽ đổi sau khi register)
FONT_REG  = "Times-Roman"
FONT_BOLD = "Times-Bold"
# =======================================================

def _first_existing(paths):
    for p in paths:
        if not p:
            continue
        p = os.path.abspath(str(p).strip().strip('"').strip("'"))
        if os.path.exists(p):
            return p
    return None

def _register_font_times():
    r"""
    Tự dò Times New Roman/DejaVu:
      - settings.FONT_PATH / FONT_PATH_BOLD
      - assets\TimesNewRoman(.ttf/.Bold.ttf)
      - C:\Windows\Fonts\times(.ttf/.bd.ttf)
      - assets\DejaVuSans(.ttf/.Bold.ttf)
    Không có -> fallback Times-Roman/Times-Bold (không crash).
    """
    global FONT_REG, FONT_BOLD

    reg = _first_existing([
        getattr(settings, "FONT_PATH", None),
        os.path.join(os.getcwd(), "assets", "TimesNewRoman.ttf"),
        r"C:\Windows\Fonts\times.ttf",
        os.path.join(os.getcwd(), "assets", "DejaVuSans.ttf"),
    ])
    bold = _first_existing([
        getattr(settings, "FONT_PATH_BOLD", None) or getattr(settings, "FONT_PATH", None),
        os.path.join(os.getcwd(), "assets", "TimesNewRoman-Bold.ttf"),
        r"C:\Windows\Fonts\timesbd.ttf",
        os.path.join(os.getcwd(), "assets", "DejaVuSans-Bold.ttf"),
    ])

    try:
        if reg:
            pdfmetrics.registerFont(TTFont("TNR", reg))
            FONT_REG = "TNR"
        if bold:
            pdfmetrics.registerFont(TTFont("TNR-Bold", bold))
            FONT_BOLD = "TNR-Bold"
    except Exception as e:
        print("[WARN] Could not register TrueType fonts:", e)
        # giữ fallback


def _wrap_lines(text: str, font: str, size: int, max_w: float):
    words = (text or "").split()
    lines, cur = [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if stringWidth(t, font, size) <= max_w:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines

# ===== Helper tên: ưu tiên ho_dem + ten, fallback ho_ten =====
def _name_parts(a: Applicant):
    """
    Trả về (ho_dem, ten) nếu có; nếu không, cố gắng tách từ ho_ten.
    """
    ln = (getattr(a, "ho_dem", None) or "").strip()
    fn = (getattr(a, "ten", None) or "").strip()
    if ln or fn:
        return ln, fn
    full = (getattr(a, "ho_ten", None) or "").strip()
    if not full:
        return "", ""
    parts = full.split()
    if len(parts) == 1:
        return "", parts[0]
    return " ".join(parts[:-1]), parts[-1]

def _full_name(a: Applicant) -> str:
    ln, fn = _name_parts(a)
    if ln or fn:
        return f"{ln} {fn}".strip()
    return (getattr(a, "ho_ten", None) or "").strip()

# ===== Vẽ cặp "Nhãn: Giá trị" bám sát dấu ":" =====
def _draw_kv(c, x_label, _x_val_ignored, y, label, value, step=KV_STEP, gap=1.4*mm):
    """
    Vẽ 'Nhãn:' (regular) và giá trị (bold) ngay sau dấu ':'.
    Giữ nguyên signature để không phải sửa gọi.
    """
    lbl = (label or "").rstrip(":")
    lbl_text = f"{lbl}:"

    c.setFont(FONT_REG, TEXT_SIZE)
    c.drawString(x_label, y, lbl_text)

    x_val = x_label + stringWidth(lbl_text, FONT_REG, TEXT_SIZE) + gap
    c.setFont(FONT_BOLD, TEXT_SIZE)
    c.drawString(x_val, y, value or "")

    return y - step

# ================== Danh mục hồ sơ (có STT) ==================
def _build_checklist_rows(items: List[ChecklistItem], docs: List[ApplicantDoc]):
    doc_map = {d.code: d.so_luong for d in docs}
    rows = [["STT", "Danh mục", "Số lượng"]]
    stt = 1
    for it in items:
        qty = int(doc_map.get(it.code, 0) or 0)
        rows.append([str(stt), it.display_name, "" if qty == 0 else str(qty)])
        stt += 1
    return rows

def _draw_checklist_table(c: rl_canvas.Canvas, x, y, w, rows):
    """Bảng danh mục 3 cột (STT/Danh mục/Số lượng)."""
    table = Table(rows, colWidths=[w*0.10, w*0.68, w*0.22])
    table.setStyle(TableStyle([
        ("FONTNAME",   (0,0), (-1,-1), FONT_REG),
        ("FONTNAME",   (0,0), (-1,0),  FONT_BOLD),
        ("FONTSIZE",   (0,0), (-1,-1), TEXT_SIZE),
        ("ALIGN",      (0,0), (-1,0),  "CENTER"),   # header giữa
        ("ALIGN",      (0,1), (0,-1),  "CENTER"),   # STT giữa
        ("ALIGN",      (-1,1), (-1,-1),  "CENTER"), # số lượng giữa
        ("GRID",       (0,0), (-1,-1), 0.5, colors.black),
        ("TOPPADDING",    (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 4),
        ("RIGHTPADDING",  (0,0), (-1,-1), 4),
    ]))
    table.wrapOn(c, 0, 0)
    table.drawOn(c, x, y - table._height)
    return y - table._height
# ============================================================

# ---------- Normalization & splitting helpers ----------
def _normalize_text_simple(s: str | None) -> str:
    if not s:
        return ""
    s = str(s)
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower()
    s = re.sub(r"[^a-z0-9]", "", s)
    return s

_SPECIAL_DOC_NAMES = [
    "Bằng tốt nghiệp Đại học",
    "Bảng điểm toàn khoá học Đại học",
    "Bằng tốt nghiệp Cao đẳng",
    "Bảng điểm toàn khóa học Cao đẳng",
    "Bằng tốt nghiệp Trung Cấp",
    "Bảng điểm toàn khóa Trung Cấp",
]
_EXEMPT_NAME = "Đơn miễn giảm"
_SPECIAL_DOC_NAMES_N = {_normalize_text_simple(x) for x in _SPECIAL_DOC_NAMES}
_EXEMPT_NAME_N = _normalize_text_simple(_EXEMPT_NAME)

def _is_special_name(name: str | None) -> bool:
    return _normalize_text_simple(name) in _SPECIAL_DOC_NAMES_N

def _is_exempt_name(name: str | None) -> bool:
    return _normalize_text_simple(name) == _EXEMPT_NAME_N

def _split_doc_rows_for_items(items: List[ChecklistItem], docs: List[ApplicantDoc]):
    """
    Trả về (main_row_qtys, reduced_row_qtys, display_names)
    main_row_qtys/reduced_row_qtys nằm theo thứ tự items.
    docs: list ApplicantDoc (code -> so_luong). Try to match code or display_name (normalize + fuzzy).
    """
    dm = {}
    for d in docs or []:
        key = getattr(d, "code", "") or ""
        qty = int(getattr(d, "so_luong", 0) or 0)
        dm[key] = qty
        kn = _normalize_text_simple(key)
        if kn and kn not in dm:
            dm[kn] = qty

    main = []
    reduced = []
    displays = []
    for it in items or []:
        code = getattr(it, "code", None) or ""
        disp = getattr(it, "display_name", None) or code or ""
        displays.append(disp)

        qty = 0
        # exact match
        if code in dm:
            qty = int(dm.get(code, 0) or 0)
        elif disp in dm:
            qty = int(dm.get(disp, 0) or 0)
        else:
            code_n = _normalize_text_simple(code)
            disp_n = _normalize_text_simple(disp)
            if code_n and code_n in dm:
                qty = int(dm.get(code_n, 0) or 0)
            elif disp_n and disp_n in dm:
                qty = int(dm.get(disp_n, 0) or 0)
            else:
                # fuzzy normalized substring match
                for k, v in dm.items():
                    kn = _normalize_text_simple(k)
                    if not kn:
                        continue
                    if (code_n and (kn in code_n or code_n in kn)) or (disp_n and (kn in disp_n or disp_n in kn)):
                        qty = int(v or 0)
                        break

        if _is_special_name(code) or _is_special_name(disp):
            m = 1 if qty > 0 else 0
            r = qty - m if qty > 0 else 0
        elif _is_exempt_name(code) or _is_exempt_name(disp):
            m = 0
            r = qty
        else:
            m = qty
            r = 0

        main.append(int(m))
        reduced.append(int(r))

    return main, reduced, displays

# ===== Chuẩn hóa ngày dd/mm/yyyy =====
def _fmt_dmy(v) -> str:
    if not v:
        return ""
    if isinstance(v, (datetime, date)):
        return v.strftime("%d/%m/%Y")
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.strftime("%d/%m/%Y")
        except ValueError:
            pass
    try:
        dt = datetime.fromisoformat(s)
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return s

def _header_block(c: rl_canvas.Canvas, W, H, khoa: str, ma_hs: str, ngay_nhan):
    """
    Header:
      [1] Khung MÃ HỒ SƠ (góc phải)
      [2] TIÊU ĐỀ
      [3] Ngày nhận HS
      [4] Đoạn intro “Viện Hợp tác…”
    """
    # [1] KHUNG MÃ HỒ SƠ
    box_w, box_h = 42*mm, 14*mm
    x_box = W - box_w - 8*mm
    y_box = H - 7*mm - box_h

    c.setLineWidth(1.0)
    c.roundRect(x_box, y_box, box_w, box_h, 3.0*mm, stroke=1, fill=0)
    c.setFont(FONT_BOLD, 11); c.drawCentredString(x_box + box_w/2, y_box + box_h - 4*mm, "MÃ HỒ SƠ")
    c.setFont(FONT_BOLD, 13); c.drawCentredString(x_box + box_w/2, y_box + 4*mm, (ma_hs or ""))

    # [2] TIÊU ĐỀ
    title_y = y_box - 12*mm
    c.setFont(FONT_BOLD, TITLE_SIZE)
    title = "BIÊN NHẬN HỒ SƠ NHẬP HỌC CHƯƠNG TRÌNH ĐÀO TẠO TỪ XA"
    if (khoa or "").strip():
        title += f" KHÓA {khoa.strip()}"
    c.drawCentredString(W/2, title_y, title)

    # [3] Ngày nhận HS
    date_y = title_y - 7*mm
    c.setFont(FONT_BOLD, TEXT_SIZE + 1)
    c.drawRightString(W - RM, date_y, f"Ngày nhận HS: {_fmt_dmy(ngay_nhan)}")

    # [4] Intro
    y = date_y - 10*mm
    c.setFont(FONT_REG, TEXT_SIZE)
    intro = "Viện Hợp tác và Phát triển Đào tạo xác nhận đã nhận hồ sơ nhập học"
    intro += f" khóa {khoa.strip()} của Anh/Chị:" if (khoa or "").strip() else " của Anh/Chị:"
    text_w = W - LM - RM
    for line in _wrap_lines(intro, FONT_REG, TEXT_SIZE, text_w):
        c.drawString(LM, y, line)
        y -= PARA_LEADING
    return y

def _draw_signature_block(c: rl_canvas.Canvas, y, W, receiver_name: str):
    """Bảng chữ ký 2 cột × 3 hàng (1 hàng trống + nhãn + tên)."""
    table_w = W - LM - RM
    spacer_h, label_h, sign_h = 1*PARA_LEADING, 12*mm, 36*mm
    row_heights = [spacer_h, label_h, sign_h]
    col_widths  = [table_w*0.5, table_w*0.5]

    data = [["",""], ["","Người nhận"], ["", receiver_name or ""]]
    t = Table(data, colWidths=col_widths, rowHeights=row_heights)
    t.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,-1), FONT_REG),
        ("FONTNAME", (1,2), (1,2), FONT_BOLD),
        ("FONTSIZE", (0,0), (-1,-1), TEXT_SIZE),
        ("ALIGN",    (1,1), (1,2), "CENTER"),
        ("VALIGN",   (0,0), (-1,-1), "MIDDLE"),
        ("INNERGRID",(0,0),(-1,-1),0,colors.white),
        ("LINEABOVE",(0,0),(-1,-1),0,colors.white),
        ("LINEBELOW",(0,0),(-1,-1),0,colors.white),
        ("TOPPADDING",(0,0),(-1,-1),2),
        ("BOTTOMPADDING",(0,0),(-1,-1),2),
    ]))
    t.wrapOn(c, 0, 0)
    total_h = sum(row_heights)
    t.drawOn(c, LM, y - total_h)
    return y - total_h

def _vn_date_line(d: date | datetime | None, location: str = "TP.HCM") -> str:
    """
    Trả về chuỗi: 'TP.HCM, ngày dd tháng mm năm yyyy'
    - Nếu d=None -> dùng ngày hiện tại theo múi giờ Việt Nam.
    - Nếu d là date -> nâng lên datetime để format đồng nhất.
    """
    if not d:
        d = _now_vn()
    if isinstance(d, date) and not isinstance(d, datetime):
        d = datetime(d.year, d.month, d.day)
    return f"{location}, ngày {d.day:02d} tháng {d.month:02d} năm {d.year}"

def _onpage_footer_a5(canvas, doc, a: Applicant, location: str = "TP.HCM"):
    """Vẽ footer cố định (A5 ngang)."""
    W, H = landscape(A5)
    bm = 6 * mm
    y0 = bm + 4*mm
    canvas.saveState()

    canvas.setFont(FONT_REG, 9)
    canvas.drawCentredString(W/2, y0 + 18*mm, _vn_date_line(getattr(a, "ngay_nhan_hs", None), location))

    left_x  = W/2 - 55*mm
    right_x = W/2 + 55*mm
    canvas.setFont(FONT_BOLD, 10)
    canvas.drawCentredString(left_x,  y0 + 10*mm, "NGƯỜI NỘP HỒ SƠ")
    canvas.drawCentredString(right_x, y0 + 10*mm, "NGƯỜI NHẬN HỒ SƠ")

    canvas.setFont(FONT_REG, 9)
    canvas.drawCentredString(left_x,  y0 + 4*mm, "(Ký, ghi rõ họ tên)")
    canvas.drawCentredString(right_x, y0 + 4*mm, "(Ký, ghi rõ họ tên)")

    canvas.setLineWidth(0.6)
    line_w = 50 * mm
    canvas.line(left_x - line_w/2,  y0, left_x + line_w/2,  y0)
    canvas.line(right_x - line_w/2, y0, right_x + line_w/2, y0)
    canvas.restoreState()

# ========= New helper to draw one receipt copy (below header area) =========
def _draw_receipt_copy(c: rl_canvas.Canvas, y: float, W: float, H: float,
                       a: Applicant, items: List[ChecklistItem], docs: List[ApplicantDoc],
                       receiver_name: str) -> float:
    """
    Draw the body of one receipt copy starting from y (current top y after header lines).
    Returns the y position after drawing this copy (bottom of copy).
    """
    left_lbl, left_val   = LM,          LM + 26*mm
    right_lbl, right_val = LM + 85*mm,  LM + 110*mm

    # Info rows
    y_l = _draw_kv(c, left_lbl,  left_val,  y, "Họ và tên:",      _full_name(a))
    y_r = _draw_kv(c, right_lbl, right_val, y, "Mã số HV:",       a.ma_so_hv or "");                       y = min(y_l, y_r)

    y_l = _draw_kv(c, left_lbl,  left_val,  y, "Ngày sinh:",      _fmt_dmy(a.ngay_sinh))
    y_r = _draw_kv(c, right_lbl, right_val, y, "Giới tính:",      getattr(a, "gioi_tinh", "") or "");     y = min(y_l, y_r)

    y_l = _draw_kv(c, left_lbl,  left_val,  y, "Số ĐT:",          a.so_dt or "")
    y_r = _draw_kv(c, right_lbl, right_val, y, "Email HV:",       getattr(a, "email_hoc_vien", "") or "");y = min(y_l, y_r)

    y_l = _draw_kv(c, left_lbl,  left_val,  y, "Dân tộc:",        getattr(a, "dan_toc", "") or "")
    y_r = _draw_kv(c, right_lbl, right_val, y, "Ngành nhập học:", getattr(a, "nganh_nhap_hoc", None) or getattr(a, "nganh", None) or ""); y = min(y_l, y_r)

    y_l = _draw_kv(c, left_lbl,  left_val,  y, "Đã TN:",          a.da_tn_truoc_do or "")
    y_r = _draw_kv(c, right_lbl, right_val, y, "Đợt:",            a.dot or "");                            y = min(y_l, y_r)

    # Hồ sơ gồm (main)
    c.setFont(FONT_BOLD, TEXT_SIZE); c.drawString(LM, y, "Hồ sơ gồm:")
    y -= 6*mm

    main_row, reduced_row, displays = _split_doc_rows_for_items(items, docs)
    rows_main = [["STT", "Danh mục", "Số lượng"]]
    for idx, disp in enumerate(displays, start=1):
        rows_main.append([str(idx), disp, str(main_row[idx-1])])

    y = _draw_checklist_table(c, LM, y, W - LM - RM, rows_main)

    # Ghi chú
    y -= 6*mm
    c.setFont(FONT_REG, TEXT_SIZE);  c.drawString(LM, y, "Ghi chú:")
    c.setFont(FONT_BOLD, TEXT_SIZE)
    NOTE_LABEL_W = 22 * mm
    text_w = W - LM - RM - NOTE_LABEL_W
    note_text = a.ghi_chu or ""
    lines = _wrap_lines(note_text, FONT_BOLD, TEXT_SIZE, text_w)
    y_note = y
    for line in lines:
        c.drawString(LM + NOTE_LABEL_W, y_note, line)
        y_note -= PARA_LEADING

    # Hồ sơ xét miễn môn
    y = y_note - 8*mm
    c.setFont(FONT_BOLD, TEXT_SIZE); c.drawString(LM, y, "HỒ SƠ XÉT MIỄN MÔN")
    y -= 6*mm

    rows_red = [["STT", "Danh mục", "Số lượng"]]
    st = 1
    for idx, disp in enumerate(displays):
        q = reduced_row[idx]
        rows_red.append([str(st), disp, str(q)])
        st += 1

    y = _draw_checklist_table(c, LM, y, W - LM - RM, rows_red)

    # signature block for this copy
    y_sig_top = y - 10*mm
    _draw_signature_block(c, y_sig_top, W, receiver_name or "")

    return y_sig_top

# ================== A4: 1 hồ sơ (modified to draw 2 copies on one page) ==================
def render_single_pdf(a: Applicant, items: List[ChecklistItem], docs: List[ApplicantDoc]) -> bytes:
    _register_font_times()
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"Bản in A4 - {_full_name(a)}")
    W, H = A4

    # Draw header (top) and get the y after header area
    y_top = _header_block(
        c, W, H,
        getattr(a, "khoa", "") or "",
        a.ma_ho_so,
        a.ngay_nhan_hs
    )

    # First copy (top)
    y_after_first = _draw_receipt_copy(c, y_top, W, H, a, items, docs, a.nguoi_nhan_ky_ten or "")

    # Estimate gap and compute second copy starting position
    gap_between = 8 * mm

    # Compute used height by first copy (approx)
    used_height_first = y_top - y_after_first
    # Start second header a bit below the bottom of first copy
    second_header_y = y_after_first - gap_between + 12*mm  # tweak offset for header area

    # Draw compact header for second copy (title + intro)
    c.setFont(FONT_BOLD, TITLE_SIZE)
    title = "BIÊN NHẬN HỒ SƠ NHẬP HỌC CHƯƠNG TRÌNH ĐÀO TẠO TỪ XA"
    if (a.khoa or "").strip():
        title += f" KHÓA {a.khoa.strip()}"
    c.drawCentredString(W/2, second_header_y, title)

    c.setFont(FONT_REG, TEXT_SIZE)
    intro = "Viện Hợp tác và Phát triển Đào tạo xác nhận đã nhận hồ sơ nhập học"
    intro += f" khóa {a.khoa.strip()} của Anh/Chị:" if (a.khoa or "").strip() else " của Anh/Chị:"
    y_intro = second_header_y - 7*mm
    for line in _wrap_lines(intro, FONT_REG, TEXT_SIZE, W - LM - RM):
        c.drawString(LM, y_intro, line)
        y_intro -= PARA_LEADING

    # Draw second copy body
    _draw_receipt_copy(c, y_intro - 4*mm, W, H, a, items, docs, a.nguoi_nhan_ky_ten or "")

    c.showPage()
    c.save()
    return buf.getvalue()

# ================== A4: in gộp ==================
def render_batch_pdf(
    apps: List[Applicant],
    items_by_version: Dict[int, List[ChecklistItem]],
    docs_by_app: Dict[str, List[ApplicantDoc]],   # key = MSSV
):
    _register_font_times()
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)
    c.setTitle("Bản in A4 - Danh sách")
    W, H = A4

    for a in apps:
        items = items_by_version.get(a.checklist_version_id, [])
        docs  = docs_by_app.get(a.ma_so_hv, [])

        y = _header_block(
            c, W, H,
            getattr(a, "khoa", "") or "",
            a.ma_ho_so,
            a.ngay_nhan_hs
        )

        # 2 cột thông tin
        left_lbl, left_val   = LM,         LM + 26*mm
        right_lbl, right_val = LM + 85*mm, LM + 110*mm

        # Hàng 1
        y_l = _draw_kv(c, left_lbl,  left_val,  y, "Họ và tên:",      _full_name(a))
        y_r = _draw_kv(c, right_lbl, right_val, y, "Mã số HV:",       a.ma_so_hv or "");                       y = min(y_l, y_r)

        # Hàng 2
        y_l = _draw_kv(c, left_lbl,  left_val,  y, "Ngày sinh:",      _fmt_dmy(a.ngay_sinh))
        y_r = _draw_kv(c, right_lbl, right_val, y, "Giới tính:",      getattr(a, "gioi_tinh", "") or "");     y = min(y_l, y_r)

        # Hàng 3
        y_l = _draw_kv(c, left_lbl,  left_val,  y, "Số ĐT:",          a.so_dt or "")
        y_r = _draw_kv(c, right_lbl, right_val, y, "Email HV:",       getattr(a, "email_hoc_vien", "") or "");y = min(y_l, y_r)

        # Hàng 4
        y_l = _draw_kv(c, left_lbl,  left_val,  y, "Dân tộc:",        getattr(a, "dan_toc", "") or "")
        y_r = _draw_kv(c, right_lbl, right_val, y, "Ngành nhập học:", a.nganh_nhap_hoc or "");                y = min(y_l, y_r)

        # Hàng 5
        y_l = _draw_kv(c, left_lbl,  left_val,  y, "Đã TN:",          a.da_tn_truoc_do or "")
        y_r = _draw_kv(c, right_lbl, right_val, y, "Đợt:",            a.dot or "");                            y = min(y_l, y_r)

        # Bảng hồ sơ gồm
        c.setFont(FONT_BOLD, TEXT_SIZE); c.drawString(LM, y, "Hồ sơ gồm:")
        y -= 6*mm
        rows = _build_checklist_rows(items, docs)
        y = _draw_checklist_table(c, LM, y, W - LM - RM, rows)

        # Sau bảng
        y -= 10*mm

        # Ghi chú
        c.setFont(FONT_REG, TEXT_SIZE);  c.drawString(LM, y, "Ghi chú:")
        c.setFont(FONT_BOLD, TEXT_SIZE)
        NOTE_LABEL_W = 22 * mm
        text_w = W - LM - RM - NOTE_LABEL_W
        note_text = a.ghi_chu or ""
        lines = _wrap_lines(note_text, FONT_BOLD, TEXT_SIZE, text_w)
        y_note = y
        for line in lines:
            c.drawString(LM + NOTE_LABEL_W, y_note, line)
            y_note -= PARA_LEADING

        sig_top = y_note - 4*mm
        _draw_signature_block(c, sig_top, W, a.nguoi_nhan_ky_ten or "")

        c.showPage()

    c.save()
    return buf.getvalue()

# ================== BẢN IN A5 TỐI GIẢN (cho học viên) ==================
def _build_rows_nonzero(items: List[ChecklistItem], docs: List[ApplicantDoc]):
    """Chỉ lấy mục có số lượng > 0 để bản A5 gọn + thêm cột STT."""
    doc_map = {d.code: int(d.so_luong or 0) for d in docs}
    rows = [["STT", "Danh mục", "Số lượng"]]
    stt = 1
    for it in items:
        n = int(doc_map.get(it.code, 0))
        if n > 0:
            rows.append([str(stt), it.display_name, str(n)])
            stt += 1
    if len(rows) == 1:
        rows.append(["", "(Chưa nộp hồ sơ!)", ""])
    return rows

def render_single_pdf_a5(a: Applicant, items: List[ChecklistItem], docs: List[ApplicantDoc]) -> bytes:
    """
    A5 ngang, lề sát, intro sát tiêu đề để kéo toàn trang lên trên.
    """
    _register_font_times()
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=landscape(A5))
    c.setTitle(f"Bản in A5 - {_full_name(a)}")
    W, H = landscape(A5)

    # Lề & cỡ chữ gọn
    lm, rm, tm, bm = 8*mm, 8*mm, 6*mm, 6*mm
    title_sz, text_sz = 10, 9
    info_step = 5.0*mm     # hơi gọn hơn
    para_step = 5.2*mm
    intro_step = 4.2*mm    # intro dãn dòng nhỏ để sát tiêu đề

    # ===== Tiêu đề =====
    c.setFont(FONT_BOLD, title_sz)
    title = "BIÊN NHẬN HỒ SƠ NHẬP HỌC CHƯƠNG TRÌNH ĐÀO TẠO TỪ XA"
    if (a.khoa or "").strip():
        title += f" KHÓA {a.khoa.strip()}"
    c.drawCentredString(W/2, H - tm, title)

    # 2 dòng góc phải: đẩy lên cao để nhường chỗ cho intro
    c.setFont(FONT_BOLD, text_sz)
    c.drawRightString(W - rm, H - tm - 4*mm,  f"Mã HS: {a.ma_ho_so or ''}")
    c.drawRightString(W - rm, H - tm - 8*mm,  f"Ngày nhận HS: {_fmt_dmy(a.ngay_nhan_hs)}")

    # ===== Intro: bám sát ngay dưới tiêu đề (nhưng vẫn thấp hơn 2 dòng góc phải) =====
    c.setFont(FONT_REG, text_sz)
    intro = "Viện Hợp tác và Phát triển Đào tạo xác nhận đã nhận hồ sơ nhập học"
    intro += f" khóa {a.khoa.strip()} của Anh/Chị:" if (a.khoa or "").strip() else " của Anh/Chị:"
    text_w = W - lm - rm

    # Bắt đầu intro ngay dưới tiêu đề ~9.5mm (vẫn dưới 2 dòng góc phải ở -4mm và -8mm)
    y = H - tm - 6.0*mm
    for line in _wrap_lines(intro, FONT_REG, text_sz, text_w):
        c.drawString(lm, y, line)
        y -= intro_step

    # Đệm rất mỏng trước khối thông tin
    y -= 1.5*mm

    # ===== Khối thông tin 2 cột (tiếp tục từ y sau intro – không reset y) =====
    left_x, val_x      = lm,         lm + 25*mm
    r_left_x, r_val_x  = lm + 70*mm, lm + 95*mm

    c.setFont(FONT_REG, text_sz);  c.drawString(left_x,  y, "Họ và tên:")
    c.setFont(FONT_BOLD, text_sz); c.drawString(val_x,   y, _full_name(a))
    c.setFont(FONT_REG, text_sz);  c.drawString(r_left_x, y, "MS HV:")
    c.setFont(FONT_BOLD, text_sz); c.drawString(r_val_x,  y, a.ma_so_hv or "")
    y -= info_step

    c.setFont(FONT_REG, text_sz);  c.drawString(left_x,  y, "Ngày sinh:")
    c.setFont(FONT_BOLD, text_sz); c.drawString(val_x,   y, _fmt_dmy(a.ngay_sinh))
    c.setFont(FONT_REG, text_sz);  c.drawString(r_left_x, y, "SDT:")
    c.setFont(FONT_BOLD, text_sz); c.drawString(r_val_x,  y, a.so_dt or "")
    y -= info_step

    c.setFont(FONT_REG, text_sz);  c.drawString(left_x,  y, "Email HV:")
    c.setFont(FONT_BOLD, text_sz); c.drawString(val_x,   y, getattr(a, "email_hoc_vien", "") or "")
    y -= info_step

    c.setFont(FONT_REG, text_sz);  c.drawString(left_x,  y, "Ngành:")
    c.setFont(FONT_BOLD, text_sz); c.drawString(val_x,   y, a.nganh_nhap_hoc or "")
    c.setFont(FONT_REG, text_sz);  c.drawString(r_left_x, y, "Khóa:")
    c.setFont(FONT_BOLD, text_sz); c.drawString(r_val_x,  y, getattr(a, "khoa", "") or "")
    y -= para_step

    # ===== Bảng giấy tờ đã nộp (số lượng >0) =====
    rows = _build_rows_nonzero(items, docs)     # ⬅️ có STT
    table_w = W - lm - rm
    tbl = Table(rows, colWidths=[table_w*0.12, table_w*0.66, table_w*0.22])
    tbl.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,-1), FONT_REG),
        ("FONTNAME", (0,0), (-1,0),  FONT_BOLD),
        ("FONTSIZE", (0,0), (-1,-1), text_sz),
        ("ALIGN",    (0,0), (-1,0),  "CENTER"),    # header giữa
        ("ALIGN",    (0,1), (0,-1),  "CENTER"),    # STT giữa
        ("ALIGN",    (-1,1), (-1,-1), "CENTER"),   # số lượng giữa
        ("GRID",     (0,0), (-1,-1), 0.4, colors.black),
        ("TOPPADDING",(0,0),(-1,-1), 2),
        ("BOTTOMPADDING",(0,0),(-1,-1), 1),
        ("LEFTPADDING",(0,0),(-1,-1), 3),
        ("RIGHTPADDING",(0,0),(-1,-1), 3),
    ]))
    tbl.wrapOn(c, 0, 0)
    tbl_h = tbl._height
    tbl.drawOn(c, lm, y - tbl_h)
    y = y - tbl_h - 4*mm

    # ===== Ghi chú (nếu có) =====
    if a.ghi_chu:
        c.setFont(FONT_REG, text_sz);  c.drawString(lm, y, "Ghi chú:")
        c.setFont(FONT_BOLD, text_sz); c.drawString(lm + 15*mm, y, a.ghi_chu)
        y -= 8*mm

    # ===== Footer cố định sát chân trang =====
    bm_footer    = 1*mm              # mép dưới an toàn
    sign_label_h = 6*mm              # hàng "Người nộp/nhận"
    sign_area_h  = 24*mm             # vùng ký tên
    sign_h       = sign_label_h + sign_area_h

    # Dòng ngày tháng năm — căn phải, nằm ngay trên khu ký tên ~3mm
    c.setFont(FONT_REG, 9)
    c.drawRightString(
        W - rm,
        bm_footer + sign_h + 2*mm,
        _vn_date_line(None, "TP.HCM")
    )
    # Bảng chữ ký: Người nộp (HV) — Người nhận (NV)
    content_w = W - lm - rm
    sign_w    = content_w / 2.0
    total_w   = sign_w * 2
    x_right   = W - rm - total_w   # neo block sát lề phải

    sig = Table(
        [["Người nộp", "Người nhận"],
         [_full_name(a), a.nguoi_nhan_ky_ten or ""]],
        colWidths=[sign_w, sign_w],
        rowHeights=[sign_label_h, sign_area_h],
    )
    sig.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,0), FONT_REG),
        ("FONTNAME", (0,1), (1,1), FONT_BOLD),
        ("ALIGN",    (0,0), (-1,-1), "CENTER"),
        ("VALIGN",   (0,0), (-1,-1), "MIDDLE"),
        ("LINEBEFORE",(0,0),(-1,-1),0,colors.white),
        ("LINEAFTER", (0,0),(-1,-1),0,colors.white),
        ("LINEABOVE", (0,0),(-1,-1),0,colors.white),
        ("LINEBELOW", (0,0),(-1,-1),0,colors.white),
        ("INNERGRID", (0,0),(-1,-1),0,colors.white),
    ]))
    sig.wrapOn(c, 0, 0)
    sig.drawOn(c, x_right, bm_footer)  # <-- đặt sát chân trang

    c.showPage(); c.save()
    return buf.getvalue()

# ===== LƯU FILE PDF BIÊN NHẬN (A4/A5) =====
def save_receipt_pdf_file(
    a: Applicant,
    items: List[ChecklistItem],
    docs: List[ApplicantDoc],
    *,
    a5: bool = False,
    out_dir: str | Path | None = None,
) -> str:
    """Render biên nhận (A4/A5) -> ghi file -> trả về absolute path."""
    data = render_single_pdf_a5(a, items, docs) if a5 else render_single_pdf(a, items, docs)

    base_dir: Path = Path(out_dir).resolve() if out_dir else getattr(settings, "receipts_path", Path("assets/receipts"))
    base_dir.mkdir(parents=True, exist_ok=True)

    def _safe_filename(s: str) -> str:
        s = (s or "").strip()
        s = re.sub(r"[^\w\s.-]", "_", s, flags=re.UNICODE)
        s = re.sub(r"\s+", "_", s)
        return s or "file"

    def _display_name_local(a: Applicant) -> str:
        ln = (getattr(a, "ho_dem", "") or "").strip()
        fn = (getattr(a, "ten", "") or "").strip()
        if ln or fn:
            return f"{ln} {fn}".strip()
        return (getattr(a, "ho_ten", "") or "").strip()

    name_safe = _safe_filename(_display_name_local(a))
    mcode = (a.ma_ho_so or a.ma_so_hv or "").strip()
    mcode_safe = _safe_filename(mcode) if mcode else "NA"

    ts = _now_vn().strftime("%Y%m%d_%H%M%S")
    size_tag = "A5" if a5 else "A4"
    fname = f"bien_nhan_{size_tag}_{mcode_safe}_{name_safe}_{ts}.pdf"

    fpath = base_dir / fname
    with open(fpath, "wb") as f:
        f.write(data)
    return str(fpath.resolve())