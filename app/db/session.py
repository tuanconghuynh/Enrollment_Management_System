# app/db/session.py
import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import OperationalError

from .base import Base
from ..core.config import settings

log = logging.getLogger("db")

# lấy URL từ cấu hình / .env, fallback SQLite nếu chưa đặt
DB_URL = getattr(settings, "DB_URL", None) or os.getenv("DB_URL") or "sqlite:///./app.db"

def _make_engine(url_str: str):
    url = make_url(url_str)
    connect_args = {}
    if url.get_backend_name().startswith("sqlite"):
        connect_args["check_same_thread"] = False
    elif url.get_backend_name().startswith("mysql"):
        # với PyMySQL, charset nên có trong query string,
        # nhưng để chắc ăn vẫn truyền xuống DBAPI connect()
        connect_args["charset"] = "utf8mb4"

    return create_engine(
        url_str,
        connect_args=connect_args,
        pool_pre_ping=True,
        pool_recycle=3600,
        future=True,
    )

# engine ban đầu theo cấu hình
engine = _make_engine(DB_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

def init_db():
    """Tạo bảng; nếu MySQL không kết nối được và cho phép fallback thì rơi sang SQLite."""
    global engine, SessionLocal

    try:
        Base.metadata.create_all(bind=engine)
        log.info("DB init OK with %s", DB_URL)
        return
    except OperationalError as e:
        backend = make_url(DB_URL).get_backend_name()
        log.error("DB init failed on %s: %s", backend, e)

        # Cho phép fallback khi MySQL chết: đặt FALLBACK_SQLITE=1 trong .env nếu muốn bật
        allow_fallback = os.getenv("FALLBACK_SQLITE", "0") == "1"
        if backend.startswith("mysql") and allow_fallback:
            fallback_url = "sqlite:///./app.db"
            log.warning("Falling back to SQLite: %s", fallback_url)
            engine = _make_engine(fallback_url)
            SessionLocal.configure(bind=engine)
            Base.metadata.create_all(bind=engine)
        else:
            # không fallback -> ném lỗi để app báo fail
            raise

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
