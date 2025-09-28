# app/db/session.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine.url import make_url
from .base import Base
from ..core.config import settings

# >>> ADD: detect backend & build connect_args
url = make_url(settings.DB_URL)
connect_args = {}
if url.get_backend_name().startswith("mysql"):
    # Ép charset cho PyMySQL để tránh None
    connect_args["charset"] = "utf8mb4"
elif url.get_backend_name().startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    settings.DB_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    pool_recycle=3600,
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
