# scripts/ensure_user.py
from app.db.session import SessionLocal, engine
from app.models.user import User
from passlib.hash import bcrypt

USERS_TO_ENSURE = [
    ("admin", "admin123", "Admin", "Administrator", "admin@local"),
    ("vhtpt@hutech.edu.vn", "VHTPT@hutech123", "Admin", "V-HT.PTĐT", "vhtpt@hutech.edu.vn"),
]

def upsert_user(db, username, password, role, full_name, email):
    u = db.query(User).filter(User.username == username).first()
    if u:
        u.password_hash = bcrypt.hash(password)
        u.role = role
        if full_name: u.full_name = full_name
        if email: u.email = email
        msg = f"UPDATED {username}"
    else:
        u = User(username=username, password_hash=bcrypt.hash(password),
                 role=role, full_name=full_name, email=email, is_active=True)
        db.add(u)
        msg = f"CREATED {username}"
    return msg

def main():
    print("DB =", engine.url.render_as_string(hide_password=True))
    db = SessionLocal()
    try:
        for (u, p, r, f, e) in USERS_TO_ENSURE:
            print(upsert_user(db, u, p, r, f, e))
        db.commit()
        # show users
        users = db.query(User).all()
        print("Users in DB:", [(x.id, x.username, x.role, x.is_active) for x in users])
    finally:
        db.close()

if __name__ == "__main__":
    main()
