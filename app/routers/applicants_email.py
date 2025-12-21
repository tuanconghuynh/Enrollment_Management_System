# app/routers/applicants_email.py
from __future__ import annotations
from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Body, Query, Request
import json
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import SessionLocal, get_db
from app.core.config import settings
from app.services.sendmail_service import send_html_email, render_email
from app.services import pdf_service
from app.models.applicant import Applicant, ApplicantDoc
from app.models.checklist import ChecklistItem
from app.models.email_log import EmailLog
from typing import List, Dict, Any
from sqlalchemy import select
from types import SimpleNamespace
from app.services.audit import write_audit
from app.services.pdf_service import render_postal_pdf
from pathlib import Path


router = APIRouter(prefix="/applicants", tags=["applicants-email"])


# ---------- Helper ----------
def _load_items_docs(db: Session, a: Applicant):
    """
    Trả về: (items_checklist, docs_ctx_list)
    docs_ctx_list: list[{'code','name','received','so_luong','received_at','note'}]
    """
    items = []
    if getattr(a, "checklist_version_id", None):
        items = (
            db.query(ChecklistItem)
            .filter(ChecklistItem.version_id == a.checklist_version_id)
            .order_by(ChecklistItem.id.asc())
            .all()
        )

    # Ưu tiên bảng ApplicantDoc
    docs_db = (
        db.query(ApplicantDoc)
        .filter(ApplicantDoc.applicant_ma_so_hv == a.ma_so_hv)
        .all()
    )
    if docs_db:
        docs_ctx = []
        for x in docs_db:
            qty = getattr(x, "so_luong", 0) or 0
            try:
                qty = int(qty)
            except Exception:
                qty = 0
            docs_ctx.append({
                "code": getattr(x, "code", None),
                "name": getattr(x, "name", None) or getattr(x, "code", None),
                "so_luong": qty,
                "received": qty > 0 if getattr(x, "received", None) is None else bool(getattr(x, "received")),
                "received_at": getattr(x, "received_at", None),
                "note": getattr(x, "note", None),
            })
        return items, docs_ctx

    # Rơi về JSON
    return items, build_docs_from_json(a)

def _ensure_to_email(a: Applicant) -> str:
    to_email = getattr(a, "email_hoc_vien", None) or getattr(a, "email", None)
    if not to_email:
        raise HTTPException(status_code=400, detail="Applicant has no email")
    return to_email

def build_docs_from_json(ap: "Applicant") -> List[Dict[str, Any]]:
    raw = getattr(ap, "docs_json", None)
    if not raw:
        return []
    import json
    docs = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
    out: List[Dict[str, Any]] = []
    for d in docs:
        qty = d.get("so_luong")
        if qty is None:
            # nếu không có so_luong: đã nhận -> 1, chưa nhận -> 0
            qty = 1 if d.get("received") else 0
        try:
            qty = int(qty)
        except Exception:
            qty = 0
        out.append({
            "code": d.get("code"),
            "name": d.get("name") or d.get("code"),
            "so_luong": qty,
            "received": bool(d.get("received")) if d.get("received") is not None else (qty > 0),
            "received_at": d.get("received_at"),
            "note": d.get("note"),
        })
    return out

def _normalize_docs_for_pdf(docs):
    """
    Trả về list object có thuộc tính .code, .so_luong (int)
    docs có thể là list[ApplicantDoc ORM] hoặc list[dict] từ JSON
    """
    out = []
    for d in docs or []:
        if isinstance(d, dict):
            code = d.get("code") or d.get("name") or ""
            qty  = d.get("so_luong")
            if qty is None:
                # nếu không có so_luong trong JSON, suy luận: nhận rồi -> 1, chưa nhận -> 0
                qty = 1 if d.get("received") else 0
            try:
                qty = int(qty)
            except Exception:
                qty = 0
            out.append(SimpleNamespace(code=code, so_luong=qty))
        else:
            # ORM ApplicantDoc: ưu tiên .code; fallback các tên cột khác nếu có
            code = getattr(d, "code", None) or getattr(d, "ten_giay_to", "") or ""
            qty  = getattr(d, "so_luong", 0) or 0
            try:
                qty = int(qty)
            except Exception:
                qty = 0
            out.append(SimpleNamespace(code=code, so_luong=qty))
    return out

