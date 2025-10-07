from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text, func
)
from ..db.base import Base

class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_code = Column(String(64), unique=True, nullable=False)
    full_name = Column(String(128), nullable=False)
    dob = Column(String(10))
    gender = Column(String(16))
    phone = Column(String(32))
    email = Column(String(128))
    id_number = Column(String(64))
    address = Column(String(255))
    note = Column(Text)
    created_by_user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<Student(id={self.id}, code='{self.student_code}', name='{self.full_name}')>"


class Application(Base):
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    program = Column(String(128))
    intake = Column(String(64))
    status = Column(String(32), default="Draft")
    documents_json = Column(Text)
    assigned_to_user_id = Column(Integer, ForeignKey("users.id"))
    last_modified_by_user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<Application(id={self.id}, student_id={self.student_id}, status='{self.status}')>"
