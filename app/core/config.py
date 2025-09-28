# ================================
# file: app/core/config.py
# ================================
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # DB mặc định: bạn có thể override bằng biến môi trường DB_URL hoặc file .env
    DB_URL: str = "mysql+pymysql://root:@localhost:3306/admission_check?charset=utf8mb4"

    # Đường dẫn font Times New Roman (có thể override bằng ENV)
    FONT_PATH: str = "assets/TimesNewRoman.ttf"
    FONT_PATH_BOLD: str = "assets/TimesNewRoman-Bold.ttf"

    # Pydantic v2: cấu hình đọc .env, bỏ qua biến lạ
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

# Tạo singleton settings cho toàn app
settings = Settings()
