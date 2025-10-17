# app/services/audit.py
from __future__ import annotations

import os
import json
import hmac
import hashlib
from typing import Optional, Any, Dict

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.audit import AuditLog

# Bí mật ký HMAC cho audit (đặt biến môi trường ở production)
AUDIT_HMAC_SECRET = os.getenv("AUDIT_HMAC_SECRET", "audit-dev")


def _norm_json(val: Any) -> Dict[str, Any]:
    """
    Chuẩn hoá prev_values/new_values thành dict để lưu JSON.
    - Nếu là None -> {}
    - Nếu là dict -> giữ nguyên
    - Nếu là chuỗi JSON -> parse
    - Còn lại -> bọc vào {"_raw": ...}
    """
    if val is None:
        return {}
    if isinstance(val, dict):
        return val
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            return parsed if isinstance(parsed, dict) else {"_raw": parsed}
        except Exception:
            return {"_raw": val}
    return {"_raw": val}


def _build_hmac_hash(
    *,
    action: str,
    status: Optional[str],
    target_type: Optional[str],
    target_id: Optional[str],
    correlation_id: Optional[str],
    prev_values: Dict[str, Any],
    new_values: Dict[str, Any],
) -> str:
    """
    Tạo chữ ký HMAC-SHA256 trên payload audit (đã chuẩn hoá).
    """
    payload = {
        "action": action or "",
        "status": status or "",
        "target_type": target_type or "",
        "target_id": str(target_id or ""),
        "correlation_id": correlation_id or "",
        "prev_values": prev_values,
        "new_values": new_values,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hmac.new(AUDIT_HMAC_SECRET.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256).hexdigest()


def write_audit(
    db: Session,
    *,
    action: str,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    status: str = "SUCCESS",
    prev_values: Optional[Dict[str, Any]] = None,
    new_values: Optional[Dict[str, Any]] = None,
    request: Optional[Request] = None,
) -> AuditLog:
    """
    Ghi 1 dòng audit. Không commit ở đây (để caller chủ động).
    Bắt buộc set được hmac_hash để phù hợp DB NOT NULL.
    """
    # Lấy actor từ session (nếu có)
    actor_id = None
    actor_name = None
    if request is not None:
        try:
            sess = getattr(request, "session", {}) or {}
            actor_id = sess.get("uid") or sess.get("user_id")
            actor_name = (
                sess.get("full_name")
                or sess.get("username")
                or sess.get("email")
                or actor_id
            )
        except Exception:
            pass

    ip = request.client.host if (request and request.client) else None
    path = request.url.path if request else None
    cid = getattr(request.state, "correlation_id", None) if request else None

    # Chuẩn hoá JSON cho cột JSON của MySQL
    prev_j = _norm_json(prev_values)
    new_j = _norm_json(new_values)

    # Tính chữ ký hmac
    h = _build_hmac_hash(
        action=action,
        status=status,
        target_type=target_type,
        target_id=target_id,
        correlation_id=cid,
        prev_values=prev_j,
        new_values=new_j,
    )

    row = AuditLog(
        action=action,
        status=status,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        prev_values=prev_j,
        new_values=new_j,
        actor_id=str(actor_id) if actor_id is not None else None,
        actor_name=str(actor_name) if actor_name is not None else None,
        ip_address=ip,
        path=path,
        correlation_id=cid,
        hmac_hash=h,  # 👈 quan trọng: set giá trị NOT NULL
    )
    db.add(row)
    return row
