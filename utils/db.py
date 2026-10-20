"""
───────────
Koneksi ke PostgreSQL menggunakan SQLAlchemy.
Menyediakan:
  - engine          → untuk pandas read_sql / to_sql
  - get_connection  → context manager untuk raw SQL
"""

from contextlib import contextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
from config.settings import DATABASE_URL
from utils.logger import get_logger

logger = get_logger(__name__)

# Engine SQLAlchemy – pakai NullPool agar koneksi tidak di-cache
# (cocok untuk proses batch/ETL yang tidak butuh persistent connection)
engine = create_engine(
    DATABASE_URL,
    poolclass=NullPool,
    echo=False,
)


@contextmanager
def get_connection():
    """
    Context manager untuk mendapatkan koneksi DB.
    Otomatis commit jika sukses, rollback jika ada error.

    Contoh pemakaian:
        with get_connection() as conn:
            conn.execute(text("SELECT 1"))
    """
    with engine.begin() as conn:
        try:
            yield conn
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error, rollback dilakukan: {e}")
            raise


def execute_query(sql: str, params: dict = None):
    """Jalankan query dan kembalikan semua baris sebagai list of dict."""
    with get_connection() as conn:
        result = conn.execute(text(sql), params or {})
        return [dict(row._mapping) for row in result]


def execute_many(sql: str, rows: list[dict]):
    """Jalankan query untuk banyak baris sekaligus (batch insert/update)."""
    if not rows:
        return
    with get_connection() as conn:
        conn.execute(text(sql), rows)