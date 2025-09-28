# ================================
# file: app/services/checklist_service.py
# ================================
from sqlalchemy.orm import Session
from ..db.session import SessionLocal
from ..models import ChecklistVersion, ChecklistItem

DEFAULT_ITEMS = [
    ("so_yeu_ly_lich", "Sơ yếu lý lịch", 1),
    ("bang_tn_thpt", "Bằng tốt nghiệp THPT (hoặc tương đương)", 1),
    ("hoc_ba_thpt", "Học bạ THPT (hoặc Bảng điểm THPT)", 1),
    ("bang_tn_dh", "Bằng tốt nghiệp Đại học", 1),
    ("bang_diem_dh", "Bảng điểm toàn khoá học Đại học", 1),
    ("bang_tn_cd", "Bằng tốt nghiệp Cao đẳng", 1),
    ("bang_diem_cd", "Bảng điểm toàn khóa học Cao đẳng", 1),
    ("bang_tn_tc", "Bằng tốt nghiệp Trung Cấp", 1),
    ("bang_diem_tc", "Bảng điểm toàn khóa Trung Cấp", 1),
    ("cccd", "Căn cước công dân", 1),
    ("anh_3x4", "Ảnh 3x4", 2),
    ("giay_kham_sk", "Giấy Khám sức khỏe", 1),
    ("don_mien_giam", "Đơn miễn giảm", 1),
]

def seed_default_checklist():
    db: Session = SessionLocal()
    try:
        if db.query(ChecklistVersion).count() == 0:
            v = ChecklistVersion(version_name="v1", active=True)
            db.add(v)
            db.flush()
            for i, (code, name, qty) in enumerate(DEFAULT_ITEMS, start=1):
                db.add(ChecklistItem(version_id=v.id, code=code, display_name=name, default_qty=qty, order_no=i))
            db.commit()
    finally:
        db.close()