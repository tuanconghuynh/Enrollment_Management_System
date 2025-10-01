# app/routers/applicants.py
from datetime import datetime, date
import io

from fastapi import APIRouter, Depends, HTTPException, Query, status
from starlette.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..models.applicant import Applicant, ApplicantDoc
from ..models.checklist import ChecklistItem, ChecklistVersion
from ..schemas.applicant import ApplicantIn, ApplicantOut
from ..services.pdf_service import render_single_pdf, render_single_pdf_a5



router = APIRouter(prefix="/applicants", tags=["applicants"])

# ----------------- helpers -----------------
def _parse_date_ymd(v):
    """Nhận str 'YYYY-MM-DD' | datetime | date | None -> date|None"""
    if v in (None, ""):
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    # string
    return datetime.strptime(v, "%Y-%m-%d").date()

def _to_ymd(v):
    """date|datetime|str|None -> 'YYYY-MM-DD'|None"""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        v = v.date()
    if isinstance(v, date):
        return v.strftime("%Y-%m-%d")
    # assume string already ok
    return str(v)

# ----------------- FIND BY CODE (cho UI) -----------------
@router.get("/by-code/{ma_ho_so}")
def get_by_code(ma_ho_so: str, db: Session = Depends(get_db)):
    code = (ma_ho_so or "").strip()
    a = db.query(Applicant).filter(Applicant.ma_ho_so == code).first()
    if not a:
        raise HTTPException(status_code=404, detail="Not Found")

    docs = (
        db.query(ApplicantDoc)
        .filter(ApplicantDoc.applicant_id == a.id)
        .all()
    )

    applicant_payload = {
        "id": a.id,
        "ma_ho_so": a.ma_ho_so,
        "ngay_nhan_hs": _to_ymd(a.ngay_nhan_hs),
        "ho_ten": a.ho_ten,
        "ma_so_hv": a.ma_so_hv,
        "ngay_sinh": _to_ymd(a.ngay_sinh),
        "so_dt": a.so_dt,
        "nganh_nhap_hoc": a.nganh_nhap_hoc,
        "dot": a.dot,
        "khoa": getattr(a, "khoa", None),
        "da_tn_truoc_do": a.da_tn_truoc_do,
        "ghi_chu": a.ghi_chu,
        "nguoi_nhan_ky_ten": a.nguoi_nhan_ky_ten,
        "status": a.status,
        "printed": a.printed,
        "checklist_version_id": a.checklist_version_id,
    }
    return {
        "applicant": applicant_payload,
        "docs": [{"code": d.code, "so_luong": int(d.so_luong or 0)} for d in docs],
    }

# ----------------- CREATE -----------------
@router.post("", response_model=ApplicantOut, status_code=201)
@router.post("/", response_model=ApplicantOut, status_code=201)
def create_applicant(payload: ApplicantIn, db: Session = Depends(get_db)):
    v = (
        db.query(ChecklistVersion)
        .filter(ChecklistVersion.version_name == payload.checklist_version_name)
        .first()
    )
    if not v:
        raise HTTPException(400, f"Checklist version '{payload.checklist_version_name}' not found")

    if db.query(Applicant).filter(Applicant.ma_ho_so == payload.ma_ho_so).first():
        raise HTTPException(409, "Mã hồ sơ đã tồn tại")

    a = Applicant(
        ma_ho_so=payload.ma_ho_so.strip(),
        ngay_nhan_hs=_parse_date_ymd(payload.ngay_nhan_hs),
        ho_ten=payload.ho_ten,
        ma_so_hv=payload.ma_so_hv,
        ngay_sinh=_to_ymd(payload.ngay_sinh),   # bạn đang lưu string cho ngày sinh
        so_dt=payload.so_dt,
        nganh_nhap_hoc=payload.nganh_nhap_hoc,
        dot=payload.dot,
        khoa=payload.khoa,
        da_tn_truoc_do=payload.da_tn_truoc_do,
        ghi_chu=payload.ghi_chu,
        nguoi_nhan_ky_ten=payload.nguoi_nhan_ky_ten,
        checklist_version_id=v.id,
        status="saved",
        printed=False,
    )
    db.add(a)
    db.flush()  # có a.id

    # lưu docs (bỏ qua None/"", giữ 0 nếu gửi 0)
    for d in payload.docs:
        if d.so_luong in (None, ""):
            continue
        db.add(ApplicantDoc(applicant_id=a.id, code=d.code, so_luong=int(d.so_luong)))

    db.commit()
    db.refresh(a)
    return ApplicantOut(id=a.id, ma_ho_so=a.ma_ho_so, status=a.status, printed=a.printed)