# ====== NEW: merge items + docs for email view ======
def _merge_items_with_docs_for_email(items, docs_ctx):
    """
    Trả về list dict cho email:
    [{'code','name','so_luong','received'}]
    - 'name' ưu tiên từ checklist; nếu không có => tra bảng map; cuối cùng mới dùng code.
    """

    # Fallback map cho các mã phổ biến
    VN_LABELS = {
        "so_yeu_ly_lich": "Sơ yếu lý lịch",
        "bang_tot_nghiep_thpt": "Bằng tốt nghiệp THPT (hoặc tương đương)",
        "hoc_ba_thpt": "Học bạ THPT (hoặc Bảng điểm THPT)",
        "bang_tot_nghiep_dai_hoc": "Bằng tốt nghiệp Đại học",
        "bang_diem_dai_hoc": "Bảng điểm toàn khoá học Đại học",
        "bang_tot_nghiep_cao_dang": "Bằng tốt nghiệp Cao đẳng",
        "bang_diem_cao_dang": "Bảng điểm toàn khóa học Cao đẳng",
        "bang_tot_nghiep_trung_cap": "Bằng tốt nghiệp Trung Cấp",
        "bang_diem_trung_cap": "Bảng điểm toàn khóa Trung Cấp",
        "can_cuoc_cong_dan": "Căn cước công dân",
        "anh_3x4": "Ảnh 3x4",
        "giay_kham_suc_khoe": "Giấy Khám sức khỏe",
        "don_mien_giam": "Đơn miễn giảm",
    }

    def keyify(v: str) -> str:
        return (v or "").strip().lower()

    def pretty_name_from_item(it) -> str:
        # thử hết các khả năng có thể tồn tại trong ChecklistItem
        for attr in (
            "display_name", "label", "vi_name", "vi_label",
            "ten_giay_to", "ten", "title", "name",
        ):
            val = getattr(it, attr, None)
            if val:
                return str(val)
        code = getattr(it, "code", None) or getattr(it, "ma", None) or ""
        # tra mapping code -> tên đẹp
        return VN_LABELS.get(keyify(code), code)

    # Map docs by code (lowercase)
    doc_by_code = { keyify(d.get("code") or d.get("name")): d for d in (docs_ctx or []) }

    merged = []
    for it in (items or []):
        code = getattr(it, "code", None) or getattr(it, "ma", None) or ""
        name = pretty_name_from_item(it)
        d = doc_by_code.get(keyify(code)) or {}
        qty = d.get("so_luong", 0) if isinstance(d, dict) else 0
        try:
            qty = int(qty)
        except Exception:
            qty = 0
        merged.append({
            "code": code,
            "name": name,          # ← luôn là tên đẹp
            "so_luong": qty,
            "received": (qty > 0),
        })

    # Thêm mục phát sinh ngoài checklist (nếu có)
    for d in (docs_ctx or []):
        k = keyify(d.get("code") or d.get("name"))
        if not any(keyify(x["code"]) == k for x in merged):
            qty = d.get("so_luong", 0)
            try:
                qty = int(qty)
            except Exception:
                qty = 0
            merged.append({
                "code": d.get("code") or d.get("name") or "",
                "name": d.get("name") or VN_LABELS.get(k, d.get("code") or ""),
                "so_luong": qty,
                "received": (qty > 0),
            })

    return merged

