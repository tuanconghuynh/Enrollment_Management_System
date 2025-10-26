# Project AdmissionCheck

Quản trị & kiểm tra hồ sơ tuyển sinh (AdmissionCheck) — nền tảng nội bộ giúp nhập liệu hàng loạt từ Excel/CSV, kiểm tra điều kiện/thiếu sót, sinh mã QR phục vụ xác thực tại quầy, và xuất báo cáo nhanh.

> 🗂 Cấu trúc repo cho thấy dự án gồm **backend Python/FastAPI**, **frontend web**, kịch bản khởi chạy `.bat`, script DB `init_db.sql`, thư mục `Database/` để lưu mẫu dữ liệu và `assets/` (static). (Xem các mục `app/`, `web/`, `scripts/`, `init_db.sql`, `requirements.txt` trong repo.)

---

## ✨ Tính năng chính

- **Nhập dữ liệu hàng loạt** từ Excel/CSV, tự ánh xạ cột, kiểm tra hợp lệ dữ liệu (bắt buộc/định dạng/ngày tháng).
- **Tra cứu & tìm kiếm nhanh** thí sinh/hồ sơ theo nhiều tiêu chí.
- **Sinh/hiển thị QR** để đối chiếu và xác thực nhanh tại điểm tiếp nhận.
- **Bộ quy tắc kiểm tra** linh hoạt (ví dụ: thiếu giấy tờ, sai định dạng CCCD, điều kiện xét tốt nghiệp…).
- **Xuất báo cáo** theo đợt/khoa/kỳ, xuất Excel/PDF.
- **Quản trị người dùng & phân quyền** cơ bản (staff/admin), nhật ký thao tác.

> Ghi chú: Một số tính năng có thể đang triển khai dở dang — điều chỉnh mô tả theo tiến độ thực tế của repo.

---

## 🏗 Kiến trúc tổng quan

- **Backend**: Python (FastAPI), Uvicorn, phụ trợ ORM/DB (SQL dùng qua `init_db.sql`), tiện ích `extensions.py`, `make_hash.py`.
- **Frontend**: Ứng dụng web (thư mục `web/`).
- **CSDL**: Khởi tạo bằng `init_db.sql` (khuyến nghị PostgreSQL hoặc MySQL tuỳ môi trường).
- **Scripts**: `run_server.bat`, `stop_server.bat`, `run_all_windows.bat` để chạy nhanh trên Windows.
- **Khác**: `assets/` (static), `Database/admission_check/` (mẫu/seed), `.vscode/` (dev), `.env` (biến môi trường — **không commit**), `.venv/` (virtual env — **không commit**).

---

## 🚀 Bắt đầu nhanh (Local Dev)

### 1) Yêu cầu

- **Python** ≥ 3.10
- **Node.js** ≥ 18 (nếu chạy frontend `web/`)
- **PostgreSQL** hoặc **MySQL** (khuyến nghị Postgres)
- **Git**

### 2) Clone & thiết lập môi trường

```bash
# Clone
git clone https://github.com/tuanconghuynh/Project_AdmissionCheck.git
cd Project_AdmissionCheck

# Python venv
python -m venv .venv
# Windows
.\.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

# Cài thư viện backend
pip install -r requirements.txt

# Biến môi trường
# Tạo file .env từ mẫu (nếu có .env.example)
# và cập nhật các biến kết nối DB, JWT_SECRET, v.v.
```

### 3) Khởi tạo CSDL

```bash
# Ví dụ với PostgreSQL
# tạo DB trước rồi import schema
psql -U <user> -d <database_name> -f init_db.sql
```

> Nếu dùng MySQL, chuyển lệnh tương đương (`mysql -u <user> -p <db> < init_db.sql>`). Điều chỉnh câu lệnh DDL nếu cần.

### 4) Chạy backend

```bash
# Tuỳ entrypoint (ví dụ app.main:app)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Hoặc dùng script Windows có sẵn:

```bat
run_server.bat
```

API mặc định: `http://localhost:8000` (OpenAPI Docs: `/docs`).

