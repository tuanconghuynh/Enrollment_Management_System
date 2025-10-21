from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.session import get_db
from app.models.checklist import ChecklistItem, ChecklistVersion
from app.routers.auth import require_roles

router = APIRouter(prefix="/checklist", tags=["Checklist"])

# ==================== Helpers ====================

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


def _active_attr_name() -> str | None:
    if hasattr(ChecklistVersion, "is_active"):
        return "is_active"
    if hasattr(ChecklistVersion, "active"):
        return "active"
    return None


def _has_active_flag() -> bool:
    return _active_attr_name() is not None


def _get_active_flag(v: ChecklistVersion) -> bool | None:
    name = _active_attr_name()
    return getattr(v, name, None) if name else None


def _set_active_flag(v: ChecklistVersion, value: bool):
    name = _active_attr_name()
    if name:
        setattr(v, name, bool(value))


def _order_col():
    if hasattr(ChecklistItem, "order_index"):
        return getattr(ChecklistItem, "order_index")
    if hasattr(ChecklistItem, "order_no"):
        return getattr(ChecklistItem, "order_no")
    return None


def _set_order(item: ChecklistItem, idx: int):
    if hasattr(item, "order_index"):
        setattr(item, "order_index", idx)
    if hasattr(item, "order_no"):
        setattr(item, "order_no", idx)


# ==================== Core Logic ====================

def _seed_if_empty(db: Session) -> ChecklistVersion:
    total = db.query(func.count(ChecklistVersion.id)).scalar() or 0
    if total > 0:
        if _has_active_flag():
            v = db.query(ChecklistVersion).filter(
                getattr(ChecklistVersion, _active_attr_name()).is_(True)
            ).first()
            if v:
                return v
        return db.query(ChecklistVersion).order_by(ChecklistVersion.id.desc()).first()

    v = ChecklistVersion(version_name="v1")
    if _has_active_flag():
        _set_active_flag(v, True)
    db.add(v)
    db.flush()

    for i, (code, name) in enumerate(DEFAULT_ITEMS, start=1):
        it = ChecklistItem(version_id=v.id, code=code, display_name=name)
        _set_order(it, i)
        db.add(it)

    db.commit()
    db.refresh(v)
    return v


def _get_active(db: Session) -> ChecklistVersion:
    if _has_active_flag():
        v = db.query(ChecklistVersion).filter(
            getattr(ChecklistVersion, _active_attr_name()).is_(True)
        ).first()
        if v:
            return v
    v = db.query(ChecklistVersion).order_by(ChecklistVersion.id.desc()).first()
    if not v:
        v = _seed_if_empty(db)
    return v


def _list_items(db: Session, version_id: int):
    q = db.query(ChecklistItem).filter(ChecklistItem.version_id == version_id)
    order = _order_col()
    q = q.order_by(order.asc() if order else ChecklistItem.id.asc())
    return q.all()

# ==================== APIs ====================

@router.get("/active")
def get_active_checklist(db: Session = Depends(get_db)):
    v = _get_active(db)
    items = _list_items(db, v.id)
    return {
        "version_id": v.id,
        "version_name": v.version_name,
        "is_active": _get_active_flag(v),
        "items": [
            {
                "code": it.code,
                "display_name": it.display_name,
                "order_index": getattr(it, "order_index", None),
                "order_no": getattr(it, "order_no", None),
            }
            for it in items
        ],
    }


@router.get("/versions")
def list_versions(db: Session = Depends(get_db)):
    rows = db.query(ChecklistVersion).order_by(ChecklistVersion.id.asc()).all()
    return [
        {
            "id": v.id,
            "version_name": v.version_name,
            "is_active": _get_active_flag(v),
            "active": _get_active_flag(v),  # để UI linh hoạt
        }
        for v in rows
    ]


@router.get("/versions/{version_id}/items")
def get_version_items(
    version_id: int,
    db: Session = Depends(get_db),
    me=Depends(require_roles("Admin", "NhanVien")),  # cho xem cả nhân viên
):
    v = db.query(ChecklistVersion).filter(ChecklistVersion.id == version_id).first()
    if not v:
        raise HTTPException(404, "Version không tồn tại")
    items = _list_items(db, v.id)
    return {
        "version_id": v.id,
        "version_name": v.version_name,
        "is_active": _get_active_flag(v),
        "items": [
            {
                "code": it.code,
                "display_name": it.display_name,
                "order_index": getattr(it, "order_index", None),
                "order_no": getattr(it, "order_no", None),
            }
            for it in items
        ],
    }


@router.delete("/versions/{version_id}")
def delete_version(
    version_id: int,
    db: Session = Depends(get_db),
    me=Depends(require_roles("Admin")),
):
    v = db.query(ChecklistVersion).filter(ChecklistVersion.id == version_id).first()
    if not v:
        raise HTTPException(404, "Version không tồn tại")

    # chặn xóa nếu đang active
    if _has_active_flag():
        if _get_active_flag(v):
            raise HTTPException(409, "Không thể xóa phiên bản đang hoạt động")
    else:
        active = _get_active(db)  # fallback: xem phiên bản mới nhất là 'đang dùng'
        if active and active.id == v.id:
            raise HTTPException(409, "Không thể xóa phiên bản hiện tại")

    db.delete(v)
    db.commit()
    return {"ok": True, "deleted_id": version_id}


