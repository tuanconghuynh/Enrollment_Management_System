# app/main.py
import os
import uuid
from time import time as _now

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import JSONResponse, RedirectResponse

from app.db.base import Base
from app.db.session import engine, get_db

# Routers
from app.routers import health, applicants, checklist, export, batch
from app.routers import auth, admin, journal
from app.routers import account  #trang thông tin tài khoản
from urllib.parse import quote

# Dùng chung hằng số timeout với auth.py để không lệch
from app.routers.auth import IDLE_TIMEOUT_SEC as AUTH_IDLE_TIMEOUT_SEC

# (tuỳ) audit
try:
    from app.services.audit import write_audit
except Exception:
    write_audit = None  # fallback an toàn

app = FastAPI()

# ---------------- Session cookie ----------------
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "change-me-please"),
    max_age=60 * 60 * 24 * 7,  # 7 ngày
    same_site="lax",
)

# ---------------- Correlation-ID ----------------
@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    cid = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
    request.state.correlation_id = cid
    resp = await call_next(request)
    resp.headers["X-Correlation-ID"] = cid
    return resp

# ---------------- Idle timeout ----------------
MAX_IDLE_SECONDS = AUTH_IDLE_TIMEOUT_SEC  # 1h từ auth.py

WHITELIST_PREFIXES = (
    "/compilation.html",
    "/ams_home.html",
    "/login", "/api/login",
    "/logout", "/api/logout",
    "/health", "/api/health",
    "/auth_login.html",
    "/hutech.png", "/favicon",
    "/static", "/assets",
    "/journal.html",
    "/account", "/account/change-password",
)

STATIC_EXTS = (
    ".css", ".js", ".png", ".jpg", ".jpeg", ".svg",
    ".ico", ".map", ".woff", ".woff2", ".ttf", ".html"
)

@app.middleware("http")
async def idle_timeout_middleware(request: Request, call_next):
    path = request.url.path

    # Cho phép truy cập các đường tĩnh / whitelist
    if path.startswith(WHITELIST_PREFIXES) or path.lower().endswith(STATIC_EXTS):
        return await call_next(request)

    # Không có session -> tiếp tục bình thường
    if "session" not in request.scope:
        return await call_next(request)

    sess = request.session
    uid = sess.get("uid")

    if uid:
        now = int(_now())
        last = int(sess.get("_last_seen") or 0)
        if last and now - last > MAX_IDLE_SECONDS:
            # Hết hạn phiên
            request.session.clear()

            if path.startswith("/api"):
                # API: 401 + header để FE biết bật thông báo
                return JSONResponse(
                    {"detail": "Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại!"},
                    status_code=401,
                    headers={"X-Session-Expired": "1"}
                )

            # Web: đặt cookie cờ + redirect về login?expired=1
            next_q = quote(str(request.url.path) + (("?" + request.url.query) if request.url.query else ""))
            resp = RedirectResponse(url=f"/login?expired=1&next={next_q}", status_code=302)
            # Cookie *không* httponly để JS đọc và show toast; sống 30 giây
            resp.set_cookie(
                key="__session_expired",
                value="1",
                max_age=30,
                path="/",
                secure=False,      # Nếu anh chạy HTTPS có thể đặt True
                httponly=False,    # cho phép JS đọc
                samesite="lax",
            )
            return resp

        # Còn hạn → cập nhật dấu vết
        sess["_last_seen"] = now

    return await call_next(request)

# ---------------- Ép đổi mật khẩu lần đầu ----------------
ENFORCE_CHANGE_WHITELIST = (
    "/account", "/account/change-password", "/api/account/change-password",  # cho phép trang + API đổi pass
    "/login", "/api/login", "/logout", "/api/logout",
    "/health", "/api/health",
    "/auth_login.html",
    "/hutech.png", "/favicon",
    "/static", "/assets",
    "/journal.html",
)

from starlette.status import HTTP_403_FORBIDDEN

@app.middleware("http")
async def enforce_first_change_password(request: Request, call_next):
    path = request.url.path

    # file tĩnh & đường cho phép
    if path.startswith(ENFORCE_CHANGE_WHITELIST) or path.lower().endswith(STATIC_EXTS):
        return await call_next(request)

    # chưa đăng nhập thì thôi
    sess = request.session if "session" in request.scope else None
    uid = sess.get("uid") if sess else None
    if not uid:
        return await call_next(request)

    must_change = sess.get("must_change_password")
    if must_change is None:
        # nạp 1 lần rồi cache vào session
        try:
            db = next(get_db())
            from app.models.user import User
            u = db.get(User, uid)
            must_change = bool(u.must_change_password) if u else False
        except Exception:
            must_change = False
        sess["must_change_password"] = must_change

    if must_change:
        # API → trả JSON 403
        if path.startswith("/api"):
            return JSONResponse(
                {"detail": "Vui lòng đổi mật khẩu trước khi tiếp tục.", "force_change": True},
                status_code=HTTP_403_FORBIDDEN
            )
        # Web → ép về trang account
        return RedirectResponse(url="/account?first=1", status_code=302)

    return await call_next(request)

# ---------------- Global exception handler ----------------
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

# ---------------- Mount routers ----------------
app.include_router(auth.router,    tags=["Auth"])
app.include_router(admin.router,   tags=["Admin"])
app.include_router(account.router, tags=["Account"])

# API chuẩn
app.include_router(health.router,     prefix="/api", tags=["Health"])
app.include_router(checklist.router,  prefix="/api", tags=["Checklist"])
app.include_router(applicants.router, prefix="/api", tags=["Applicants"])
app.include_router(batch.router,      prefix="/api", tags=["Batch"])
app.include_router(export.router,     prefix="/api", tags=["Export"])
app.include_router(journal.router,    prefix="/api", tags=["Journal"])

# Alias không /api (ẩn khỏi docs)
for r in (health.router, checklist.router, applicants.router, batch.router, export.router, journal.router):
    app.include_router(r, prefix="", include_in_schema=False)

# ---------------- Startup ----------------
@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)

@app.on_event("startup")
def _log_routes():
    for r in app.routes:
        try:
            print("ROUTE:", getattr(r, "path", r), getattr(r, "methods", ""))
        except Exception:
            pass

# ---------------- Redirect "/" → ams_home.html ----------------
@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/ams_home.html", status_code=307)

# ---------------- Static web/ ----------------
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WEB_DIR  = os.path.join(BASE_DIR, "web")
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="webroot")
