# ================================
# file: app/models/checklist.py
# ================================
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from ..db.base import Base

class ChecklistVersion(Base):
    __tablename__ = "checklist_versions"
    id = Column(Integer, primary_key=True)
    version_name = Column(String(64), unique=True, index=True)
    active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    items = relationship("ChecklistItem", back_populates="version", cascade="all, delete-orphan")

class ChecklistItem(Base):
    __tablename__ = "checklist_items"
    id = Column(Integer, primary_key=True)
    version_id = Column(Integer, ForeignKey("checklist_versions.id", ondelete="CASCADE"))
    code = Column(String(64), index=True)
    display_name = Column(String(255))
    default_qty = Column(Integer, default=1)
    order_no = Column(Integer, default=0)
    version = relationship("ChecklistVersion", back_populates="items")