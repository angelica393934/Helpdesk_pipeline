"""
config/settings.py
──────────────────
Membaca semua konfigurasi dari environment variables (.env).
Satu tempat untuk semua config – tidak ada magic string di kode lain.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Database PostgreSQL ────────────────────────────────────
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB   = os.getenv("POSTGRES_DB", "etl_db")
POSTGRES_USER = os.getenv("POSTGRES_USER", "etl_user")
POSTGRES_PASS = os.getenv("POSTGRES_PASSWORD", "etl_pass")

DATABASE_URL = (
    f"postgresql://{POSTGRES_USER}:{POSTGRES_PASS}"
    f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)

# ── Redis / Celery ─────────────────────────────────────────
REDIS_HOST   = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT   = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB     = int(os.getenv("REDIS_DB", "0"))

CELERY_BROKER_URL      = os.getenv("CELERY_BROKER_URL", f"redis://{REDIS_HOST}:{REDIS_PORT}/0")
CELERY_RESULT_BACKEND  = os.getenv("CELERY_RESULT_BACKEND", f"redis://{REDIS_HOST}:{REDIS_PORT}/1")

# ── API Sumber Data ────────────────────────────────────────
API_BASE_URL              = os.getenv("API_BASE_URL", "http://100.106.188.77:7001")
API_LOG_ACTIVITY_ENDPOINT = os.getenv("API_LOG_ACTIVITY_ENDPOINT", "/log_activity")
API_PETUGAS_ENDPOINT      = os.getenv("API_PETUGAS_ENDPOINT", "/petugas")
API_TIMEOUT               = int(os.getenv("API_TIMEOUT", "30"))

# URL lengkap
URL_LOG_ACTIVITY = API_BASE_URL + API_LOG_ACTIVITY_ENDPOINT
URL_PETUGAS      = API_BASE_URL + API_PETUGAS_ENDPOINT

# ── Jadwal ─────────────────────────────────────────────────
SCHEDULE_FETCH_INTERVAL_HOURS = int(os.getenv("SCHEDULE_FETCH_INTERVAL_HOURS", "1"))
SCHEDULE_ETL_HOUR             = int(os.getenv("SCHEDULE_ETL_HOUR", "2"))
SCHEDULE_ETL_MINUTE           = int(os.getenv("SCHEDULE_ETL_MINUTE", "0"))

# ── Logging ────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_DIR   = os.getenv("LOG_DIR", "./logs")