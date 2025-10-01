from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .db.session import init_db
from .routers import health, checklist, applicants, batch, export

app = FastAPI(title="AdmissionCheck", docs_url="/api/docs", redoc_url=None)

# CORS thoải mái
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    init_db()

# ===== API CHÍNH dưới /api =====
app.include_router(health.router,     prefix="/api", tags=["Health"])
app.include_router(checklist.router,  prefix="/api", tags=["Checklist"])
app.include_router(applicants.router, prefix="/api", tags=["Applicants"])
app.include_router(batch.router,      prefix="/api", tags=["Batch"])
app.include_router(export.router,     prefix="/api", tags=["Export"])


# ===== Alias KHÔNG /api (nếu web cũ đang gọi đường cũ) =====
app.include_router(health.router,     prefix="", include_in_schema=False)
app.include_router(checklist.router,  prefix="", include_in_schema=False)
app.include_router(applicants.router, prefix="", include_in_schema=False)
app.include_router(batch.router,      prefix="", include_in_schema=False)
app.include_router(export.router,     prefix="", include_in_schema=False)
app.include_router(applicants.router, prefix="/api/applicants", tags=["Applicants"])
app.include_router(export.router, prefix="/api", tags=["Export"])
app.include_router(export.router,     prefix="/api") 




# Health đơn giản
@app.get("/health", include_in_schema=False)
@app.get("/api/health", include_in_schema=False)
def health_check():
    return {"ok": True}

# In routes để kiểm tra
for r in app.routes:
    try:
        print("ROUTE:", r.path, r.methods)
    except Exception:
        pass

# ========= MOUNT STATIC Ở CUỐI CÙNG =========
# Serve giao diện web tại /
app.mount("/", StaticFiles(directory="web", html=True), name="web")
