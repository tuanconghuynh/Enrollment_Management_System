# ================================
# file: app/schemas/checklist.py
# ================================
from pydantic import BaseModel
from typing import List

class ChecklistItemOut(BaseModel):
    code: str
    display_name: str
    default_qty: int | None = None
    order_no: int | None = None

class ChecklistActiveOut(BaseModel):
    version_name: str
    items: List[ChecklistItemOut]
