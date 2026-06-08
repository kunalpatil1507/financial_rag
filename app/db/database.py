from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

if settings.DATABASE_URL.startswith("sqlite"):
    # SQLite (including in-memory) should use a StaticPool so the in-memory DB
    # is preserved across connections within the same process (useful for tests).
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        settings.DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
else:
    engine = create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables."""
    from app.models import user, document, role  # noqa: F401
    Base.metadata.create_all(bind=engine)