# ----------------- SEARCH (cho UI) -----------------
@router.get("/search")
def search_applicants(
    q: str = Query(..., min_length=2),
    limit: int = 10,
    db: Session = Depends(get_db),
):
    like = f"%{q}%"
    rows = (
        db.query(Applicant)
        .filter((Applicant.ho_ten.ilike(like)) | (Applicant.ma_ho_so.ilike(like)))
        .order_by(Applicant.id.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": a.id,
            "ma_ho_so": a.ma_ho_so,
            "ho_ten": a.ho_ten,
            "ma_so_hv": a.ma_so_hv,
            "ngay_nhan_hs": a.ngay_nhan_hs.isoformat() if a.ngay_nhan_hs else None,
            "dot": a.dot,
        }
        for a in rows
    ]

# ----------------- FIND BY CODE (API cho hệ thống khác) -----------------
@router.get("/find")
@router.get("/find/")
def find_by_ma_ho_so(ma_ho_so: str = Query(...), db: Session = Depends(get_db)):
    code = (ma_ho_so or "").strip()
    a = db.query(Applicant).filter(Applicant.ma_ho_so == code).first()
    if not a:
        raise HTTPException(status_code=404, detail="Not Found")

    docs = db.query(ApplicantDoc).filter_by(applicant_id=a.id).all()
    q = db.query(ChecklistItem).filter(ChecklistItem.version_id == a.checklist_version_id)
    q = q.order_by(getattr(ChecklistItem, "order_no", ChecklistItem.id).asc())
    items = q.all()

    return {
        "id": a.id,
        "ma_ho_so": a.ma_ho_so,
        "ngay_nhan_hs": a.ngay_nhan_hs.isoformat() if a.ngay_nhan_hs else None,
        "ho_ten": a.ho_ten,
        "ma_so_hv": a.ma_so_hv,
        "ngay_sinh": a.ngay_sinh if isinstance(a.ngay_sinh, str)
                     else (a.ngay_sinh.isoformat() if a.ngay_sinh else None),
        "so_dt": a.so_dt,
        "nganh_nhap_hoc": a.nganh_nhap_hoc,
        "dot": a.dot,
        "khoa": getattr(a, "khoa", None),
        "da_tn_truoc_do": a.da_tn_truoc_do,
        "ghi_chu": a.ghi_chu,
        "nguoi_nhan_ky_ten": a.nguoi_nhan_ky_ten,
        "docs": [{"code": d.code, "so_luong": int(d.so_luong or 0)} for d in docs],
        "checklist_items": [
            {"code": it.code, "display_name": it.display_name, "order_no": getattr(it, "order_no", 0)}
            for it in items
        ],
    }

# --- fallback: by-code dạng path param ---
@router.get("/by-code/{ma_ho_so}")
def find_by_code_path(ma_ho_so: str, db: Session = Depends(get_db)):
    return find_by_ma_ho_so(ma_ho_so=ma_ho_so, db=db)

# ----------------- UPDATE -----------------
@router.put("/{applicant_id}")
def update_applicant(applicant_id: int, payload: ApplicantIn, db: Session = Depends(get_db)):
    a = db.query(Applicant).get(applicant_id)
    if not a:
        raise HTTPException(404, "Applicant not found")

    a.ma_ho_so        = payload.ma_ho_so.strip()
    a.ngay_nhan_hs    = _parse_date_ymd(payload.ngay_nhan_hs)
    a.ho_ten          = payload.ho_ten
    a.ma_so_hv        = payload.ma_so_hv
    a.ngay_sinh       = _to_ymd(payload.ngay_sinh)
    a.so_dt           = payload.so_dt
    a.nganh_nhap_hoc  = payload.nganh_nhap_hoc
    a.dot             = payload.dot
    a.khoa            = payload.khoa
    a.da_tn_truoc_do  = payload.da_tn_truoc_do
    a.ghi_chu         = payload.ghi_chu
    a.nguoi_nhan_ky_ten = payload.nguoi_nhan_ky_ten

    # upsert docs (None => bỏ qua, <=0 => xoá)
    existing = {d.code: d for d in db.query(ApplicantDoc).filter_by(applicant_id=a.id).all()}
    for d in payload.docs:
        if d.so_luong is None:
            continue
        if int(d.so_luong) <= 0:
            if d.code in existing:
                db.delete(existing[d.code])
        else:
            if d.code in existing:
                existing[d.code].so_luong = int(d.so_luong)
            else:
                db.add(ApplicantDoc(applicant_id=a.id, code=d.code, so_luong=int(d.so_luong)))

    db.commit()
    return {"ok": True, "id": a.id, "ma_ho_so": a.ma_ho_so}

