# app/services/pdf_service.py
from datetime import datetime, date
import io, os
from typing import List, Dict

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
    if not d:
        d = datetime.today()
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


# ================== A4: 1 hồ sơ ==================
def render_single_pdf(a: Applicant, items: List[ChecklistItem], docs: List[ApplicantDoc]) -> bytes:
    _register_font_times()
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"Bản in A4 - {a.ho_ten}")
    W, H = A4

    # Header + intro
    y = _header_block(
        c, W, H,
        getattr(a, "khoa", "") or "",
        a.ma_ho_so,
        a.ngay_nhan_hs
    )

    # 2 cột thông tin (bám sát dấu :)
    left_lbl, left_val   = LM,          LM + 26*mm
    right_lbl, right_val = LM + 85*mm,  LM + 110*mm   

    # Hàng 1
    y_l = _draw_kv(c, left_lbl,  left_val,  y, "Họ và tên:",      a.ho_ten or "")
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

    # Khoảng trắng cứng sau bảng
    y -= 10*mm

    # Ghi chú (wrap)
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

    # Chữ ký
    sig_top = y_note - 4*mm
    _draw_signature_block(c, sig_top, W, a.nguoi_nhan_ky_ten or "")

    c.showPage(); c.save()
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
        y_l = _draw_kv(c, left_lbl,  left_val,  y, "Họ và tên:",      a.ho_ten or "")
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
        c.setFont(FONT_BOLD, TEXT_SIZE); c.drawString(LM, y, "Hồ sơ gồm")
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

# ================== (đã thêm cột STT) ==================
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
# =======================================================


def render_single_pdf_a5(a: Applicant, items: List[ChecklistItem], docs: List[ApplicantDoc]) -> bytes:
    """
    A5 ngang, lề sát, intro sát tiêu đề để kéo toàn trang lên trên.
    """
    _register_font_times()
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=landscape(A5))
    c.setTitle(f"Bản in A5 - {a.ho_ten}")
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
    c.setFont(FONT_BOLD, text_sz); c.drawString(val_x,   y, a.ho_ten or "")
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
    # rows = _build_checklist_rows(items, docs) #Bảng đầy đủ
    table_w = W - lm - rm
    # STT ~12%, Danh mục ~66%, Số lượng ~22% (tỷ lệ gọn cho A5)
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
        _vn_date_line(getattr(a, "ngay_nhan_hs", None), "__________")
    )

    # Bảng chữ ký: Người nộp (HV) — Người nhận (NV)
    content_w = W - lm - rm
    sign_w    = content_w / 2.0
    total_w   = sign_w * 2
    x_right   = W - rm - total_w   # neo block sát lề phải

    sig = Table(
        [["Người nộp", "Người nhận"],
         [a.ho_ten or "", a.nguoi_nhan_ky_ten or ""]],
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

# ================== HẾT BẢN IN A5 ==================
