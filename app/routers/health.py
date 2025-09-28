# ================================
# file: app/routers/health.py
# ================================
from fastapi import APIRouter
from datetime import datetime

router = APIRouter()

@router.get("/health")
def health():
    return {"ok": True, "time": datetime.utcnow().isoformat()}
