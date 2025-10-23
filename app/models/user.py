from sqlalchemy import Column, Integer, String, DateTime, Boolean, func, Date
from app.db.base import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False)

    # Hash đang dùng để đăng nhập
    password_hash = Column(String(255), nullable=False)

    # 🆕 Hash của "mật khẩu mặc định" mỗi lần Admin reset.
    # Dùng để NGĂN người dùng đặt lại đúng mật khẩu này.
    # Không xóa sau khi user đổi mật khẩu; chỉ thay khi Admin reset lần mới.
    reset_password_hash = Column(String(255), nullable=True)

    role = Column(String(20), nullable=False, default="CongTacVien")
    full_name = Column(String(128))
    email = Column(String(128))
    dob = Column(Date)
    is_active = Column(Boolean, default=True)

    # Lần đầu phải đổi mật khẩu
    must_change_password = Column(Boolean, nullable=False, server_default="1")

    last_login_at = Column(DateTime, nullable=True)
    password_changed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username='{self.username}', role='{self.role}')>"
