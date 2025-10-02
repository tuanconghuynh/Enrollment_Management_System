# app/models/__init__.py
# Aggregator: cho phép "from app.models import Applicant, ApplicantDoc, ChecklistItem"
from app.db.base import Base

from .applicant import Applicant, ApplicantDoc
from .checklist import ChecklistItem

# Nếu anh có thêm model khác (vd: User) thì import ở đây
try:
    from .user import User  # optional
except Exception:
    pass

__all__ = [
    "Base",
    "Applicant",
    "ApplicantDoc",
    "ChecklistItem",
    "User",
]