# ---------- Template router ----------
@router.get("/{ma_so_hv}/email-draft")
def get_email_draft(
    ma_so_hv: str,
    db: Session = Depends(get_db),
    tpl: str = Query("confirmation"),
):
    a = db.query(Applicant).filter(Applicant.ma_so_hv == ma_so_hv).first()
    if not a:
        raise HTTPException(404, "Applicant not found")

    to_email = _ensure_to_email(a)
    items, docs_ctx = _load_items_docs(db, a)
    docs_email = _merge_items_with_docs_for_email(items, docs_ctx)
    missing_list = [d["name"] for d in docs_email if int(d.get("so_luong") or 0) <= 0]
    has_missing = bool(missing_list)

    if tpl == "student_card":
        subject = "[V-HTPTĐT] THÔNG BÁO PHÁT HÀNH THẺ SINH VIÊN"
        html_body = render_email(
            "email/student_card_email.html",
            {
                "applicant": {
                    "full_name": a.full_name,
                    "ma_so_hv": a.ma_so_hv,
                    "ngay_sinh": a.ngay_sinh.strftime("%d/%m/%Y") if a.ngay_sinh else "",
                    "nganh": getattr(a, "nganh_nhap_hoc", None) or getattr(a, "nganh", None),
                },
                "org_name": "Viện Hợp tác và Phát triển Đào tạo",
                "docs": docs_email,  # không dùng nhưng để sẵn cho đồng nhất
                
            },
        )
        attach_path = None
    else:
        subject = "[V-HTPTĐT] BIÊN NHẬN HỒ SƠ NHẬP HỌC"
        html_body = render_email(
            "email/confirmation.html",
            {
                "applicant": {
                    "full_name": a.full_name,
                    "ma_ho_so": a.ma_ho_so or a.ma_so_hv,
                    "ma_so_hv": a.ma_so_hv,
                    "ngay_sinh": a.ngay_sinh.strftime("%d/%m/%Y") if a.ngay_sinh else "",
                    "nganh": getattr(a, "nganh_nhap_hoc", None) or getattr(a, "nganh", None),
                },
                "org_name": "Viện Hợp tác và Phát triển Đào tạo",
                "docs": docs_email,   # để render HTML cho học viên thấy
                "has_missing": has_missing,        # <<< THÊM
                "missing_list": missing_list,      # <<< THÊM
            },
        )
        # Chuẩn hoá dữ liệu docs để PDF đọc theo thuộc tính .code/.so_luong
        docs_for_pdf = _normalize_docs_for_pdf(docs_email)

        pdf_bytes = pdf_service.render_student_receipt_pdf_a5(a, docs_for_pdf)

        # tạo file lưu A5
        file_name = f"{a.ma_so_hv}_bien_nhan_A5.pdf"
        pdf_path = Path(settings.RECEIPTS_DIR) / file_name


        with open(pdf_path, "wb") as f:
            f.write(pdf_bytes)

        attach_path = str(pdf_path)

    return {
        "to_email": to_email,
        "subject": subject,
        "html_body": html_body,
        "attachment_url": attach_path,
        "template": tpl,
    }

# ---------- Send mail ----------
@router.post("/{ma_so_hv}/send-email")
def send_email_generic(
    ma_so_hv: str,
    bg: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
    tpl: str = Query("confirmation"),
    subject: str | None = Body(None),
    html_body: str | None = Body(None),
    attach_receipt: bool = Body(False),
):
    a = db.query(Applicant).filter(Applicant.ma_so_hv == ma_so_hv).first()
    if not a:
        raise HTTPException(404, "Applicant not found")

    to_email = _ensure_to_email(a)
    items, docs_ctx = _load_items_docs(db, a)
    docs_email = _merge_items_with_docs_for_email(items, docs_ctx)
    att_paths: List[str] = []
    missing_list = [d["name"] for d in docs_email if int(d.get("so_luong") or 0) <= 0]
    has_missing = bool(missing_list)

    if tpl == "confirmation" and attach_receipt:
        docs_for_pdf = _normalize_docs_for_pdf(docs_ctx)

        # force A5 output
        pdf_bytes = pdf_service.render_student_receipt_pdf_a5(a, docs_for_pdf)

        file_name = f"{a.ma_so_hv}_bien_nhan_A5.pdf"
        pdf_path = Path(settings.RECEIPTS_DIR) / file_name

        with open(pdf_path, "wb") as f:
            f.write(pdf_bytes)

        att_paths.append(str(pdf_path))

    subj = subject or ("[V-HTPTĐT] BIÊN NHẬN HỒ SƠ NHẬP HỌC" if tpl == "confirmation"
                       else "[V-HTPTĐT] THÔNG BÁO THẺ SINH VIÊN")

    html = html_body or render_email(
        f"email/{tpl}.html",
        {
            "applicant": {
                "full_name": a.full_name,
                "ma_ho_so": a.ma_ho_so or a.ma_so_hv,
                "ma_so_hv": a.ma_so_hv,
                "ngay_sinh": a.ngay_sinh.strftime("%d/%m/%Y") if a.ngay_sinh else "",
                "nganh": getattr(a, "nganh_nhap_hoc", None) or getattr(a, "nganh", None),
            },
            "org_name": "Viện Hợp tác và Phát triển Đào tạo",
            "docs": docs_email,
            "has_missing": has_missing,
            "missing_list": missing_list,
        },
    )

    async def _task(ma_so_hv, to_email, subj, html, att_paths):
        session = SessionLocal()
        ok, err = True, None
        try:
            try:
                await send_html_email(
                    subject=subj,
                    recipients=[to_email],
                    html_body=html,
                    attachments=att_paths or None,
                )
            except Exception as e:
                ok, err = False, str(e)
            session.add(EmailLog(
                applicant_ma_so_hv=ma_so_hv,
                applicant_ma_ho_so=getattr(a, "ma_ho_so", None),
                to_email=to_email or "",
                subject=subj,
                success=ok,
                error_message=err,
            ))
            session.commit()
        except SQLAlchemyError:
            session.rollback()
        finally:
            session.close()

    bg.add_task(_task, a.ma_so_hv, to_email, subj, html, att_paths)

    # Cập nhật trạng thái hồ sơ
    a.status = "emailed"  # hoặc "email_sent" tuỳ anh đặt
    try:
        # 👇 Ghi log vào bảng AuditLog để hiện lên trang Nhật ký
        write_audit(
            db,
            action="EMAIL_SENT",
            target_type="Applicant",
            target_id=a.ma_so_hv,   # 👈 MSSV vào đây
            prev_values=None,
            new_values={
                "template": tpl,
                "attach_receipt": attach_receipt,
                "to_email": to_email,
                "subject": subj,
            },
            status="SUCCESS",
            request=request,
        )
        db.commit()
    except Exception:
        db.rollback()
        # không raise để không làm hỏng flow gửi mail, chỉ mất log thôi

    return {
        "ok": True,
        "ma_so_hv": a.ma_so_hv,
        "template": tpl,
        "status": a.status,
    }

