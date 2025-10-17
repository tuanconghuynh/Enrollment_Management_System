# app/models/audit.py
from sqlalchemy import Column, Integer, String, DateTime, JSON, Text, func, ForeignKey
from app.db.base import Base

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    occurred_at = Column(DateTime, server_default=func.now(), nullable=False)

    action = Column(String(64), nullable=False)
    status = Column(String(32), nullable=True)

    target_type = Column(String(64), nullable=True)
    target_id   = Column(String(128), nullable=True)

    actor_id   = Column(String(128), nullable=True)
    actor_name = Column(String(255), nullable=True)
    ip_address = Column(String(64), nullable=True)
    path       = Column(String(255), nullable=True)
    correlation_id = Column(String(64), nullable=True)

    # 👇 THÊM DÒNG NÀY (khớp DB hiện có)
    hmac_hash = Column(String(128), nullable=False)

    prev_values = Column(JSON, nullable=True)
    new_values  = Column(JSON, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "occurred_at": self.occurred_at.isoformat() if self.occurred_at else None,
            "action": self.action,
            "status": self.status,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "actor_id": self.actor_id,
            "actor_name": self.actor_name,
            "ip_address": self.ip_address,
            "path": self.path,
            "correlation_id": self.correlation_id,
            "prev_values": self.prev_values,
            "new_values": self.new_values,
        }
    
class DeletionRequest(Base):
    __tablename__ = "deletion_requests"

    id = Column(Integer, primary_key=True)

    # Ai tạo yêu cầu xoá
    actor_id   = Column(String(128), nullable=True)
    actor_name = Column(String(255), nullable=True)

    # Mục tiêu cần xoá
    target_type = Column(String(64), nullable=True)     # vd: "Applicant"
    target_id   = Column(String(128), nullable=False)   # vd: MSSV

    # Lý do và trạng thái phê duyệt
    reason = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="pending")  # pending/approved/rejected

    # Tham chiếu log phát sinh yêu cầu (nếu có)
    audit_log_id = Column(Integer, ForeignKey("audit_logs.id"), nullable=True)

    # Thông tin xác nhận
    confirmed_by = Column(String(255), nullable=True)
    confirmed_at = Column(DateTime, nullable=True)

    # Thời điểm tạo
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "actor_id": self.actor_id,
            "actor_name": self.actor_name,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "reason": self.reason,
            "confirmed_by": self.confirmed_by,
            "confirmed_at": self.confirmed_at.isoformat() if self.confirmed_at else None,
            "status": self.status,
            "audit_log_id": self.audit_log_id,
        }