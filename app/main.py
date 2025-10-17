# app/main.py
import os
import uuid

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import JSONResponse, RedirectResponse

from app.db.base import Base
from app.db.session import engine, get_db

# --- sửa import: journal (không phải journa)
from app.routers import journal

# Routers
from app.routers import health, applicants, checklist, export, batch
from app.routers import auth, admin

# Dùng chung hằng số timeout với auth.py để không lệch
from app.routers.auth import IDLE_TIMEOUT_SEC as AUTH_IDLE_TIMEOUT_SEC

# (tuỳ) audit
try:
    from app.services.audit import write_audit
except Exception:
    write_audit = None  # fallback an toàn

app = FastAPI()

# Cookie sống 7 ngày; idle timeout xử lý riêng (3 giờ trong auth + middleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "change-me-please"),  # nên đưa vào ENV
    max_age=60 * 60 * 24 * 7,        # 7 ngày
    same_site="lax",
)

# ===== Correlation-ID cho audit =====
@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    cid = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
    request.state.correlation_id = cid
    resp = await call_next(request)
    resp.headers["X-Correlation-ID"] = cid
    return resp

# ===== Idle timeout =====
MAX_IDLE_SECONDS = AUTH_IDLE_TIMEOUT_SEC  # 2h từ auth.py

WHITELIST_PREFIXES = (
    # KHÔNG để "/" ở đây kẻo bypass mọi route
    "/index.html",
    "/login", "/api/login",          # login
    "/health", "/api/health",        # health
    "/auth_login.html",              # file login tĩnh
    "/hutech.png", "/favicon",       # assets phổ biến
    "/static", "/assets",            # mount assets
    "/journal.html",
)

STATIC_EXTS = (".css", ".js", ".png", ".jpg", ".jpeg", ".svg", ".ico", ".map", ".woff", ".woff2", ".ttf", ".html")

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

# ===== Exception handler tổng: ghi audit khi lỗi chưa bắt =====
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    try:
        if write_audit:
            db = next(get_db())
            write_audit(
                db,
                action="EXCEPTION",
                target_type="System",
                target_id=None,
                status="FAILURE",
                new_values={"path": request.url.path, "error": type(exc).__name__},
                request=request,
            )
            db.commit()
    except Exception:
        pass
    return JSONResponse(status_code=500, content={"detail": "Đã xảy ra lỗi không xác định. Vui lòng thử lại."})

# ================== Mount routers ==================
app.include_router(auth.router,  tags=["Auth"])
app.include_router(admin.router, tags=["Admin"])

# API chuẩn /api/...
app.include_router(health.router,     prefix="/api", tags=["Health"])
app.include_router(checklist.router,  prefix="/api", tags=["Checklist"])
app.include_router(applicants.router, prefix="/api", tags=["Applicants"])
app.include_router(batch.router,      prefix="/api", tags=["Batch"])
app.include_router(export.router,     prefix="/api", tags=["Export"])
# >>> thêm journal vào /api
app.include_router(journal.router,    prefix="/api", tags=["Journal"])

# Alias không /api (ẩn khỏi docs) để web cũ vẫn chạy
for r in (health.router, checklist.router, applicants.router, batch.router, export.router, journal.router):
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