# ---------- Batch ----------
@router.post("/send-email-batch")
def send_email_batch(
    bg: BackgroundTasks,
    db: Session = Depends(get_db),
    tpl: str = Query("confirmation"),
    payload: dict = Body(...),
):
    ids = list(map(str, payload.get("ma_so_hv_list") or []))
    if not ids:
        raise HTTPException(400, "ma_so_hv_list is empty")

    async def _task_batch(ids: list[str], tpl: str):
        session = SessionLocal()
        try:
            for mshv in ids:
                a = session.query(Applicant).filter(Applicant.ma_so_hv == mshv).first()
                if not a:
                    continue
                to_email = _ensure_to_email(a)
                items, docs_ctx = _load_items_docs(session, a)
                docs_email = _merge_items_with_docs_for_email(items, docs_ctx)
                missing_list = [d["name"] for d in docs_email if int(d.get("so_luong") or 0) <= 0]
                has_missing = bool(missing_list)

                subj = ("[V-HTPTĐT] BIÊN NHẬN HỒ SƠ NHẬP HỌC"
                        if tpl == "confirmation" else "[V-HTPTĐT] THẺ SINH VIÊN")

                html = render_email(
                    f"email/{tpl}.html",
                    {
                        "applicant": {
                            "full_name": a.full_name,
                            "ma_ho_so": a.ma_ho_so or a.ma_so_hv,
                            "ma_so_hv": a.ma_so_hv,
                            "ngay_sinh": a.ngay_sinh.strftime("%d/%m/%Y") if a.ngay_sinh else "",
                            "nganh": getattr(a, "nganh_nhap_hoc", None) or getattr(a, "nganh", None),
                        },
                        "org_name": "Viện Hợp tác và Phát triển Đào tạo",
                        "docs": docs_email,
                        "has_missing": has_missing,
                        "missing_list": missing_list,
                    },
                )
                await send_html_email(subject=subj, recipients=[to_email], html_body=html)
                session.add(EmailLog(
                    applicant_ma_so_hv=a.ma_so_hv,
                    applicant_ma_ho_so=a.ma_ho_so,
                    to_email=to_email or "",
                    subject=subj,
                    success=True,
                ))

                # 🔵 THÊM: log vào AuditLog cho từng MSSV
                write_audit(
                    session,
                    action="EMAIL_SENT",
                    target_type="Applicant",
                    target_id=a.ma_so_hv,
                    prev_values=None,
                    new_values={
                        "template": tpl,
                        "to_email": to_email,
                        "subject": subj,
                        "batch": True,
                    },
                    status="SUCCESS",
                    request=None,    # background task, không có request
                )

                a.status = "emailed"
                session.add(a)

                session.commit()
        finally:
            session.close()

    bg.add_task(_task_batch, ids, tpl)
    return {"ok": True, "count": len(ids), "template": tpl}
