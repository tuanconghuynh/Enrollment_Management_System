# app/utils/soft_delete.py
from __future__ import annotations

from typing import Any, Optional
from fastapi import HTTPException
from sqlalchemy.orm import Query
from sqlalchemy.sql import and_

def _soft_delete_conds(model) -> list:
    """
    Tạo danh sách điều kiện soft-delete từ model:
      - deleted_at IS NULL
      - is_deleted = FALSE
      - status != 'deleted'
    Có trường nào thì áp trường đó.
    """
    conds = []
    # deleted_at: datetime nullable
    if hasattr(model, "deleted_at"):
        conds.append(getattr(model, "deleted_at").is_(None))
    # is_deleted: bool
    if hasattr(model, "is_deleted"):
        conds.append(getattr(model, "is_deleted").is_(False))
    # status: string
    if hasattr(model, "status"):
        conds.append(getattr(model, "status") != "deleted")
    return conds

def exclude_deleted(model_or_query: Any, maybe_query: Optional[Query] = None) -> Query:
    """
    Dùng chuẩn:  exclude_deleted(Applicant, query)
    (Giữ tương thích cũ: exclude_deleted(query) nếu trước đây anh từng gọi vậy.)

    Trả về query đã thêm filter loại bỏ bản ghi đã xoá mềm.
    Không có cột nào liên quan -> trả nguyên query (không crash).
    """
    # Back-compat: nếu chỉ truyền 1 tham số là Query
    if maybe_query is None:
        q = model_or_query
        model = q.column_descriptions[0]["entity"] if q.column_descriptions else None
    else:
        model = model_or_query
        q = maybe_query

    if not isinstance(q, Query):
        raise TypeError("exclude_deleted expects SQLAlchemy Query")

    conds = _soft_delete_conds(model) if model is not None else []
    return q.filter(and_(*conds)) if conds else q

def ensure_not_deleted(obj: Any, raise_http_exception: bool = True) -> bool:
    """
    Kiểm tra một bản ghi có bị xoá mềm không.
    - Nếu raise_http_exception=True và đối tượng bị xoá -> raise HTTP 410.
    - Ngược lại trả về True (bình thường) / False (đã xoá).
    """
    deleted = False

    if hasattr(obj, "deleted_at") and getattr(obj, "deleted_at") is not None:
        deleted = True
    if hasattr(obj, "is_deleted") and getattr(obj, "is_deleted") is True:
        deleted = True
    if hasattr(obj, "status") and getattr(obj, "status") == "deleted":
        deleted = True

    if deleted and raise_http_exception:
        raise HTTPException(status_code=410, detail="Hồ sơ đã bị xoá tạm.")
    return not deleted
