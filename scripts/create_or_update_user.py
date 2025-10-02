# scripts/create_or_update_user.py
from app.db.session import SessionLocal
from app.models import User
from passlib.hash import bcrypt

USERNAME   = "vhtpt@hutech.edu.vn"
PASSWORD   = "VHTPT@hutech123"
ROLE       = "Admin"      # đổi thành "NhanVien" hoặc "CongTacVien" nếu muốn
FULL_NAME  = "V-HT.PTĐT"
EMAIL      = "vhtpt@hutech.edu.vn"

def main():
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.username == USERNAME).first()
        if u:
            u.password_hash = bcrypt.hash(PASSWORD)
            u.role = ROLE
            if FULL_NAME: u.full_name = FULL_NAME
            if EMAIL:     u.email = EMAIL
            print(f"UPDATED user id={u.id} ({USERNAME})")
        else:
            u = User(
                username=USERNAME,
                password_hash=bcrypt.hash(PASSWORD),
                role=ROLE,
                full_name=FULL_NAME,
                email=EMAIL,
                is_active=True,
            )
            db.add(u)
            print(f"CREATED user ({USERNAME})")
        db.commit()
    finally:
        db.close()

if __name__ == "__main__":
    main()
