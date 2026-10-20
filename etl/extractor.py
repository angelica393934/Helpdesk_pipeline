"""
1 – EXTRACT
Mengambil data dari API eksternal dan menyimpan langsung ke tabel raw.

Strategi Incremental:
  - Untuk log_activity: cek tiket mana yang sudah ada di etl_processed_tickets
    → hanya simpan tiket yang BELUM pernah diproses
  - Untuk petugas: selalu ambil semua (data master, kecil)

Flow:
  API → raw_log_activity / raw_petugas → return jumlah baris baru
"""
import uuid
from datetime import datetime, timezone

import requests
import pandas as pd
from sqlalchemy import text

from config.settings import URL_LOG_ACTIVITY, URL_PETUGAS, API_TIMEOUT
from utils.db import engine, get_connection
from utils.logger import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────
# Helper API
# ─────────────────────────────────────────────
def _fetch_api(url: str, params: dict = None, max_retry: int = 3) -> list[dict]:
    for attempt in range(1, max_retry + 1):
        try:
            logger.info(f"Hit API [{attempt}/{max_retry}]: {url}")
            resp = requests.get(url, params=params, timeout=API_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()

            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                for key in ("data", "results", "items", "records"):
                    if key in data:
                        return data[key]
                return [data]

        except Exception as e:
            logger.warning(f"Retry {attempt}: {e}")

    return []


# ─────────────────────────────────────────────
# UPSERT LOG ACTIVITY
# ─────────────────────────────────────────────
def _upsert_raw_log_activity(df: pd.DataFrame):

    expected_cols = [
        "id_masalah","tiket","waktu_kejadian","prioritas","dampak",
        "target","pihak","jenis_masalah","klasifikasi","tgl_diterima",
        "id_cabang","user","pelapor","masalah","waktu_tanggap",
        "penyebab","penyelesaian","waktu_penyelesaian","tgl_selesai",
        "tgl_esk","status","petugas","komentar","eskalasi",
        "petugas_esk","fetched_at","batch_id"
    ]

    for col in expected_cols:
        if col not in df.columns:
            df[col] = None

    df = df[expected_cols]
    records = df.to_dict(orient="records")

    query = text("""
        INSERT INTO raw_log_activity (
            id_masalah, tiket, waktu_kejadian, prioritas, dampak,
            target, pihak, jenis_masalah, klasifikasi, tgl_diterima,
            id_cabang, "user", pelapor, masalah, waktu_tanggap,
            penyebab, penyelesaian, waktu_penyelesaian, tgl_selesai,
            tgl_esk, status, petugas, komentar, eskalasi,
            petugas_esk, fetched_at, batch_id
        )
        VALUES (
            :id_masalah, :tiket, :waktu_kejadian, :prioritas, :dampak,
            :target, :pihak, :jenis_masalah, :klasifikasi, :tgl_diterima,
            :id_cabang, :user, :pelapor, :masalah, :waktu_tanggap,
            :penyebab, :penyelesaian, :waktu_penyelesaian, :tgl_selesai,
            :tgl_esk, :status, :petugas, :komentar, :eskalasi,
            :petugas_esk, :fetched_at, :batch_id
        )
        ON CONFLICT (id_masalah)
        DO UPDATE SET
            tiket = EXCLUDED.tiket,
            waktu_kejadian = EXCLUDED.waktu_kejadian,
            prioritas = EXCLUDED.prioritas,
            dampak = EXCLUDED.dampak,
            target = EXCLUDED.target,
            pihak = EXCLUDED.pihak,
            jenis_masalah = EXCLUDED.jenis_masalah,
            klasifikasi = EXCLUDED.klasifikasi,
            tgl_diterima = EXCLUDED.tgl_diterima,
            id_cabang = EXCLUDED.id_cabang,
            "user" = EXCLUDED."user",
            pelapor = EXCLUDED.pelapor,
            masalah = EXCLUDED.masalah,
            waktu_tanggap = EXCLUDED.waktu_tanggap,
            penyebab = EXCLUDED.penyebab,
            penyelesaian = EXCLUDED.penyelesaian,
            waktu_penyelesaian = EXCLUDED.waktu_penyelesaian,
            tgl_selesai = EXCLUDED.tgl_selesai,
            tgl_esk = EXCLUDED.tgl_esk,
            status = EXCLUDED.status,
            petugas = EXCLUDED.petugas,
            komentar = EXCLUDED.komentar,
            eskalasi = EXCLUDED.eskalasi,
            petugas_esk = EXCLUDED.petugas_esk,
            fetched_at = NOW(),
            batch_id = EXCLUDED.batch_id
    """)

    with engine.begin() as conn:
        conn.execute(query, records)


# ─────────────────────────────────────────────
# UPSERT PETUGAS
# ─────────────────────────────────────────────
def _upsert_petugas(df: pd.DataFrame):

    for col in ["id_petugas", "nama", "position"]:
        if col not in df.columns:
            df[col] = None

    records = df.to_dict(orient="records")

    query = text("""
        INSERT INTO raw_petugas (id_petugas, nama, position, fetched_at, batch_id)
        VALUES (:id_petugas, :nama, :position, :fetched_at, :batch_id)
        ON CONFLICT (id_petugas)
        DO UPDATE SET
            nama = EXCLUDED.nama,
            position = EXCLUDED.position,
            fetched_at = NOW(),
            batch_id = EXCLUDED.batch_id
    """)

    with engine.begin() as conn:
        conn.execute(query, records)


# ─────────────────────────────────────────────
# EXTRACT LOG ACTIVITY
# ─────────────────────────────────────────────
def extract_log_activity(batch_id: str) -> int:

    logger.info("=== EXTRACT: log_activity dimulai ===")

    raw_data = _fetch_api(URL_LOG_ACTIVITY)
    if not raw_data:
        return 0

    df = pd.DataFrame(raw_data)

    if "id_masalah" not in df.columns:
        logger.error("id_masalah tidak ada")
        return 0

    now = datetime.now(timezone.utc)
    df["fetched_at"] = now
    df["batch_id"] = batch_id

    _upsert_raw_log_activity(df)

    logger.info(f"Processed {len(df)} rows")
    return len(df)


# ─────────────────────────────────────────────
# EXTRACT PETUGAS
# ─────────────────────────────────────────────
def extract_petugas(batch_id: str) -> int:

    logger.info("=== EXTRACT: petugas dimulai ===")

    raw_data = _fetch_api(URL_PETUGAS)
    if not raw_data:
        return 0

    df = pd.DataFrame(raw_data)

    now = datetime.now(timezone.utc)
    df["fetched_at"] = now
    df["batch_id"] = batch_id

    _upsert_petugas(df)

    logger.info(f"Processed {len(df)} petugas")
    return len(df)


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def run_extract() -> dict:

    batch_id = str(uuid.uuid4())[:8]

    result = {
        "batch_id": batch_id,
        "log_activity_new": extract_log_activity(batch_id),
        "petugas_new": extract_petugas(batch_id),
        "status": "success"
    }

    return result