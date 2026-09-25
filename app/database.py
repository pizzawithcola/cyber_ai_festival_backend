from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import settings


def _postgres_driver_url(url: str) -> str:
    """Force the psycopg2 driver on PostgreSQL URLs.

    SQLAlchemy's default DBAPI for ``postgresql://`` changed across releases
    (psycopg2 → psycopg3), and we install ``psycopg2-binary``. Pin the driver
    explicitly so a fresh dependency resolution can never crash the app at
    import time (production outage on 2026-09-25: a new build resolved
    ``psycopg`` and exited 1 with ModuleNotFoundError).
    """
    for scheme in ("postgresql://", "postgres://"):
        if url.startswith(scheme):
            return "postgresql+psycopg2://" + url[len(scheme):]
    return url


engine = create_engine(
    _postgres_driver_url(settings.database_url),
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
