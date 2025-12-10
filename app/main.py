# app/main.py
import os
import uuid
from time import time as _now

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import JSONResponse, RedirectResponse
from starlette.status import HTTP_403_FORBIDDEN

from fastapi.middleware.cors import CORSMiddleware

from app.db.base import Base
from app.db.session import engine, get_db
from app.routers import applicants_batch
from app.routers import health, applicants, checklist, export, batch
from app.routers import auth, admin, journal
from app.routers import account
from app.routers import applicants_email
from app.core.config import settings
from app.routers.auth import IDLE_TIMEOUT_SEC as AUTH_IDLE_TIMEOUT_SEC
from urllib.parse import quote

# (tuỳ) audit
try:
    from app.services.audit import write_audit
except Exception:
    write_audit = None

# ================== TEMPLATE PATH CHUNG ==================
BASE_DIR = os.path.dirname(__file__)                  # .../app
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
WEB_TEMPLATES_DIR = os.path.join(TEMPLATES_DIR, "web")
templates = Jinja2Templates(directory=WEB_TEMPLATES_DIR)
# =========================================================

app = FastAPI()

app.include_router(applicants_email.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- Session cookie ----------------
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "change-me-please"),
    max_age=60 * 60 * 24 * 7,
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

    if path.startswith(WHITELIST_PREFIXES) or path.lower().endswith(STATIC_EXTS):
        return await call_next(request)

    if "session" not in request.scope:
        return await call_next(request)

    sess = request.session
    uid = sess.get("uid")

    if uid:
        now = int(_now())
        last = int(sess.get("_last_seen") or 0)
        if last and now - last > MAX_IDLE_SECONDS:
            request.session.clear()

            if path.startswith("/api"):
                return JSONResponse(
                    {"detail": "Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại!"},
                    status_code=401,
                    headers={"X-Session-Expired": "1"}
                )

            next_q = quote(str(request.url.path) + (("?" + request.url.query) if request.url.query else ""))
            resp = RedirectResponse(url=f"/login?expired=1&next={next_q}", status_code=302)
            resp.set_cookie(
                key="__session_expired",
                value="1",
                max_age=30,
                path="/",
                secure=False,
                httponly=False,
                samesite="lax",
            )
            return resp

        sess["_last_seen"] = now

    return await call_next(request)

# ---------------- Ép đổi mật khẩu lần đầu ----------------
ENFORCE_CHANGE_WHITELIST = (
    "/account", "/account/change-password", "/api/account/change-password",
    "/login", "/api/login", "/logout", "/api/logout",
    "/health", "/api/health",
    "/auth_login.html",
    "/hutech.png", "/favicon",
    "/static", "/assets",
    "/journal.html",
)

@app.middleware("http")
async def enforce_first_change_password(request: Request, call_next):
    path = request.url.path

    if path.startswith(ENFORCE_CHANGE_WHITELIST) or path.lower().endswith(STATIC_EXTS):
        return await call_next(request)

    sess = request.session if "session" in request.scope else None
    uid = sess.get("uid") if sess else None
    if not uid:
        return await call_next(request)

    must_change = sess.get("must_change_password")
    if must_change is None:
        try:
            db = next(get_db())
            from app.models.user import User
            u = db.get(User, uid)
            must_change = bool(u.must_change_password) if u else False
        except Exception:
            must_change = False
        sess["must_change_password"] = must_change

    if must_change:
        if path.startswith("/api"):
            return JSONResponse(
                {"detail": "Vui lòng đổi mật khẩu trước khi tiếp tục.", "force_change": True},
                status_code=HTTP_403_FORBIDDEN
            )
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

app.include_router(health.router,     prefix="/api", tags=["Health"])
app.include_router(checklist.router,  prefix="/api", tags=["Checklist"])
app.include_router(applicants.router, prefix="/api", tags=["Applicants"])
app.include_router(applicants_batch.router, prefix="/api", tags=["Applicants (batch)"])
app.include_router(batch.router,      prefix="/api", tags=["Batch"])
app.include_router(export.router,     prefix="/api", tags=["Export"])
app.include_router(journal.router,    prefix="/api", tags=["Journal"])

for r in (health.router, checklist.router, applicants.router, applicants_batch.router, batch.router, export.router, journal.router):
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

# ------------ Route chung cho các trang .html (template) ------------
@app.get("/{page_name}.html", response_class=HTMLResponse, include_in_schema=False)
async def render_page(page_name: str, request: Request):
    # map tên file -> key active_page trong layout_ams.html
    active_map = {
        "ams_home": "home",
        "compilation": "compilation",
        "students_list": "students",
        "import_students": "import",
        "journal": "journal",
        "checklist_admin": "checklist",
        "admin_ams": "admin",
    }
    ctx = {
        "request": request,
        "active_page": active_map.get(page_name, page_name),
    }
    return templates.TemplateResponse(f"{page_name}.html", ctx)

# ---------------- Static files ----------------
os.makedirs(settings.receipts_path, exist_ok=True)
app.mount(
    "/static/receipts",
    StaticFiles(directory=str(settings.receipts_path)),
    name="receipts",
)

app.mount(
    "/assets",
    StaticFiles(directory=os.path.join(TEMPLATES_DIR, "assets")),
    name="assets",
)
app.mount(
    "/css",
    StaticFiles(directory=os.path.join(TEMPLATES_DIR, "css")),
    name="css",
)
app.mount(
    "/js",
    StaticFiles(directory=os.path.join(TEMPLATES_DIR, "js")),
    name="js",
)
