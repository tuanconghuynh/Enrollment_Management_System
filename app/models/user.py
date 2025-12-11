# app/models/user.py
from sqlalchemy import Column, Integer, String, DateTime, Boolean, func, Date
from sqlalchemy.ext.hybrid import hybrid_property
from app.db.base import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False)

    # Hash đang dùng để đăng nhập
    password_hash = Column(String(255), nullable=False)

    # Hash "mật khẩu mặc định" mỗi lần Admin reset
    reset_password_hash = Column(String(255), nullable=True)

    role = Column(String(20), nullable=False, default="CongTacVien")

    # Giữ để tương thích cũ (sẽ bỏ sau)
    full_name = Column(String(128), nullable=True)

    # MỚI: tách tên
    last_name = Column(String(128), nullable=True, index=True)
    first_name = Column(String(64), nullable=True, index=True)

    email = Column(String(128))
    dob = Column(Date)
    is_active = Column(Boolean, default=True)

    must_change_password = Column(Boolean, nullable=False, server_default="1")

    last_login_at = Column(DateTime, nullable=True)
    password_changed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # --- Tương thích ngược: đọc "full name" thống nhất ---
    @hybrid_property
    def display_name(self) -> str:
        """
        Tên hiển thị ưu tiên last_name + first_name; nếu trống thì fallback full_name (cũ).
        """
        ln = (self.last_name or '').strip()
        fn = (self.first_name or '').strip()
        if ln or fn:
            return (ln + ' ' + fn).strip()
        return (self.full_name or '').strip()

    # Cho phép dùng trong SQL (ORDER BY / filter) mà không phải load về Python
    @display_name.expression
    def display_name(cls):
        # TRIM(CONCAT(COALESCE(last_name,''),' ',COALESCE(first_name,'')))
        return func.trim(
            func.concat(
                func.coalesce(cls.last_name, ''),
                ' ',
                func.coalesce(cls.first_name, '')
            )
        )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username='{self.username}', role='{self.role}')>"
