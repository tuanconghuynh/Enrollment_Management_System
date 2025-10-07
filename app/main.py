# app/main.py
import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import JSONResponse, RedirectResponse

from app.db.base import Base
from app.db.session import engine

# Routers
from app.routers import health, applicants, checklist, export, batch
from app.routers import auth, admin
# Dùng chung hằng số timeout với auth.py để không lệch
from app.routers.auth import IDLE_TIMEOUT_SEC as AUTH_IDLE_TIMEOUT_SEC

app = FastAPI()

# Cookie sống 7 ngày; idle timeout xử lý riêng (3 giờ trong auth + middleware)
app.add_middleware(
    SessionMiddleware,
    secret_key="change-me-please",   # nhớ đổi ở production / đặt qua ENV
    max_age=60 * 60 * 24 * 7,        # 7 ngày
    same_site="lax",
)

# ===== Idle timeout =====
MAX_IDLE_SECONDS = AUTH_IDLE_TIMEOUT_SEC  # 3h từ auth.py

WHITELIST_PREFIXES = (
    # KHÔNG để "/" ở đây kẻo bypass mọi route
    "/index.html",
    "/login", "/api/login",          # login
    "/health", "/api/health",        # health
    "/auth_login.html",              # file login tĩnh
    "/hutech.png", "/favicon",       # assets phổ biến
    "/static", "/assets",            # mount assets
)

STATIC_EXTS = (".css", ".js", ".png", ".jpg", ".jpeg", ".svg", ".ico", ".map", ".woff", ".woff2", ".ttf")


@app.middleware("http")
async def idle_timeout_middleware(request, call_next):
    path = request.url.path

    # Bỏ qua đường whitelist & file tĩnh
    if path.startswith(WHITELIST_PREFIXES) or path.lower().endswith(STATIC_EXTS):
        return await call_next(request)

    # Một số path (nhất là static mount) có thể không có session trong scope -> bỏ qua an toàn
    if "session" not in request.scope:
        return await call_next(request)

    sess = request.session
    uid = sess.get("uid")

    if uid:
        from time import time as _now
        now = int(_now())
        # DÙNG CÙNG KEY VỚI auth.py
        last = int(sess.get("_last_seen") or 0)

        # Hết hạn do không hoạt động
        if last and now - last > MAX_IDLE_SECONDS:
            request.session.clear()
            # API -> 401 JSON ; Web -> redirect /login
            if path.startswith("/api"):
                return JSONResponse({"detail": "Session expired"}, status_code=401)
            return RedirectResponse(url="/login", status_code=302)

        # Còn hạn -> cập nhật mốc hoạt động (đồng bộ với auth.py)
        sess["_last_seen"] = now

    return await call_next(request)


# ================== Mount routers ==================
app.include_router(auth.router,  tags=["Auth"])
app.include_router(admin.router, tags=["Admin"])

# API chuẩn /api/...
app.include_router(health.router,     prefix="/api", tags=["Health"])
app.include_router(checklist.router,  prefix="/api", tags=["Checklist"])
app.include_router(applicants.router, prefix="/api", tags=["Applicants"])
app.include_router(batch.router,      prefix="/api", tags=["Batch"])
app.include_router(export.router,     prefix="/api", tags=["Export"])

# Alias không /api (ẩn khỏi docs) để web cũ vẫn chạy
for r in (health.router, checklist.router, applicants.router, batch.router, export.router):
    app.include_router(r, prefix="", include_in_schema=False)

# ================== Startup ==================
@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)

# (tuỳ chọn) log routes để debug
@app.on_event("startup")
def _log_routes():
    for r in app.routes:
        try:
            print("ROUTE:", getattr(r, "path", r), getattr(r, "methods", ""))
        except Exception:
            pass

# ================== Static web/ (ĐẶT CUỐI CÙNG) ==================
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WEB_DIR  = os.path.join(BASE_DIR, "web")
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="webroot")
