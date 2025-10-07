# Aggregator: cho phép "from app.models import Applicant, ApplicantDoc, ChecklistItem, ..."

from app.db.base import Base

from .applicant import Applicant, ApplicantDoc
from .checklist import ChecklistItem, ChecklistVersion
from .user import User
from .user_models import Student, Application

__all__ = [
    "Base",
    "Applicant",
    "ApplicantDoc",
    "ChecklistItem",
    "ChecklistVersion",
    "User",
    "Student",
    "Application",
]
