"""
tasks/celery_app.py
───────────────────
Konfigurasi Celery + definisi semua task.

Task yang tersedia:
  1. task_fetch_data       → Extract dari API (jalan tiap 1 jam)
  2. task_run_etl          → Full ETL: extract + transform (jalan tiap malam)
  3. task_run_transform    → Transform saja (dari data yang sudah di-raw)
"""

from celery import Celery
from celery.schedules import crontab
from datetime import timedelta

from config.settings import (
    CELERY_BROKER_URL,
    CELERY_RESULT_BACKEND,
    SCHEDULE_FETCH_INTERVAL_HOURS,
    SCHEDULE_ETL_HOUR,
    SCHEDULE_ETL_MINUTE,
)
from utils.logger import get_logger

logger = get_logger(__name__)

# ── Inisialisasi Celery ────────────────────────────────────────
app = Celery(
    "etl_tasks",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
)

app.conf.update(
    # Serialisasi
    task_serializer    = "json",
    result_serializer  = "json",
    accept_content     = ["json"],

    # Timezone
    timezone           = "Asia/Jakarta",
    enable_utc         = True,

    # Queue
    task_default_queue = "etl_queue",
    task_queues        = {
        "etl_queue": {},
        "priority_queue": {},
    },

    # Retry
    task_acks_late           = True,
    task_reject_on_worker_lost = True,

    # Result
    result_expires = 86400,  # 24 jam

    # Beat schedule
    beat_schedule = {
        # Ambil data dari API setiap N jam
        "fetch-data-every-hour": {
            "task": "tasks.celery_app.task_fetch_data",
            "schedule": timedelta(hours=SCHEDULE_FETCH_INTERVAL_HOURS),
            "options": {"queue": "etl_queue"},
        },
        # Full ETL setiap malam (jam 02:00 WIB)
        "run-etl-nightly": {
            "task": "tasks.celery_app.task_run_etl",
            "schedule": crontab(
                hour   = SCHEDULE_ETL_HOUR,
                minute = SCHEDULE_ETL_MINUTE,
            ),
            "options": {"queue": "etl_queue"},
        },
    },
)


# ──────────────────────────────────────────────────────────────
# TASK 1: Fetch data dari API (Extract saja)
# ──────────────────────────────────────────────────────────────

@app.task(
    name="tasks.celery_app.task_fetch_data",
    bind=True,
    max_retries=3,
    default_retry_delay=300,  # retry setelah 5 menit
)
def task_fetch_data(self):
    """
    Task: Ambil data terbaru dari API dan simpan ke raw tables.
    Dijalankan tiap N jam oleh Celery Beat.
    """
    from etl.extractor import run_extract
    from utils.db import get_connection
    from sqlalchemy import text

    logger.info(f"[TASK] task_fetch_data dimulai (attempt {self.request.retries + 1})")

    # Log ke etl_run_log
    with get_connection() as conn:
        result = conn.execute(
            text("INSERT INTO etl_run_log (task_name, status) VALUES ('task_fetch_data', 'running') RETURNING id")
        )
        log_id = result.scalar()

    try:
        extract_result = run_extract()

        # Update log sukses
        with get_connection() as conn:
            conn.execute(text("""
                UPDATE etl_run_log
                SET status = 'success',
                    rows_fetched = :fetched,
                    rows_new     = :new,
                    finished_at  = NOW()
                WHERE id = :log_id
            """), {
                "fetched": extract_result["log_activity_new"] + extract_result["petugas_new"],
                "new":     extract_result["log_activity_new"],
                "log_id":  log_id,
            })

        logger.info(f"[TASK] task_fetch_data selesai: {extract_result}")
        return extract_result

    except Exception as e:
        # Update log gagal
        with get_connection() as conn:
            conn.execute(text("""
                UPDATE etl_run_log
                SET status = 'failed', error_msg = :err, finished_at = NOW()
                WHERE id = :log_id
            """), {"err": str(e)[:500], "log_id": log_id})

        logger.error(f"[TASK] task_fetch_data gagal: {e}")
        raise self.retry(exc=e)


# ──────────────────────────────────────────────────────────────
# TASK 2: Transform saja (dari data raw yang sudah ada)
# ──────────────────────────────────────────────────────────────

@app.task(
    name="tasks.celery_app.task_run_transform",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def task_run_transform(self):
    """
    Task: Jalankan proses Transform + Load dari data raw yang sudah ada.
    Bisa dipanggil manual atau otomatis setelah fetch.
    """
    from etl.transformer import run_transform
    from utils.db import get_connection
    from sqlalchemy import text

    logger.info("[TASK] task_run_transform dimulai")

    with get_connection() as conn:
        result = conn.execute(
            text("INSERT INTO etl_run_log (task_name, status) VALUES ('task_run_transform', 'running') RETURNING id")
        )
        log_id = result.scalar()

    try:
        transform_result = run_transform()

        with get_connection() as conn:
            conn.execute(text("""
                UPDATE etl_run_log
                SET status = 'success',
                    rows_new    = :rows,
                    finished_at = NOW()
                WHERE id = :log_id
            """), {"rows": transform_result["rows_inserted"], "log_id": log_id})

        logger.info(f"[TASK] task_run_transform selesai: {transform_result}")
        return transform_result

    except Exception as e:
        with get_connection() as conn:
            conn.execute(text("""
                UPDATE etl_run_log
                SET status = 'failed', error_msg = :err, finished_at = NOW()
                WHERE id = :log_id
            """), {"err": str(e)[:500], "log_id": log_id})

        logger.error(f"[TASK] task_run_transform gagal: {e}")
        raise self.retry(exc=e)


# ──────────────────────────────────────────────────────────────
# TASK 3: Full ETL (Extract + Transform)
# ──────────────────────────────────────────────────────────────

@app.task(
    name="tasks.celery_app.task_run_etl",
    bind=True,
    max_retries=2,
    default_retry_delay=120,
)
def task_run_etl(self):
    """
    Task: Full ETL pipeline – Extract lalu Transform.
    Dijalankan tiap malam oleh Celery Beat.
    """
    from etl.extractor import run_extract
    from etl.transformer import run_transform
    from utils.db import get_connection
    from sqlalchemy import text

    logger.info("[TASK] task_run_etl (full pipeline) dimulai")

    with get_connection() as conn:
        result = conn.execute(
            text("INSERT INTO etl_run_log (task_name, status) VALUES ('task_run_etl', 'running') RETURNING id")
        )
        log_id = result.scalar()

    try:
        # Step 1: Extract
        extract_result   = run_extract()
        # Step 2: Transform
        transform_result = run_transform()

        combined = {**extract_result, **transform_result}

        with get_connection() as conn:
            conn.execute(text("""
                UPDATE etl_run_log
                SET status = 'success',
                    rows_fetched = :fetched,
                    rows_new     = :new,
                    finished_at  = NOW()
                WHERE id = :log_id
            """), {
                "fetched": extract_result.get("log_activity_new", 0),
                "new":     transform_result.get("rows_inserted", 0),
                "log_id":  log_id,
            })

        logger.info(f"[TASK] task_run_etl selesai: {combined}")
        return combined

    except Exception as e:
        with get_connection() as conn:
            conn.execute(text("""
                UPDATE etl_run_log
                SET status = 'failed', error_msg = :err, finished_at = NOW()
                WHERE id = :log_id
            """), {"err": str(e)[:500], "log_id": log_id})

        logger.error(f"[TASK] task_run_etl gagal: {e}")
        raise self.retry(exc=e)
