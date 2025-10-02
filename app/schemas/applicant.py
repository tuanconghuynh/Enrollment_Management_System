from pydantic import BaseModel
from typing import Optional, List, Literal
from datetime import date
from pydantic import BaseModel

# ---- Docs (tài liệu kèm hồ sơ) ----
class ApplicantDocIn(BaseModel):
    code: str
    # 0,1,2...; None nghĩa là KHÔNG gửi field này (tạo mới sẽ bỏ qua)
    so_luong: Optional[int] = None

class ApplicantDocUpdate(BaseModel):
    code: str
    # 0,1,2...; None nghĩa là KHÔNG thay đổi mục này khi PATCH (merge)
    so_luong: Optional[int] = None


# ---- Tạo mới ----
class ApplicantIn(BaseModel):
    # BẮT BUỘC
    ma_ho_so: str
    ngay_nhan_hs: str          # 'YYYY-MM-DD' (MySQL nhận được vào DATE/DATETIME)
    ho_ten: str
    ma_so_hv: str

    # TUỲ CHỌN
    ngay_sinh: Optional[str] = None         # 'YYYY-MM-DD' hoặc chuỗi
    so_dt: Optional[str] = None
    nganh_nhap_hoc: Optional[str] = None
    dot: Optional[str] = None
    khoa: Optional[str] = None              # dùng cho tiêu đề/in
    bien_nhan_nhap_hoc: Optional[str] = None
    da_tn_truoc_do: Optional[str] = None
    ghi_chu: Optional[str] = None
    nguoi_nhan_ky_ten: Optional[str] = None

    checklist_version_name: str
    docs: List[ApplicantDocIn]


# ---- Cập nhật (PATCH) ----
class ApplicantUpdate(BaseModel):
    # tất cả đều Optional => PATCH phần nào gửi phần đó
    ma_ho_so: Optional[str] = None
    ngay_nhan_hs: Optional[str] = None
    ho_ten: Optional[str] = None
    ma_so_hv: Optional[str] = None

    ngay_sinh: Optional[str] = None
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


# ---- Out ----
class ApplicantOut(BaseModel):
    id: int
    ma_ho_so: str
    status: str
    printed: bool


# Dùng cho GET chi tiết (phục vụ UI sửa hồ sơ)
class ApplicantDocOut(BaseModel):
    code: str
    so_luong: int

class ApplicantDetailOut(BaseModel):
    id: int
    ma_ho_so: str
    ngay_nhan_hs: Optional[str] = None
    ho_ten: str
    ma_so_hv: str
    ngay_sinh: Optional[str] = None
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
    docs: List[ApplicantDocOut]

class ApplicantListItem(BaseModel):
    id: int
    ma_ho_so: str
    ho_ten: str | None = None
    ma_so_hv: str | None = None
    ngay_nhan_hs: date | None = None
    nganh_nhap_hoc: str | None = None
    dot: str | None = None
    khoa: str | None = None
    nguoi_nhan_ky_ten: str | None = None

    class Config:
        orm_mode = True