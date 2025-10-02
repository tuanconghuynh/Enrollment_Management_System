# app/core/security.py
from passlib.context import CryptContext

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    """Trả về bcrypt hash cho mật khẩu thô."""
    return _pwd.hash(password)

def verify_password(plain_password: str, password_hash: str) -> bool:
    """So sánh mật khẩu thô với hash đã lưu."""
    if not password_hash:
        return False
    try:
        return _pwd.verify(plain_password, password_hash)
    except Exception:
        return False
