from sqlalchemy import Column, BigInteger, Integer, String, DateTime, Text, Enum, func, JSON
from sqlalchemy.dialects.mysql import JSON as MyJSON
from sqlalchemy.orm import declarative_base
from datetime import datetime


Base = declarative_base()

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    occurred_at = Column(DateTime, server_default=func.now(), nullable=False)

    action = Column(String(64), nullable=False)
    status = Column(String(32), nullable=True)

    target_type = Column(String(64), nullable=True)
    target_id   = Column(String(128), nullable=True)

    # 👇 các trường tác nhân & ngữ cảnh
    actor_id   = Column(String(128), nullable=True)
    actor_name = Column(String(255), nullable=True)
    ip_address = Column(String(64), nullable=True)
    path       = Column(String(255), nullable=True)
    correlation_id = Column(String(64), nullable=True)

    # snapshot
    prev_values = Column(JSON, nullable=True)
    new_values  = Column(JSON, nullable=True)
    # hoặc nếu dùng Text:
    # prev_values = Column(Text)
    # new_values  = Column(Text)

    def to_dict(self):
        return {
            "id": self.id,
            "occurred_at": (self.occurred_at.isoformat() if self.occurred_at else None),
            "action": self.action,
            "status": self.status,
            "target_type": self.target_type,
            "target_id": self.target_id,

            # 👇 QUAN TRỌNG: trả về actor_name
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
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    actor_id = Column(BigInteger)
    actor_name = Column(String(255))
    target_type = Column(String(64), nullable=False)
    target_id = Column(String(64), nullable=False)
    reason = Column(Text, nullable=False)
    confirmed_by = Column(String(255))
    confirmed_at = Column(DateTime)
    status = Column(Enum('PENDING','APPROVED','REJECTED','EXECUTED'), nullable=False, default='PENDING')
    audit_log_id = Column(BigInteger)
