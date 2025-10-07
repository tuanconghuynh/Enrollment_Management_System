# app/services/pdf_service.py
from datetime import datetime, date
import io, os
from typing import List, Dict

from reportlab.lib.pagesizes import A4, A5, landscape # ⬅️ thêm A5
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import Table, TableStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader, PdfWriter, Transformation


from ..core.config import settings
from ..models.applicant import Applicant, ApplicantDoc
from ..models.checklist import ChecklistItem

# Kích thước chữ theo yêu cầu
TITLE_SIZE = 13
TEXT_SIZE  = 12

# Lề trang
LM, RM, TM, BM = 25*mm, 25*mm, 25*mm, 25*mm

# Dãn dòng (tăng +0.5 mm)
PARA_LEADING = 6.7 * mm   # trước ~6.2mm
KV_STEP      = 7.5 * mm   # trước 7mm

# Font thực dùng (được gán sau khi đăng ký)
FONT_REG  = "Times-Roman"
FONT_BOLD = "Times-Bold"


def _first_existing(paths):
    for p in paths:
        if not p:
            continue
        p = os.path.abspath(str(p).strip().strip('"').strip("'"))
        if os.path.exists(p):
            return p
    return None


def _register_font_times():
    """
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
    from reportlab.pdfbase.pdfmetrics import stringWidth
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


def _draw_kv(c: rl_canvas.Canvas, x_label, x_val, y, label, value, step=KV_STEP):
    c.setFont(FONT_REG, TEXT_SIZE);  c.drawString(x_label, y, label)
    c.setFont(FONT_BOLD, TEXT_SIZE); c.drawString(x_val,   y, value or "")
    return y - step


def _build_checklist_rows(items: List[ChecklistItem], docs: List[ApplicantDoc]):
    doc_map = {d.code: d.so_luong for d in docs}
    rows = [["Danh mục", "Số lượng"]]
    for it in items:
        qty = int(doc_map.get(it.code, 0) or 0)
        rows.append([it.display_name, "" if qty == 0 else str(qty)])  # ⬅️ 0 -> để trống
    return rows


def _draw_checklist_table(c: rl_canvas.Canvas, x, y, w, rows):
    """Bảng danh mục: ẩn kẻ header nhẹ, padding thoáng."""
    table = Table(rows, colWidths=[w*0.78, w*0.22])
    table.setStyle(TableStyle([
        ("FONTNAME",   (0,0), (-1,-1), FONT_REG),
        ("FONTNAME",   (0,0), (-1,0),  FONT_BOLD),
        ("FONTSIZE",   (0,0), (-1,-1), TEXT_SIZE),
        ("ALIGN",      (0,0), (-1,0),  "CENTER"),   # căn giữa header
        ("ALIGN",      (1,1), (1,-1),  "CENTER"),   # căn giữa cột số lượng
        ("GRID",       (0,0), (-1,-1), 0.5, colors.black),
        ("TOPPADDING",    (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ]))
    table.wrapOn(c, 0, 0)
    table.drawOn(c, x, y - table._height)
    return y - table._height


# Chuẩn hóa mọi kiểu ngày về dd/mm/yyyy
def _fmt_dmy(v) -> str:
    if not v:
        return ""
    if isinstance(v, (datetime, date)):
        return v.strftime("%d/%m/%Y")
    s = str(v).strip()
    # thử các định dạng hay gặp
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.strftime("%d/%m/%Y")
        except ValueError:
            pass
    # ISO 8601 (có thể kèm giờ)
    try:
        dt = datetime.fromisoformat(s)
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return s  # không parse được thì trả nguyên văn


def _header_block(c: rl_canvas.Canvas, W, H, khoa: str, ma_hs: str, ngay_nhan):
    c.setFont(FONT_BOLD, TITLE_SIZE)
    title = "BIÊN NHẬN HỒ SƠ NHẬP HỌC CHƯƠNG TRÌNH ĐÀO TẠO TỪ XA"
    if (khoa or "").strip():
        title += f" KHÓA {khoa.strip()}"
    c.drawCentredString(W/2, H - TM, title)

    c.setFont(FONT_BOLD, TEXT_SIZE)
    c.drawRightString(W - RM, H - TM - 10*mm, f"Mã HS: {ma_hs or ''}")
    c.drawRightString(W - RM, H - TM - 18*mm, f"Ngày nhận HS: {_fmt_dmy(ngay_nhan)}")

    intro = "Viện Hợp tác và Phát triển Đào tạo xác nhận đã nhận hồ sơ nhập học"
    intro += f" khóa {khoa.strip()} của Anh/Chị:" if (khoa or "").strip() else " của Anh/Chị:"

    text_w = W - LM - RM
    c.setFont(FONT_REG, TEXT_SIZE)
    y = H - TM - 26*mm
    for line in _wrap_lines(intro, FONT_REG, TEXT_SIZE, text_w):
        c.drawString(LM, y, line)
        y -= PARA_LEADING
    return y


def _draw_signature_block(c: rl_canvas.Canvas, y, W, receiver_name: str):
    """
    Bảng 2 cột × 2 hàng, cột 2 căn giữa, ẩn toàn bộ nét kẻ:
      [("", "Người nhận"),
       ("", receiver_name)]
    """
    table_w = W - LM - RM
    data = [
        ["", "Người nhận"],
        ["", receiver_name or ""],
    ]
    col_widths = [table_w * 0.5, table_w * 0.5]
    row_heights = [12*mm, 28*mm]  # chừa chỗ ký tên

    t = Table(data, colWidths=col_widths, rowHeights=row_heights)
    t.setStyle(TableStyle([
        ("FONTNAME", (1,0), (1,0), FONT_REG),
        ("FONTNAME", (1,1), (1,1), FONT_BOLD),
        ("FONTSIZE", (0,0), (-1,-1), TEXT_SIZE),
        ("ALIGN",    (1,0), (1,1), "CENTER"),
        ("VALIGN",   (0,0), (-1,-1), "MIDDLE"),
        # Ẩn toàn bộ đường kẻ
        ("LINEBEFORE", (0,0), (-1,-1), 0, colors.white),
        ("LINEAFTER",  (0,0), (-1,-1), 0, colors.white),
        ("LINEABOVE",  (0,0), (-1,-1), 0, colors.white),
        ("LINEBELOW",  (0,0), (-1,-1), 0, colors.white),
        ("INNERGRID",  (0,0), (-1,-1), 0, colors.white),
        ("TOPPADDING",    (0,0), (-1,-1), 2),
        ("BOTTOMPADDING", (0,0), (-1,-1), 2),
    ]))
    t.wrapOn(c, 0, 0)
    y = max(BM + 42*mm, y)  # đảm bảo không đụng lề dưới
    t.drawOn(c, LM, y - sum(row_heights))
    return y - sum(row_heights)


# ========== A4 (giữ nguyên, chỉ sửa chỗ truyền ngày) ==========
def render_single_pdf(a: Applicant, items: List[ChecklistItem], docs: List[ApplicantDoc]) -> bytes:
    _register_font_times()
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)
    W, H = A4

    # Header + intro
    y = _header_block(
        c, W, H,
        getattr(a, "khoa", "") or "",
        a.ma_ho_so,
        a.ngay_nhan_hs   # ⬅️ truyền object, để _fmt_dmy xử lý
    )

    # Khối thông tin 2 cột
    left_lbl, left_val   = LM,          LM + 35*mm
    right_lbl, right_val = LM + 95*mm,  LM + 125*mm

    y_l = _draw_kv(c, left_lbl, left_val, y, "Họ và tên:", a.ho_ten or "")
    y_r = _draw_kv(c, right_lbl, right_val, y, "Ngày sinh:", _fmt_dmy(a.ngay_sinh))
    y   = min(y_l, y_r)

    y_l = _draw_kv(c, left_lbl, left_val, y, "Mã số HV:", a.ma_so_hv or "")
    y_r = _draw_kv(c, right_lbl, right_val, y, "Số ĐT:",   a.so_dt or "")
    y   = min(y_l, y_r)

    # ✨ Thêm dòng Email HV:
    y_l = _draw_kv(c, left_lbl, left_val, y, "Email HV:", getattr(a, "email_hoc_vien", "") or "")
    # giữ nguyên dòng bên phải:
    y_r = _draw_kv(c, right_lbl, right_val, y, "Đợt:", a.dot or "")
    y   = min(y_l, y_r)

    y = _draw_kv(c, left_lbl, left_val, y, "Ngành nhập học:", a.nganh_nhap_hoc or "")

    y = _draw_kv(c, left_lbl, left_val, y, "Đã TN:", a.da_tn_truoc_do or "")

    # Bảng hồ sơ gồm
    c.setFont(FONT_BOLD, TEXT_SIZE); c.drawString(LM, y, "Hồ sơ gồm")
    y -= 6*mm
    rows = _build_checklist_rows(items, docs)
    y = _draw_checklist_table(c, LM, y, W - LM - RM, rows)

    # Ghi chú: cách bảng 10mm
    y -= 10*mm
    c.setFont(FONT_REG, TEXT_SIZE);  c.drawString(LM, y, "Ghi chú:")
    c.setFont(FONT_BOLD, TEXT_SIZE); c.drawString(LM + 22*mm, y, a.ghi_chu or "")

    # Chữ ký: bảng 2×2 ẩn kẻ, cột 2 căn giữa
    y -= 5*mm
    _draw_signature_block(c, y, W, a.nguoi_nhan_ky_ten or "")

    c.showPage(); c.save()
    return buf.getvalue()


def render_batch_pdf(
    apps: List[Applicant],
    items_by_version: Dict[int, List[ChecklistItem]],
    docs_by_app: Dict[str, List[ApplicantDoc]],   # <-- key = MSSV
):
    _register_font_times()
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)
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

        left_lbl, left_val   = LM,         LM + 35*mm
        right_lbl, right_val = LM + 95*mm, LM + 125*mm

        y_l = _draw_kv(c, left_lbl, left_val, y, "Họ và tên:", a.ho_ten or "")
        y_r = _draw_kv(c, right_lbl, right_val, y, "Ngày sinh:", _fmt_dmy(a.ngay_sinh))
        y   = min(y_l, y_r)

        y_l = _draw_kv(c, left_lbl, left_val, y, "Mã số HV:", a.ma_so_hv or "")
        y_r = _draw_kv(c, right_lbl, right_val, y, "Số ĐT:",   a.so_dt or "")
        y   = min(y_l, y_r)

        y_l = _draw_kv(c, left_lbl, left_val, y, "Ngành nhập học:", a.nganh_nhap_hoc or "")
        y_r = _draw_kv(c, right_lbl, right_val, y, "Đợt:",           a.dot or "")
        y   = min(y_l, y_r)

        y = _draw_kv(c, left_lbl, left_val, y, "Đã TN:", a.da_tn_truoc_do or "")

        c.setFont(FONT_BOLD, TEXT_SIZE); c.drawString(LM, y, "Hồ sơ gồm")
        y -= 6*mm
        rows = _build_checklist_rows(items, docs)
        y = _draw_checklist_table(c, LM, y, W - LM - RM, rows)

        y -= 10*mm
        c.setFont(FONT_REG, TEXT_SIZE);  c.drawString(LM, y, "Ghi chú:")
        c.setFont(FONT_BOLD, TEXT_SIZE); c.drawString(LM + 22*mm, y, a.ghi_chu or "")

        # Chữ ký: bảng 2×2 ẩn kẻ, cột 2 căn giữa
        y -= 5*mm
        _draw_signature_block(c, y, W, a.nguoi_nhan_ky_ten or "")

        c.showPage()

    c.save()
    return buf.getvalue()


# ================== BẢN IN A5 TỐI GIẢN (cho học viên) ==================

def _build_rows_nonzero(items: List[ChecklistItem], docs: List[ApplicantDoc]):
    """Chỉ lấy mục có số lượng > 0 để bản A5 gọn."""
    doc_map = {d.code: int(d.so_luong or 0) for d in docs}
    rows = [["Danh mục", "Số lượng"]]
    for it in items:
        n = int(doc_map.get(it.code, 0))
        if n > 0:
            rows.append([it.display_name, str(n)])
    if len(rows) == 1:
        rows.append(["(Chưa nộp hồ sơ!)", ""])
    return rows


def render_single_pdf_a5(a: Applicant, items: List[ChecklistItem], docs: List[ApplicantDoc]) -> bytes:
    """
    A5 ngang, lề sát, intro sát tiêu đề để kéo toàn trang lên trên.
    """
    _register_font_times()
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=landscape(A5))
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

    # ===== Bảng giấy tờ đã nộp (SL > 0) =====
    # c.setFont(FONT_BOLD, text_sz); c.drawString(lm, y, "Giấy tờ đã nộp")
    # y -= 3*mm

    rows = _build_rows_nonzero(items, docs)
    table_w = W - lm - rm
    table = Table(rows, colWidths=[table_w*0.78, table_w*0.22])
    table.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,-1), FONT_REG),
        ("FONTNAME", (0,0), (-1,0),  FONT_BOLD),
        ("FONTSIZE", (0,0), (-1,-1), text_sz),
        ("ALIGN",    (0,0), (-1,0),  "CENTER"),
        ("ALIGN",    (1,1), (1,-1),  "CENTER"),
        ("GRID",     (0,0), (-1,-1), 0.4, colors.black),
        ("TOPPADDING",(0,0),(-1,-1), 2),
        ("BOTTOMPADDING",(0,0),(-1,-1), 1),
        ("LEFTPADDING",(0,0),(-1,-1), 3),
        ("RIGHTPADDING",(0,0),(-1,-1), 3),
    ]))
    table.wrapOn(c, 0, 0)
    tbl_h = table._height

    # ===== Tính không gian còn lại để không chồng =====
    note_h = 7*mm if a.ghi_chu else 0
    extra_note_gap = 1.0*mm if a.ghi_chu else 0  # <-- thêm 0.5mm giữa bảng và Ghi chú

    sign_h_full = 10*mm + 26*mm
    sign_h_min  = 10*mm + 22*mm
    safety = 1.5*mm
    gap_after_table = 4*mm
    gap_min = 2*mm

    y0 = y
    # tính nhu cầu từ đáy trang (có + extra_note_gap)
    need_from_bottom = tbl_h + gap_after_table + extra_note_gap + note_h + sign_h_full + safety
    if bm + need_from_bottom <= y0:
        y_tbl_top = y0
        sign_h = sign_h_full
    else:
        spare = (y0 - bm) - (tbl_h + note_h + extra_note_gap + sign_h_full + safety)
        gap_after_table = max(gap_min, spare)
        sign_h = sign_h_full
        if gap_after_table == gap_min:
            need2 = tbl_h + gap_after_table + extra_note_gap + note_h + sign_h_min + safety
            if bm + need2 > y0:
                sign_h = sign_h_min
        y_tbl_top = y0

    # Vẽ bảng
    table.drawOn(c, lm, y_tbl_top - tbl_h)
    # sau bảng lùi xuống: gap_after_table + 0.5mm (nếu có ghi chú)
    y = y_tbl_top - tbl_h - (gap_after_table + extra_note_gap)

    # ===== Ghi chú (ngay dưới bảng) =====
    if a.ghi_chu:
        c.setFont(FONT_REG, text_sz);  c.drawString(lm, y, "Ghi chú:")
        c.setFont(FONT_BOLD, text_sz); c.drawString(lm + 15*mm, y, a.ghi_chu)
        y -= 9*mm


    # ===== Chữ ký (sát lề dưới), Người nộp = tên học viên =====
    bm = 8*mm        # lề dưới mỏng
    safety = 0.8*mm  # chừa 1 chút để không “ăn mép”

    content_w = W - lm - rm
    sign_w = content_w / 2.0          # mỗi cột ~1/2 bề ngang
    total_w = sign_w * 2               # block 2 cột
    x_right = W - rm - total_w         # neo sát lề phải  ⟵ quan trọng

    data = [["Người nộp", "Người nhận"],
            [a.ho_ten or "", a.nguoi_nhan_ky_ten or ""]]

    t = Table(data, colWidths=[sign_w, sign_w],
            rowHeights=[10*mm, sign_h - 10*mm])
    t.setStyle(TableStyle([
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

    t.wrapOn(c, 0, 0)
    y_sig_top = bm + sign_h + safety
    y = max(y, y_sig_top)
    t.drawOn(c, x_right, y - sign_h)   # vẽ sát lề phải

    c.showPage(); c.save()
    return buf.getvalue()

# ================== HẾT BẢN IN A5 ==================

def a5_two_up_to_a4(a5_pdf_bytes: bytes, margin_pt: int = 8, gap_pt: int = 8, duplicate_if_needed: bool = True) -> bytes:
    """
    Ghép các trang A5 (dọc/ ngang) thành A4 *dọc*, 2-up (một trên, một dưới).
    - Scale theo *chiều cao nửa A4* để bản in đủ khổ.
    - Nếu chỉ có 1 trang A5 -> nhân đôi trang đó (2 bản giống nhau).
    - Nếu số trang A5 lẻ -> nhân bản trang cuối để đủ cặp.
    """
    reader = PdfReader(io.BytesIO(a5_pdf_bytes))
    src_pages = list(reader.pages)

    if duplicate_if_needed:
        if len(src_pages) == 1:
            src_pages = [src_pages[0], src_pages[0]]
        elif len(src_pages) % 2 == 1:
            src_pages.append(src_pages[-1])

    out = PdfWriter()
    a4w, a4h = A4
    half_h = (a4h - 2*margin_pt - gap_pt) / 2.0  # vùng vẽ mỗi nửa A4

    page = None
    for i, src in enumerate(src_pages):
        sw = float(src.mediabox.width)
        sh = float(src.mediabox.height)

        # scale theo chiều cao nửa A4
        scale = half_h / sh
        placed_w = sw * scale
        placed_h = sh * scale

        # canh giữa theo ngang
        x = (a4w - placed_w) / 2.0

        # mỗi 2 A5 -> 1 A4 dọc
        if i % 2 == 0:
            page = out.add_blank_page(width=a4w, height=a4h)
            y = a4h - margin_pt - placed_h      # nửa trên
        else:
            y = margin_pt                        # nửa dưới

        t = Transformation().scale(scale).translate(x/scale, y/scale)
        page.merge_transformed_page(src, t)

    buf = io.BytesIO()
    out.write(buf)
    return buf.getvalue()
