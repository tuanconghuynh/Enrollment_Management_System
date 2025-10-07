# ================================
# file: app/services/checklist_service.py
# ================================
from sqlalchemy.orm import Session
from ..db.session import SessionLocal
from ..models import ChecklistVersion, ChecklistItem

# Giữ đúng code & display_name đã dùng trong routers/checklist.py
DEFAULT_ITEMS = [
    ("so_yeu_ly_lich", "Sơ yếu lý lịch", 1),
    ("bang_tot_nghiep_thpt", "Bằng tốt nghiệp THPT (hoặc tương đương)", 1),
    ("hoc_ba_thpt", "Học bạ THPT (hoặc Bảng điểm THPT)", 1),
    ("bang_tot_nghiep_dai_hoc", "Bằng tốt nghiệp Đại học", 1),
    ("bang_diem_dai_hoc", "Bảng điểm toàn khoá học Đại học", 1),
    ("bang_tot_nghiep_cao_dang", "Bằng tốt nghiệp Cao đẳng", 1),
    ("bang_diem_cao_dang", "Bảng điểm toàn khóa học Cao đẳng", 1),
    ("bang_tot_nghiep_trung_cap", "Bằng tốt nghiệp Trung Cấp", 1),
    ("bang_diem_trung_cap", "Bảng điểm toàn khóa Trung Cấp", 1),
    ("can_cuoc_cong_dan", "Căn cước công dân", 1),
    ("anh_3x4", "Ảnh 3x4", 2),
    ("giay_kham_suc_khoe", "Giấy Khám sức khỏe", 1),
    ("don_mien_giam", "Đơn miễn giảm", 1),
]

def seed_default_checklist():
    """
    Tự tạo checklist version 'v1' với 13 mục mặc định
    nếu bảng ChecklistVersion đang rỗng.
    """
    db: Session = SessionLocal()
    try:
        # Nếu DB chưa có version nào thì seed
        if db.query(ChecklistVersion).count() == 0:
            v = ChecklistVersion(version_name="v1", active=True)
            db.add(v)
            db.flush()  # có v.id

            for i, (code, name, qty) in enumerate(DEFAULT_ITEMS, start=1):
                item = ChecklistItem(
                    version_id=v.id,
                    code=code,
                    display_name=name,
                    default_qty=qty,
                )
                # tuỳ cột trong model: order_no hoặc order_index
                if hasattr(item, "order_no"):
                    setattr(item, "order_no", i)
                elif hasattr(item, "order_index"):
                    setattr(item, "order_index", i)
                db.add(item)

            db.commit()
    finally:
        db.close()
