from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, ForeignKey, Index, func
)
from sqlalchemy.orm import relationship
from ..db.base import Base

class ChecklistVersion(Base):
    __tablename__ = "checklist_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    version_name = Column(String(64), unique=True, index=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

    items = relationship("ChecklistItem", back_populates="version", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<ChecklistVersion(id={self.id}, name='{self.version_name}', active={self.active})>"


class ChecklistItem(Base):
    __tablename__ = "checklist_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    version_id = Column(Integer, ForeignKey("checklist_versions.id", ondelete="CASCADE"))
    code = Column(String(64))
    display_name = Column(String(255))
    default_qty = Column(Integer, default=1)
    order_no = Column(Integer, default=0)

    version = relationship("ChecklistVersion", back_populates="items")

    __table_args__ = (
        Index("ix_checklist_items_code", "code"),
    )

    def __repr__(self) -> str:
        return f"<ChecklistItem(id={self.id}, code='{self.code}', ver={self.version_id})>"
