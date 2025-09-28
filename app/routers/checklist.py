# app/routers/checklist.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..models.checklist import ChecklistItem, ChecklistVersion

router = APIRouter(prefix="/checklist", tags=["checklist"])

# Danh mục mặc định theo yêu cầu (mã code khớp UI)
DEFAULT_ITEMS = [
    ("so_yeu_ly_lich", "Sơ yếu lý lịch"),
    ("bang_tot_nghiep_thpt", "Bằng tốt nghiệp THPT (hoặc tương đương)"),
    ("hoc_ba_thpt", "Học bạ THPT (hoặc Bảng điểm THPT)"),
    ("bang_tot_nghiep_dai_hoc", "Bằng tốt nghiệp Đại học"),
    ("bang_diem_dai_hoc", "Bảng điểm toàn khoá học Đại học"),
    ("bang_tot_nghiep_cao_dang", "Bằng tốt nghiệp Cao đẳng"),
    ("bang_diem_cao_dang", "Bảng điểm toàn khóa học Cao đẳng"),
    ("bang_tot_nghiep_trung_cap", "Bằng tốt nghiệp Trung Cấp"),
    ("bang_diem_trung_cap", "Bảng điểm toàn khóa Trung Cấp"),
    ("can_cuoc_cong_dan", "Căn cước công dân"),
    ("anh_3x4", "Ảnh 3x4"),
    ("giay_kham_suc_khoe", "Giấy Khám sức khỏe"),
    ("don_mien_giam", "Đơn miễn giảm"),
]

def _seed_if_empty(db: Session) -> ChecklistVersion:
    # Lấy version active/last; nếu không có thì seed v1
    v = db.query(ChecklistVersion).order_by(ChecklistVersion.id.desc()).first()
    if v:
        return v

    v = ChecklistVersion(version_name="v1")
    # nếu model có cột is_active thì bật lên
    if hasattr(v, "is_active"):
        setattr(v, "is_active", True)
    db.add(v)
    db.flush()  # có v.id

    # Tạo items; set order_index (hoặc order_no tuỳ model có cột nào)
    for idx, (code, name) in enumerate(DEFAULT_ITEMS, start=1):
        it = ChecklistItem(version_id=v.id, code=code, display_name=name)
        if hasattr(it, "order_index"):
            setattr(it, "order_index", idx)
        if hasattr(it, "order_no"):
            setattr(it, "order_no", idx)
        db.add(it)

    db.commit()
    db.refresh(v)
    return v

@router.get("/active")
def get_active_checklist(db: Session = Depends(get_db)):
    """
    Trả về version checklist đang dùng và danh mục item, có sắp xếp.
    Tự seed 'v1' nếu DB chưa có gì.
    """
    v = _seed_if_empty(db)

    # Order theo order_index -> order_no -> id
    # (dùng getattr để không phụ thuộc tên cột)
    order_col = None
    if hasattr(ChecklistItem, "order_index"):
        order_col = getattr(ChecklistItem, "order_index")
    elif hasattr(ChecklistItem, "order_no"):
        order_col = getattr(ChecklistItem, "order_no")

    q = db.query(ChecklistItem).filter(ChecklistItem.version_id == v.id)
    if order_col is not None:
        q = q.order_by(order_col.asc())
    else:
        q = q.order_by(ChecklistItem.id.asc())
    items = q.all()

    # Chuẩn dữ liệu cho UI (UI sort lại bằng order_index || order_no)
    out_items = []
    for it in items:
        out_items.append({
            "code": it.code,
            "display_name": it.display_name,
            "order_index": getattr(it, "order_index", None),
            "order_no": getattr(it, "order_no", None),
        })
    return {"version_name": v.version_name, "items": out_items}