# ----------------- DELETE -----------------
@router.delete("/{applicant_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_applicant(applicant_id: int, db: Session = Depends(get_db)):
    a = db.query(Applicant).get(applicant_id)
    if not a:
        raise HTTPException(404, "Applicant not found")
    db.query(ApplicantDoc).filter_by(applicant_id=a.id).delete(synchronize_session=False)
    db.delete(a)
    db.commit()
    return

# ----------------- PRINT ONE -----------------
def _do_print(applicant_id: int, mark_printed: bool, db: Session):
    a = db.query(Applicant).filter(Applicant.id == applicant_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Applicant not found")

    q = db.query(ChecklistItem).filter(ChecklistItem.version_id == a.checklist_version_id)
    if hasattr(ChecklistItem, "order_index"):
        q = q.order_by(getattr(ChecklistItem, "order_index").asc())
    elif hasattr(ChecklistItem, "order_no"):
        q = q.order_by(getattr(ChecklistItem, "order_no").asc())
    else:
        q = q.order_by(ChecklistItem.id.asc())
    items = q.all()

    docs = db.query(ApplicantDoc).filter(ApplicantDoc.applicant_id == a.id).all()
    pdf_bytes = render_single_pdf(a, items, docs)

    if mark_printed:
        a.printed = True
        a.status = "printed"
        a.updated_at = datetime.utcnow()
        db.commit()

    filename = f"HS_{a.ma_ho_so or applicant_id}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )

@router.get("/{applicant_id}/print")
def print_applicant_now(applicant_id: int, mark_printed: bool = Query(False), db: Session = Depends(get_db)):
    return _do_print(applicant_id, mark_printed, db)

@router.post("/{applicant_id}/print")
def print_applicant_now_post(applicant_id: int, mark_printed: bool = Query(True), db: Session = Depends(get_db)):
    return _do_print(applicant_id, mark_printed, db)

def _do_print_a5(applicant_id: int, mark_printed: bool, db: Session):
    a = db.query(Applicant).filter(Applicant.id == applicant_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Applicant not found")

    q = db.query(ChecklistItem).filter(ChecklistItem.version_id == a.checklist_version_id)
    if hasattr(ChecklistItem, "order_index"):
        q = q.order_by(getattr(ChecklistItem, "order_index").asc())
    elif hasattr(ChecklistItem, "order_no"):
        q = q.order_by(getattr(ChecklistItem, "order_no").asc())
    else:
        q = q.order_by(ChecklistItem.id.asc())
    items = q.all()

    docs = db.query(ApplicantDoc).filter(ApplicantDoc.applicant_id == a.id).all()
    pdf_bytes = render_single_pdf_a5(a, items, docs)

    if mark_printed:
        a.printed = True
        a.status = "printed"
        a.updated_at = datetime.utcnow()
        db.commit()

    filename = f"HS_{a.ma_ho_so or applicant_id}_A5.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get("/recent")
def get_recent_applicants(db: Session = Depends(get_db), limit: int = 50):
    q = db.query(Applicant).order_by(Applicant.id.desc()).limit(limit).all()
    return [
        {"id": a.id, "ma_ho_so": a.ma_ho_so, "ho_ten": a.ho_ten}
        for a in q
    ]

@router.get("/{applicant_id}/print-a5")
def print_applicant_a5(applicant_id: int, mark_printed: bool = Query(False), db: Session = Depends(get_db)):
    return _do_print_a5(applicant_id, mark_printed, db)

@router.post("/{applicant_id}/print-a5")
def print_applicant_a5_post(applicant_id: int, mark_printed: bool = Query(True), db: Session = Depends(get_db)):
    return _do_print_a5(applicant_id, mark_printed, db)