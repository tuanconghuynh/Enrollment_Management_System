# ================================
# file: app/utils/datetime.py
# ================================
from datetime import datetime, timezone
def now_str() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%d/%m/%Y %H:%M")