### 5) Chạy frontend (nếu có)

```bash
cd web
npm install
npm run dev
# mở http://localhost:3000
```

---

## ⚙️ Cấu hình `.env` (ví dụ)

Tạo file `.env` ở thư mục gốc (đừng commit):

```
# Database
DB_DRIVER=postgresql
DB_HOST=localhost
DB_PORT=5432
DB_NAME=admission_check
DB_USER=postgres
DB_PASSWORD=postgres

# App
APP_ENV=development
APP_HOST=0.0.0.0
APP_PORT=8000

# Security
JWT_SECRET=change-me
JWT_EXPIRES=86400
ALLOWED_ORIGINS=http://localhost:3000
```

> Thực tế tên biến có thể khác — đối chiếu trong mã nguồn `app/` và các tiện ích đọc config.

---

## 📁 Cấu trúc thư mục (rút gọn)

```
Project_AdmissionCheck/
├─ app/                    # Source backend (FastAPI, routers, services, models)
├─ web/                    # Source frontend (SPA/Next.js/Vite — tuỳ thực tế)
├─ scripts/                # Script tiện ích (chạy server, stop, batch…)
├─ Database/admission_check/ # Mẫu dữ liệu / seed / dump
├─ assets/                 # Static assets (hình ảnh, fonts, …)
├─ init_db.sql             # DDL/seed khởi tạo CSDL
├─ requirements.txt        # Python deps
├─ run_server.bat          # Chạy nhanh backend (Windows)
├─ stop_server.bat         # Dừng server (Windows)
├─ run_all_windows.bat     # Chạy nhiều dịch vụ 1 lần (Windows)
└─ .env                    # Biến môi trường (không commit)
```

---

## 🧪 Kiểm thử

- **Unit test**: đề xuất `pytest` cho backend.
- **API test**: dùng `pytest` + `httpx` hoặc Postman/Insomnia collections.
- **E2E**: với frontend, có thể dùng Playwright/Cypress (tuỳ stack).

---

## 📦 Build & Deploy

- **Backend**: build Docker image hoặc deploy dịch vụ Uvicorn/Gunicorn + reverse proxy (Nginx/Caddy).
- **DB**: quản lý migration (khuyến nghị Alembic).
- **Frontend**: build tĩnh (`npm run build`) rồi deploy lên bất kỳ hosting tĩnh hoặc reverse proxy.
- **Env**: tách `development`/`staging`/`production` qua file env hoặc secret manager.

Ví dụ Docker (tham khảo):

```dockerfile
# Backend
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY ./app ./app
ENV APP_HOST=0.0.0.0 APP_PORT=8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 📝 Quy ước code & commit

- **Style**: black, isort, flake8 (đề xuất)
- **Conventional Commits**: `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`…
- **Branching**: `main` (stable), `dev`, `feature/*`, `hotfix/*`.

---

## 🔐 Bảo mật & dữ liệu nhạy cảm

- **Không commit**: `.env`, `.venv`, token, dump dữ liệu thật.
- Thêm/hoàn thiện **.gitignore** cho Python/Node/OS.
- Xoá lịch sử file nhạy cảm đã lỡ commit (nếu có) bằng `git filter-repo` hoặc GitHub secret scanning.

---

## 🗺 Roadmap gợi ý

-

---

## 🤝 Đóng góp

1. Fork repo
2. Tạo nhánh `feature/<ten>`
3. Commit theo Conventional Commits
4. Mở Pull Request

---

## 📄 License

Cập nhật loại giấy phép (MIT/GPL/Proprietary…) theo nhu cầu dự án.

---

## 📞 Liên hệ

- Chủ dự án: cập nhật tên/email
- Vấn đề kỹ thuật: mở **Issues** trên GitHub

---

> **Lưu ý:** README này là khung hoàn chỉnh để khởi động nhanh. Tuỳ code thực tế trong `app/` và `web/`, mình sẽ tinh chỉnh phần **entrypoint**, **biến môi trường**, **DB** và **hướng dẫn deploy** cho khớp 100%.

