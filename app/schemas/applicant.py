# app/schemas/applicant.py
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional, List, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


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

    # --- Tên: cho phép nhập theo 1 trong 2 cách ---
    ho_ten: Optional[str] = Field(
        default=None, description="Họ tên đầy đủ (fallback nếu không dùng ho_dem/ten)."
    )
    ho_dem: Optional[str] = Field(default=None, description="Họ và tên đệm")
    ten: Optional[str] = Field(default=None, description="Tên (given name)")

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

    # Bổ sung để đồng bộ với model/router
    gioi_tinh: Optional[str] = None  # "Nam"/"Nữ"/...
    dan_toc: Optional[str] = None

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

    @model_validator(mode="after")
    def _validate_name_presence(self):
        """
        Ít nhất phải có ho_ten hoặc (ho_dem và ten).
        Cho phép FE chỉ gửi ho_ten (cũ) hoặc tách đôi (mới).
        """
        ht = (self.ho_ten or "").strip()
        ln = (self.ho_dem or "").strip()
        fn = (self.ten or "").strip()
        if not ht and not (ln and fn):
            raise ValueError("Phải nhập ho_ten hoặc bộ đôi ho_dem + ten")
        return self


# ========= Cập nhật (PATCH) =========
class ApplicantUpdate(BaseModel):
    # tất cả đều Optional => PATCH phần nào gửi phần đó
    ma_ho_so: Optional[str] = None
    ngay_nhan_hs: Optional[date] = None

    # Tên: hỗ trợ cả cách cũ (ho_ten) và tách đôi (ho_dem, ten)
    ho_ten: Optional[str] = None
    ho_dem: Optional[str] = None
    ten: Optional[str] = None

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

    # Bổ sung để đồng bộ với model/router
    gioi_tinh: Optional[str] = None
    dan_toc: Optional[str] = None

    checklist_version_name: Optional[str] = None

    # cập nhật tài liệu: mặc định là "merge"
    docs_mode: Literal["merge", "replace"] = "merge"
    docs: Optional[List[ApplicantDocUpdate]] = None

    @field_validator("ma_ho_so", mode="before")
    @classmethod
    def _normalize_ma_ho_so_update(cls, v):
        if v is None:
            return None
        s = str(v).strip()
        if s == "":
            return None
        if re.fullmatch(r"\d{1,4}", s):
            return s.zfill(4)
        return s

    @field_validator("ma_so_hv")
    @classmethod
    def _validate_ma_so_hv_update(cls, v):
        if v is None:
            return v
        s = str(v).strip()
        if not re.fullmatch(r"\d{10}", s):
            raise ValueError("ma_so_hv phải gồm đúng 10 chữ số")
        return s


# ========= Out (payload trả về gọn) =========
class ApplicantOut(BaseModel):
    # Nếu API khác vẫn trả id thì để Optional
    id: Optional[int] = None
    ma_so_hv: str
    ma_ho_so: Optional[str] = None
    status: str
    printed: bool
    

# ========= Dùng cho GET chi tiết (phục vụ UI sửa hồ sơ) =========
class ApplicantDocOut(BaseModel):
    code: str
    so_luong: int


class ApplicantDetailOut(BaseModel):
    id: Optional[int] = None
    ma_so_hv: str
    ma_ho_so: Optional[str] = None
    ngay_nhan_hs: Optional[date] = None

    # Tên (đủ bộ để FE hiển thị/chỉnh sửa)
    ho_ten: Optional[str] = None
    ho_dem: Optional[str] = None
    ten: Optional[str] = None

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

    # Bổ sung để đồng bộ với API
    gioi_tinh: Optional[str] = None
    dan_toc: Optional[str] = None

    checklist_version_name: Optional[str] = None
    status: str
    printed: bool
    docs: List[ApplicantDocOut] = Field(default_factory=list)

    class Config:
        # Pydantic v2: dùng from_attributes thay cho orm_mode
        from_attributes = True
        json_encoders = {
            date: lambda v: v.strftime("%d/%m/%Y") if v else None,
            datetime: lambda v: v.strftime("%d/%m/%Y") if v else None,
        }


class ApplicantListItem(BaseModel):
    id: Optional[int] = None
    ma_so_hv: Optional[str] = None
    ma_ho_so: Optional[str] = None

    # Tên để list hiển thị
    ho_ten: Optional[str] = None
    ho_dem: Optional[str] = None
    ten: Optional[str] = None

    ngay_nhan_hs: Optional[date] = None
    nganh_nhap_hoc: Optional[str] = None
    dot: Optional[str] = None
    khoa: Optional[str] = None
    nguoi_nhan_ky_ten: Optional[str] = None

    gioi_tinh: Optional[str] = None
    dan_toc: Optional[str] = None

    class Config:
        from_attributes = True
