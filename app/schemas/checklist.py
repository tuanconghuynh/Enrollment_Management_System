# ================================
# file: app/schemas/checklist.py
# ================================
from pydantic import BaseModel
from typing import List

class ChecklistItemOut(BaseModel):
    code: str
    display_name: str
    default_qty: int
    order_no: int

class ChecklistActiveOut(BaseModel):
    version: str
    items: List[ChecklistItemOut]