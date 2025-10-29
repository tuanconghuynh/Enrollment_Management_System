# app/schemas/applicant.py
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional, List, Literal

from pydantic import BaseModel, Field, field_validator


# ========= Docs (tài liệu kèm hồ sơ) =========
class ApplicantDocIn(BaseModel):
    code: str
    # 0,1,2...; None nghĩa là KHÔNG gửi field này (tạo mới sẽ bỏ qua)
    so_luong: Optional[int] = None


class ApplicantDocUpdate(BaseModel):
    code: str
    # 0,1,2...; None nghĩa là KHÔNG thay đổi mục này khi PATCH (merge)
    so_luong: Optional[int] = None


# ========= Tạo mới =========
class ApplicantIn(BaseModel):
    # CHO PHÉP BỎ TRỐNG
    ma_ho_so: Optional[str] = Field(
        default=None, description="Mã hồ sơ (có thể để trống)."
    )

    ho_ten: str
    # PK tự nhiên: bắt buộc đủ 10 chữ số
    ma_so_hv: str
    ngay_nhan_hs: date

    email_hoc_vien: Optional[str] = None
    ngay_sinh: Optional[date] = None
    so_dt: Optional[str] = None
    nganh_nhap_hoc: Optional[str] = None
    dot: Optional[str] = None
    khoa: Optional[str] = None
    da_tn_truoc_do: Optional[str] = None
    ghi_chu: Optional[str] = None
    nguoi_nhan_ky_ten: Optional[str] = None

    # dùng model con + default_factory để tránh mutable default
    docs: List[ApplicantDocIn] = Field(default_factory=list)
    checklist_version_name: Optional[str] = None

    # ---- Validators ----
    @field_validator("ma_ho_so", mode="before")
    @classmethod
    def _normalize_ma_ho_so(cls, v):
        """Cho phép None hoặc chuỗi rỗng -> None. Nếu đưa số 1–4 chữ số thì pad về 4."""
        if v is None:
            return None
        s = str(v).strip()
        if s == "":
            return None
        # Nếu nhập 1–4 chữ số, pad về 4 để thống nhất; các format khác giữ nguyên
        if re.fullmatch(r"\d{1,4}", s):
            return s.zfill(4)
        return s

    @field_validator("ma_so_hv")
    @classmethod
    def _validate_ma_so_hv(cls, v):
        s = str(v).strip()
        if not re.fullmatch(r"\d{10}", s):
            raise ValueError("ma_so_hv phải gồm đúng 10 chữ số")
        return s


# ========= Cập nhật (PATCH) =========
class ApplicantUpdate(BaseModel):
    # tất cả đều Optional => PATCH phần nào gửi phần đó
    ma_ho_so: Optional[str] = None
    ngay_nhan_hs: Optional[date] = None
    ho_ten: Optional[str] = None
    ma_so_hv: Optional[str] = None
    email_hoc_vien: Optional[str] = None
    ngay_sinh: Optional[date] = None      # FE nên gửi ISO YYYY-MM-DD
    so_dt: Optional[str] = None
    nganh_nhap_hoc: Optional[str] = None
    dot: Optional[str] = None
    khoa: Optional[str] = None
    bien_nhan_nhap_hoc: Optional[str] = None
    da_tn_truoc_do: Optional[str] = None
    ghi_chu: Optional[str] = None
    nguoi_nhan_ky_ten: Optional[str] = None

    checklist_version_name: Optional[str] = None

    # cập nhật tài liệu: mặc định là "merge"
    docs_mode: Literal["merge", "replace"] = "merge"
    docs: Optional[List[ApplicantDocUpdate]] = None


# ========= Out (payload trả về) =========
class ApplicantOut(BaseModel):
    # Nếu API khác vẫn trả id thì để Optional
    id: Optional[int] = None
    ma_so_hv: str
    ma_ho_so: Optional[str] = None
    status: str
    printed: bool


# Dùng cho GET chi tiết (phục vụ UI sửa hồ sơ)
class ApplicantDocOut(BaseModel):
    code: str
    so_luong: int


class ApplicantDetailOut(BaseModel):
    id: Optional[int] = None
    ma_so_hv: str
    ma_ho_so: Optional[str] = None
    ngay_nhan_hs: Optional[date] = None
    ho_ten: Optional[str] = None
    ma_so_hv_display: Optional[str] = None  # nếu cần hiển thị khác
    email_hoc_vien: Optional[str] = None
    ngay_sinh: Optional[date] = None
    so_dt: Optional[str] = None
    nganh_nhap_hoc: Optional[str] = None
    dot: Optional[str] = None
    khoa: Optional[str] = None
    bien_nhan_nhap_hoc: Optional[str] = None
    da_tn_truoc_do: Optional[str] = None
    ghi_chu: Optional[str] = None
    nguoi_nhan_ky_ten: Optional[str] = None
    checklist_version_name: Optional[str] = None
    status: str
    printed: bool
    docs: List[ApplicantDocOut] = Field(default_factory=list)

    class Config:
        orm_mode = True
        json_encoders = {
            date: lambda v: v.strftime("%d/%m/%Y") if v else None,
            datetime: lambda v: v.strftime("%d/%m/%Y") if v else None,
        }


class ApplicantListItem(BaseModel):
    id: Optional[int] = None
    ma_so_hv: Optional[str] = None
    ma_ho_so: Optional[str] = None
    ho_ten: Optional[str] = None
    ngay_nhan_hs: Optional[date] = None
    nganh_nhap_hoc: Optional[str] = None
    dot: Optional[str] = None
    khoa: Optional[str] = None
    nguoi_nhan_ky_ten: Optional[str] = None

    class Config:
        orm_mode = True
