# app/main.py
import os
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles

from app.db.base import Base
from app.db.session import engine

# Routers sẵn có
from app.routers import health, applicants, checklist, export, batch
from app.routers import auth      # đăng nhập (có cả /login và /api/login)
from app.routers import admin     # quản lý người dùng /admin

app = FastAPI()

# Khóa session — đổi chuỗi này ở production
app.add_middleware(
    SessionMiddleware,
    secret_key="change-me-please",
    max_age=60 * 60 * 24 * 7,
)

# ================== Mount routers ==================

# Auth + Admin (KHÔNG prefix). Trong auth.py đã có alias /api/... sẵn.
app.include_router(auth.router, tags=["Auth"])
app.include_router(admin.router, tags=["Admin"])

# API chuẩn tại /api/...
app.include_router(health.router,     prefix="/api", tags=["Health"])
app.include_router(checklist.router,  prefix="/api", tags=["Checklist"])
app.include_router(applicants.router, prefix="/api", tags=["Applicants"])
app.include_router(batch.router,      prefix="/api", tags=["Batch"])
app.include_router(export.router,     prefix="/api", tags=["Export"])

# Alias KHÔNG /api (để web cũ gọi đường cũ vẫn chạy, ẩn khỏi docs)
for r in (health.router, checklist.router, applicants.router, batch.router, export.router):
    app.include_router(r, prefix="", include_in_schema=False)

# ================== Startup ==================
@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)

# (tuỳ chọn) log toàn bộ routes để debug nhanh
@app.on_event("startup")
def _log_routes():
    for r in app.routes:
        try:
            print("ROUTE:", getattr(r, "path", r), getattr(r, "methods", ""))
        except Exception:
            pass

# ================== Static web/ (ĐẶT CUỐI CÙNG) ==================
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WEB_DIR = os.path.join(BASE_DIR, "web")
# Serve toàn bộ thư mục web/ tại root (index.html, auth_login.html, import_students.html, students_list.html, ...)
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="webroot")
# Giờ có thể truy cập /index.html, /auth_login.html, /import_students.html, /students_list.html, ...