from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean
from app.db.base import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(128), unique=True, nullable=False)  # vd: admin hoặc email
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="CongTacVien")  # Admin|NhanVien|CongTacVien
    full_name = Column(String(128))
    email = Column(String(128))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
