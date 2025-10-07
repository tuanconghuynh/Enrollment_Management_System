# app/models/applicant.py
from sqlalchemy import (
    Column, String, Date, Integer, Boolean, ForeignKey, Text, DateTime, text
)
from sqlalchemy.orm import relationship
from app.db.base import Base

# ================= Applicant =================
class Applicant(Base):
    __tablename__ = "applicants"

    # KHÓA CHÍNH = ma_so_hv (10 số)
    ma_so_hv  = Column(String(10), primary_key=True, index=True)  # PK + unique tự nhiên

    # CHO PHÉP TRÙNG (nullable để nhập dần, KHÔNG unique)
    ma_ho_so = Column(String(64), nullable=True, index=True)

    ngay_nhan_hs = Column(Date, nullable=True)

    ho_ten = Column(String(255), nullable=True)
    email_hoc_vien = Column(String(255), nullable=True)
    ngay_sinh = Column(Date, nullable=True)
    so_dt = Column(String(32), nullable=True)

    nganh_nhap_hoc = Column(String(255), nullable=True)
    dot = Column(String(64), nullable=True)
    khoa = Column(String(64), nullable=True)
    da_tn_truoc_do = Column(String(64), nullable=True)

    ghi_chu = Column(Text, nullable=True)
    nguoi_nhan_ky_ten = Column(String(255), nullable=True)

    status  = Column(String(32), nullable=False, server_default="saved")
    printed = Column(Boolean, nullable=False, server_default=text("0"))

    checklist_version_id = Column(Integer, ForeignKey("checklist_versions.id"), nullable=True)

    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(
        DateTime,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")
    )

    # Quan hệ tới ApplicantDoc qua khóa ma_so_hv
    docs = relationship(
        "ApplicantDoc",
        back_populates="applicant",
        cascade="all, delete-orphan",
        primaryjoin="Applicant.ma_so_hv==ApplicantDoc.applicant_ma_so_hv",
        foreign_keys="ApplicantDoc.applicant_ma_so_hv",
        lazy="selectin",
    )

# ================= ApplicantDoc =================
class ApplicantDoc(Base):
    __tablename__ = "applicant_docs"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # FK theo ma_so_hv (khớp DB hiện tại)
    applicant_ma_so_hv = Column(
        String(10),
        ForeignKey("applicants.ma_so_hv", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
        index=True,
    )

    code = Column(String(64), nullable=True)
    display_name = Column(String(255), nullable=True)
    so_luong = Column(Integer, nullable=True)
    order_no = Column(Integer, nullable=True)

    applicant = relationship(
        "Applicant",
        back_populates="docs",
        primaryjoin="Applicant.ma_so_hv==ApplicantDoc.applicant_ma_so_hv",
        foreign_keys=[applicant_ma_so_hv],
    )