@router.post("/versions")
def create_version(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    me=Depends(require_roles("Admin")),
):
    name = (payload.get("version_name") or "").strip()
    if not name:
        raise HTTPException(422, "Thiếu 'version_name'")

    clone_from = payload.get("clone_from") or "active"
    if clone_from == "active":
        src = _get_active(db)
    else:
        try:
            src_id = int(clone_from)
        except Exception:
            raise HTTPException(400, "clone_from không hợp lệ")
        src = db.query(ChecklistVersion).filter(ChecklistVersion.id == src_id).first()
        if not src:
            raise HTTPException(404, "Version nguồn không tồn tại")

    v = ChecklistVersion(version_name=name)
    db.add(v)
    db.flush()

    items = _list_items(db, src.id)
    for i, it in enumerate(items, start=1):
        ni = ChecklistItem(version_id=v.id, code=it.code, display_name=it.display_name)
        _set_order(ni, i)
        db.add(ni)

    if _has_active_flag() and bool(payload.get("activate") or False):
        active_col = getattr(ChecklistVersion, _active_attr_name())
        db.query(ChecklistVersion).filter(ChecklistVersion.id != v.id).update({active_col: False})
        _set_active_flag(v, True)
    else:
        # ÉP FALSE khi không chọn kích hoạt ngay (chống dính default cũ)
        if _has_active_flag():
            _set_active_flag(v, False)

    db.commit()
    return {
        "id": v.id,
        "version_name": v.version_name,
        "is_active": _get_active_flag(v),
        "cloned_from": src.id,
        "items": len(items),
    }


@router.post("/versions/{version_id}/activate")
def activate_version(
    version_id: int,
    db: Session = Depends(get_db),
    me=Depends(require_roles("Admin")),
):
    v = db.query(ChecklistVersion).filter(ChecklistVersion.id == version_id).first()
    if not v:
        raise HTTPException(404, "Version không tồn tại")

    if not _has_active_flag():
        raise HTTPException(400, "Model ChecklistVersion không có cột 'active'/'is_active' — cần thêm cột boolean.")

    active_col = getattr(ChecklistVersion, _active_attr_name())
    db.query(ChecklistVersion).filter(ChecklistVersion.id != v.id).update({active_col: False})
    _set_active_flag(v, True)
    db.add(v)
    db.commit()
    return {"ok": True, "activated_id": v.id}


@router.post("/items")
def add_item(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    me=Depends(require_roles("Admin")),
):
    code = (payload.get("code") or "").strip()
    name = (payload.get("display_name") or "").strip()
    if not code or not name:
        raise HTTPException(422, "Thiếu code/display_name")
    if not all(c.islower() or c.isdigit() or c == "_" for c in code):
        raise HTTPException(422, "Code chỉ gồm chữ thường, số, gạch dưới")

    v = _get_active(db)
    existed = (
        db.query(ChecklistItem)
        .filter(ChecklistItem.version_id == v.id, ChecklistItem.code == code)
        .first()
    )
    if existed:
        raise HTTPException(409, "Code đã tồn tại trong version hiện tại")

    order = _order_col()
    max_order = 0
    if order is not None:
        last = (
            db.query(ChecklistItem)
            .filter(ChecklistItem.version_id == v.id)
            .order_by(order.desc())
            .first()
        )
        if last is not None:
            max_order = getattr(last, "order_index", None) or getattr(last, "order_no", None) or 0

    it = ChecklistItem(version_id=v.id, code=code, display_name=name)
    _set_order(it, max_order + 1)
    db.add(it)
    db.commit()
    return {"ok": True, "version_id": v.id, "code": code}


@router.patch("/items/{code}")
def update_item(
    code: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    me=Depends(require_roles("Admin")),
):
    v = _get_active(db)
    it = (
        db.query(ChecklistItem)
        .filter(ChecklistItem.version_id == v.id, ChecklistItem.code == code)
        .first()
    )
    if not it:
        raise HTTPException(404, "Mục không tồn tại trong version hiện tại")

    name = (payload.get("display_name") or "").strip()
    if not name:
        raise HTTPException(422, "Thiếu display_name")

    it.display_name = name
    db.add(it)
    db.commit()
    return {"ok": True}


@router.delete("/items/{code}")
def delete_item(
    code: str,
    db: Session = Depends(get_db),
    me=Depends(require_roles("Admin")),
):
    v = _get_active(db)
    it = (
        db.query(ChecklistItem)
        .filter(ChecklistItem.version_id == v.id, ChecklistItem.code == code)
        .first()
    )
    if not it:
        raise HTTPException(404, "Mục không tồn tại trong version hiện tại")

    db.delete(it)
    db.flush()

    items = _list_items(db, v.id)
    for i, item in enumerate(items, start=1):
        _set_order(item, i)
        db.add(item)

    db.commit()
    return {"ok": True}


@router.post("/reorder")
def reorder_items(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    me=Depends(require_roles("Admin")),
):
    codes = payload.get("codes") or []
    if not isinstance(codes, list) or not codes:
        raise HTTPException(422, "Thiếu/không hợp lệ: codes")

    v = _get_active(db)
    items = {it.code: it for it in _list_items(db, v.id)}
    if set(codes) != set(items.keys()):
        raise HTTPException(400, "Danh sách codes không khớp danh mục hiện tại")

    for i, code in enumerate(codes, start=1):
        it = items[code]
        _set_order(it, i)
        db.add(it)
    db.commit()
    return {"ok": True, "version_id": v.id, "count": len(codes)}
