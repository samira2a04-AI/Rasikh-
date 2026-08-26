import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()

# Default to SQLite for testing; can be overridden via DATABASE_URL env var.
sqlite_url = "sqlite:///./test.db"
# Fallback to PostgreSQL if the user explicitly sets DATABASE_URL.
DEFAULT_POSTGRES_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/rasikh"

DATABASE_URL = os.getenv("DATABASE_URL", sqlite_url)

# Detect if psycopg driver is available; if not, ensure SQLite is used.
try:
    import psycopg  # noqa: F401
except ImportError:
    # psycopg not installed; keep using SQLite.
    pass
else:
    # If user explicitly requested PostgreSQL, keep it; otherwise, stay on SQLite.
    if DATABASE_URL == sqlite_url:
        DATABASE_URL = DEFAULT_POSTGRES_URL
try:
    import psycopg  # noqa: F401
except ImportError:
    DATABASE_URL = sqlite_url
    # Optional: log fallback (omitted for brevity)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

# Enable foreign key constraints for SQLite databases
from sqlalchemy import event
if engine.dialect.name == "sqlite":
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

# Import all models so they register with Base.metadata
import app.models  # noqa: F401

# Ensure tables are created for SQLite (test) databases
if DATABASE_URL.startswith("sqlite"):
    from app.database.base import Base
    Base.metadata.create_all(engine)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)