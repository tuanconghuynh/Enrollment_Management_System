from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db.session import init_db
from .routers import health, checklist, applicants, batch, export

app = FastAPI(title="Admission Check")

# CORS thoải mái (mở file index.html trực tiếp vẫn gọi API được)
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

# Mount KHÔNG prefix (hiện trên /docs)
app.include_router(health.router)
app.include_router(checklist.router)
app.include_router(applicants.router)
app.include_router(batch.router)
app.include_router(export.router)

# Mount bản sao dưới /api nhưng KHÔNG đưa vào OpenAPI (/docs) -> tránh trùng operationId
app.include_router(health.router,     prefix="/api", include_in_schema=False)
app.include_router(checklist.router,  prefix="/api", include_in_schema=False)
app.include_router(applicants.router, prefix="/api", include_in_schema=False)
app.include_router(batch.router,      prefix="/api", include_in_schema=False)
app.include_router(export.router,     prefix="/api", include_in_schema=False)
