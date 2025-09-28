# ================================
# file: app/models/applicant.py
# ================================
from sqlalchemy import Column, Integer, String, Date, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from ..db.base import Base
from sqlalchemy import Column, Integer, String, Date, Boolean, DateTime, ForeignKey

class Applicant(Base):
    __tablename__ = "applicants"
    id = Column(Integer, primary_key=True)
    ma_ho_so = Column(String(64), unique=True, index=True)
    bien_nhan_nhap_hoc = Column(Text)
    ngay_nhan_hs = Column(Date, index=True)

    ho_ten = Column(String(255), nullable=False)
    ma_so_hv = Column(String(64), nullable=False, index=True)
    ngay_sinh = Column(String(32))
    so_dt = Column(String(64))
    nganh_nhap_hoc = Column(String(255))
    dot = Column(String(64))
    khoa = Column(String(50), nullable=True) 
    da_tn_truoc_do = Column(String(32))

    ghi_chu = Column(Text)
    nguoi_nhan_ky_ten = Column(String(255))

    checklist_version_id = Column(Integer, ForeignKey("checklist_versions.id"))

    status = Column(String(16), default="saved")  # saved | printed
    printed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    docs = relationship("ApplicantDoc", back_populates="applicant", cascade="all, delete-orphan")

class ApplicantDoc(Base):
    __tablename__ = "applicant_docs"
    id = Column(Integer, primary_key=True)
    applicant_id = Column(Integer, ForeignKey("applicants.id", ondelete="CASCADE"))
    code = Column(String(64))
    display_name = Column(String(255))
    so_luong = Column(Integer, default=0)
    order_no = Column(Integer, default=0)
    applicant = relationship("Applicant", back_populates="docs")
    