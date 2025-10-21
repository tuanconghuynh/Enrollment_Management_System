# app/models/user.py
from sqlalchemy import Column, Integer, String, DateTime, Boolean, func, Date
from app.db.base import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="CongTacVien")
    full_name = Column(String(128))
    email = Column(String(128))
    dob = Column(Date) 
    is_active = Column(Boolean, default=True)
    must_change_password = Column(Boolean, nullable=False, server_default="1")  # lần đầu phải đổi
    last_login_at = Column(DateTime, nullable=True)
    password_changed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username='{self.username}', role='{self.role}')>"
