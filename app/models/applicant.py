from sqlalchemy import (
    Column, String, Date, Integer, Boolean, ForeignKey, Text, DateTime, text, func
)
from sqlalchemy.orm import relationship
from sqlalchemy.ext.hybrid import hybrid_property
from app.db.base import Base

class Applicant(Base):
    __tablename__ = "applicants"

    ma_so_hv  = Column(String(10), primary_key=True, index=True)
    ma_ho_so  = Column(String(64), nullable=True, index=True)
    ngay_nhan_hs = Column(Date, nullable=True)

    # Cũ: giữ để tương thích
    ho_ten = Column(String(255), nullable=True)

    # Mới: tách tên
    ho_dem = Column(String(255), nullable=True, index=True)
    ten    = Column(String(100), nullable=True, index=True)

    gioi_tinh = Column(String(10), nullable=True)
    email_hoc_vien = Column(String(255), nullable=True)
    ngay_sinh = Column(Date, nullable=True)
    dan_toc = Column(String(64), nullable=True)
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

    # Quan hệ
    docs = relationship(
        "ApplicantDoc",
        back_populates="applicant",
        cascade="all, delete-orphan",
        primaryjoin="Applicant.ma_so_hv==ApplicantDoc.applicant_ma_so_hv",
        foreign_keys="ApplicantDoc.applicant_ma_so_hv",
        lazy="selectin",
    )

    # ---- Hiển thị 'full_name' thống nhất (ưu tiên ho_dem + ten, fallback ho_ten cũ) ----
    @hybrid_property
    def full_name(self) -> str:
        hd = (self.ho_dem or '').strip()
        t  = (self.ten or '').strip()
        if hd or t:
            return (hd + ' ' + t).strip()
        return (self.ho_ten or '').strip()

    @full_name.expression
    def full_name(cls):
        # Cho ORDER BY / ILIKE trên SQL side
        return func.trim(
            func.concat(
                func.coalesce(cls.ho_dem, ''), ' ', func.coalesce(cls.ten, '')
            )
        )


class ApplicantDoc(Base):
    __tablename__ = "applicant_docs"

    id = Column(Integer, primary_key=True, autoincrement=True)
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
