"""
 2 – TRANSFORM
Mengolah data dari raw tables menjadi tabel clean & dimensi.

Alur:
  A. Data Cleaning  → bersihkan data mentah
  B. Data Processing → bentuk fact_ticket_clean + kalkulasi kolom baru
  C. Data Aggregation → buat summary tables untuk dashboard
"""

import numpy as np
import pandas as pd
from sqlalchemy import text

from utils.db import engine, get_connection
from utils.logger import get_logger

logger = get_logger(__name__)

# ──────────────────────────────────────────────────────────────
# Helper: parse datetime yang fleksibel
# ────────────────────────────────────────────────────────────

DATETIME_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%d/%m/%Y %H:%M:%S",
    "%d-%m-%Y %H:%M:%S",
    "%Y-%m-%d",
]

def _parse_datetime(series: pd.Series) -> pd.Series:
    """Coba parse datetime dengan beberapa format. Return NaT jika gagal."""
    parsed = pd.to_datetime(series, errors="coerce", utc=True)
    # Jika banyak NaT, coba format lain
    if parsed.isna().sum() > len(series) * 0.5:
        for fmt in DATETIME_FORMATS:
            try:
                attempt = pd.to_datetime(series, format=fmt, errors="coerce", utc=True)
                if attempt.notna().sum() > parsed.notna().sum():
                    parsed = attempt
            except Exception:
                continue
    return parsed

def _parse_time_on_date(series: pd.Series, base: pd.Series) -> pd.Series:
    """Kolom berisi jam saja ('09:15:00'): gabungkan dengan tanggal dari `base`
    (tgl_diterima). Jam lebih kecil dari jam `base` = lewat tengah malam -> +1 hari.
    Jika isinya sudah tanggal lengkap, di-parse seperti biasa."""
    s = series.astype("string").str.strip()
    is_time = s.str.fullmatch(r"\d{1,2}:\d{2}(:\d{2})?").fillna(False).astype(bool)

    full = _parse_datetime(series.where(~is_time))

    t_str = s.where(is_time).astype(object)
    t_str = t_str.where(~is_time | t_str.astype(str).str.count(":").eq(2),
                        t_str.astype(str) + ":00")
    t = pd.to_timedelta(t_str, errors="coerce")

    combined = base.dt.normalize() + t
    combined = combined.where(~(combined < base), combined + pd.Timedelta(days=1))
    return full.where(~is_time, combined)
# ────────────────────────────────────────────────────────────
# A. DATA CLEANING
# ────────────────────────────────────────────────────────────

def clean_raw_data() -> pd.DataFrame:
    """
    Ambil data baru dari raw_log_activity yang belum pernah diproses,
    lakukan cleaning, dan kembalikan DataFrame bersih.

    "Belum pernah diproses" = tiket tidak ada di etl_processed_tickets
    """
    logger.info("=== TRANSFORM A: Data Cleaning dimulai ===")

    # Ambil tiket yang belum diproses
    sql_unprocessed = """
        SELECT r.*
        FROM raw_log_activity r
        LEFT JOIN fact_ticket_clean f ON r.tiket = f.tiket
        WHERE r.tiket IS NOT NULL
          AND (
                f.tiket IS NULL                  -- tiket baru
             OR r.updated_at > f.processed_at    -- tiket berubah di API
          )
    """
    df = pd.read_sql(sql_unprocessed, engine)

    if df.empty:
        logger.info("Tidak ada data baru untuk diproses")
        return df

    logger.info(f"Data mentah yang akan diproses: {len(df)} baris")

    # ── 1. Hapus duplicate tiket (ambil yang terbaru) ──────────
    before = len(df)
    df = df.sort_values("fetched_at", ascending=False).drop_duplicates(subset=["tiket"])
    logger.info(f"Setelah dedup: {len(df)} baris (hapus {before - len(df)} duplikat)")

    # ── 2. Konversi kolom datetime ─────────────────────────────
    for col in ["waktu_kejadian", "tgl_diterima", "tgl_selesai", "tgl_esk"]:
        if col in df.columns:
            df[col] = _parse_datetime(df[col])

    # Kolom berisi jam saja -> digabung dengan tanggal tgl_diterima
    for col in ["waktu_tanggap", "waktu_penyelesaian"]:
        if col in df.columns:
            df[col] = _parse_time_on_date(df[col], df["tgl_diterima"])

    # ── 3. Validasi wajib: tgl_diterima tidak boleh null ───────
    before = len(df)
    df = df[df["tgl_diterima"].notna()].copy()
    dropped = before - len(df)
    if dropped:
        logger.warning(f"Hapus {dropped} baris karena tgl_diterima null")

    # ── 4. Konversi tipe data ───────────────────────────────────
    # prioritas → integer (jika berupa string angka)
    if "prioritas" in df.columns:
        df["prioritas"] = pd.to_numeric(df["prioritas"], errors="coerce").fillna(1).astype(int)

    # status → integer
    if "status" in df.columns:
        df["status"] = pd.to_numeric(df["status"], errors="coerce").fillna(0).astype(int)

    # ── 5. Trim whitespace di kolom teks ───────────────────────
    text_cols = ["tiket", "petugas", "jenis_masalah", "klasifikasi", "id_cabang"]
    for col in text_cols:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace("nan", None)

    logger.info(f"=== Cleaning selesai: {len(df)} baris bersih ===")
    return df


# ──────────────────────────────────────────────────────────────
# B. DATA PROCESSING → fact_ticket_clean
# ──────────────────────────────────────────────────────────────

def process_to_fact_table(df_clean: pd.DataFrame) -> pd.DataFrame:
    """
    Tambahkan kolom-kolom turunan ke DataFrame yang sudah bersih:
      - is_selesai
      - response_time_minutes
      - resolution_time_minutes
      - breakdown waktu (hour, date, week, month, year)
    """
    if df_clean.empty:
        return df_clean

    logger.info("=== TRANSFORM B: Processing ke fact_ticket_clean ===")

    df = df_clean.copy()

    # ── is_selesai: status == 2 → selesai ──────────────────────
    df["is_selesai"] = (df["status"] == 2).astype(int)

    # ── Response time: tgl_diterima → waktu_tanggap ───────────
    if "waktu_tanggap" in df.columns and "tgl_diterima" in df.columns:
        df["response_time_minutes"] = (
            (df["waktu_tanggap"] - df["tgl_diterima"])
            .dt.total_seconds()
            .div(60)
            .round(2)
        )
        # Negatif tidak masuk akal → set NaN
        df.loc[df["response_time_minutes"] < 0, "response_time_minutes"] = np.nan
    else:
        df["response_time_minutes"] = np.nan

    # ── Resolution time: tgl_diterima → waktu_penyelesaian ────
    if "waktu_penyelesaian" in df.columns and "tgl_diterima" in df.columns:
        df["resolution_time_minutes"] = (
            (df["waktu_penyelesaian"] - df["tgl_diterima"])
            .dt.total_seconds()
            .div(60)
            .round(2)
        )
        df.loc[df["resolution_time_minutes"] < 0, "resolution_time_minutes"] = np.nan
    else:
        df["resolution_time_minutes"] = np.nan

    # ── Breakdown waktu dari tgl_diterima ──────────────────────
    df["created_hour"]  = df["tgl_diterima"].dt.hour.astype("Int16")
    df["created_date"]  = df["tgl_diterima"].dt.date
    df["created_week"]  = df["tgl_diterima"].dt.isocalendar().week.astype("Int16")
    df["created_month"] = df["tgl_diterima"].dt.month.astype("Int16")
    df["created_year"]  = df["tgl_diterima"].dt.year.astype("Int16")

    logger.info("=== Processing selesai ===")
    return df


def load_fact_ticket_clean(df: pd.DataFrame) -> int:
    """
    Upsert ke fact_ticket_clean:
      - tiket baru  → INSERT
      - tiket lama  → UPDATE (status, waktu, dll ikut diperbarui)
    Returns: jumlah baris yang di-insert/update
    """
    if df.empty:
        return 0

    fact_cols = [
        "tiket", "id_masalah", "waktu_kejadian", "prioritas", "dampak",
        "target", "pihak", "jenis_masalah", "klasifikasi", "tgl_diterima",
        "id_cabang", "user", "pelapor", "masalah", "waktu_tanggap",
        "penyebab", "penyelesaian", "waktu_penyelesaian", "tgl_selesai",
        "tgl_esk", "status", "petugas", "komentar", "eskalasi", "petugas_esk",
        "is_selesai", "response_time_minutes", "resolution_time_minutes",
        "created_hour", "created_date", "created_week", "created_month", "created_year",
    ]

    df_save = df[[c for c in fact_cols if c in df.columns]].copy()

    df_save.to_sql(
        name="_temp_fact_ticket",
        con=engine,
        if_exists="replace",
        index=False,
    )

    def q(c: str) -> str:
        return f'"{c}"' if c == "user" else c

    cols = ", ".join(q(c) for c in df_save.columns)
    set_clause = ", ".join(
        f"{q(c)} = EXCLUDED.{q(c)}" for c in df_save.columns if c != "tiket"
    )

    sql_upsert = f"""
        INSERT INTO fact_ticket_clean ({cols})
        SELECT {cols} FROM _temp_fact_ticket
        ON CONFLICT (tiket) DO UPDATE SET
            {set_clause},
            processed_at = NOW()
    """

    with get_connection() as conn:
        result = conn.execute(text(sql_upsert))
        affected = result.rowcount
        conn.execute(text("DROP TABLE IF EXISTS _temp_fact_ticket"))

    logger.info(f"fact_ticket_clean: {affected} baris di-upsert (baru + berubah)")
    return affected


def _mark_tickets_processed(tikets: list):
    """Tandai tiket sebagai sudah diproses di etl_processed_tickets."""
    if not tikets:
        return
    rows = [{"tiket": t} for t in tikets]
    sql = """
        INSERT INTO etl_processed_tickets (tiket)
        VALUES (:tiket)
        ON CONFLICT (tiket) DO NOTHING
    """
    from utils.db import execute_many
    execute_many(sql, rows)


# ──────────────────────────────────────────────────────────────
# UPDATE dim_petugas dari raw_petugas
# ──────────────────────────────────────────────────────────────

def update_dim_petugas():
    """Upsert data petugas dari raw_petugas ke dim_petugas."""
    logger.info("Update dim_petugas dari raw_petugas...")

    sql = """
        INSERT INTO dim_petugas (id_petugas, nama, position, updated_at)
        SELECT DISTINCT ON (id_petugas)
            id_petugas, nama, position, NOW()
        FROM raw_petugas
        WHERE id_petugas IS NOT NULL
        ORDER BY id_petugas, fetched_at DESC
        ON CONFLICT (id_petugas) DO UPDATE
            SET nama      = EXCLUDED.nama,
                position  = EXCLUDED.position,
                updated_at = NOW()
    """
    with get_connection() as conn:
        conn.execute(text(sql))

    logger.info("dim_petugas berhasil diupdate")


# ──────────────────────────────────────────────────────────────
# C. DATA AGGREGATION
# ──────────────────────────────────────────────────────────────

def _rank_normalize(series: pd.Series) -> pd.Series:
    """
    Rank ascending (nilai kecil = rank kecil), lalu normalize ke 0-1,
    kemudian invert: 1 - rank (sehingga nilai kecil → skor tinggi).
    """
    ranked = series.rank(method="min", ascending=True, na_option="bottom")
    n = ranked.notna().sum()
    if n <= 1:
        return pd.Series([1.0] * len(series), index=series.index)
    normalized = (ranked - 1) / (n - 1)
    return (1 - normalized).round(4)


def aggregate_productivity_summary():
    """
    Hitung fact_productivity_summary per petugas per periode (daily/weekly/monthly).
    Skor Produktivitas:
      0.40 × tingkat_penyelesaian
    + 0.30 × volume_score
    + 0.15 × response_score
    + 0.15 × resolution_score
    """
    logger.info("=== AGGREGASI: fact_productivity_summary ===")

    df = pd.read_sql(
        """
        SELECT tiket, petugas, prioritas, is_selesai,
               response_time_minutes, resolution_time_minutes,
               created_date, created_week, created_month, created_year
        FROM fact_ticket_clean
        WHERE petugas IS NOT NULL
        """,
        engine,
    )

    if df.empty:
        logger.info("Tidak ada data untuk agregasi produktivitas")
        return

    results = []

    for periode_type, group_key in [
        ("daily",   ["petugas", "created_date"]),
        ("weekly",  ["petugas", "created_year", "created_week"]),
        ("monthly", ["petugas", "created_year", "created_month"]),
    ]:
        grp = df.groupby(group_key).agg(
            total_tiket             = ("tiket",                    "count"),
            total_selesai           = ("is_selesai",               "sum"),
            sum_prioritas           = ("prioritas",                "sum"),
            sum_prioritas_selesai   = ("prioritas",                lambda x: (x * df.loc[x.index, "is_selesai"]).sum()),
            avg_response            = ("response_time_minutes",    "mean"),
            avg_resolution          = ("resolution_time_minutes",  "mean"),
        ).reset_index()

        # Tingkat penyelesaian berbobot prioritas
        grp["tingkat_penyelesaian"] = (
            grp["sum_prioritas_selesai"] / grp["sum_prioritas"].replace(0, np.nan)
        ).fillna(0).round(4)

        # Volume score = log(total_tiket + 1), lalu normalize
        grp["volume_raw"]   = np.log1p(grp["total_tiket"])
        v_max = grp["volume_raw"].max()
        grp["volume_score"] = (grp["volume_raw"] / v_max).round(4) if v_max > 0 else 0.0

        # Response & resolution score (rank invert)
        grp["response_score"]    = _rank_normalize(grp["avg_response"])
        grp["resolution_score"]  = _rank_normalize(grp["avg_resolution"])

        # Skor final
        grp["skor_produktivitas"] = (
            0.40 * grp["tingkat_penyelesaian"]
            + 0.30 * grp["volume_score"]
            + 0.15 * grp["response_score"]
            + 0.15 * grp["resolution_score"]
        ).round(4)

        # Bentuk periode_value string
        if periode_type == "daily":
            grp["periode_value"] = grp["created_date"].astype(str)
        elif periode_type == "weekly":
            grp["periode_value"] = grp["created_year"].astype(str) + "-W" + grp["created_week"].astype(str).str.zfill(2)
        else:
            grp["periode_value"] = grp["created_year"].astype(str) + "-" + grp["created_month"].astype(str).str.zfill(2)

        grp["id_petugas"]          = grp["petugas"]
        grp["periode_type"]        = periode_type
        grp["avg_response_minutes"]    = grp["avg_response"].round(2)
        grp["avg_resolution_minutes"]  = grp["avg_resolution"].round(2)

        results.append(grp[[
            "id_petugas", "periode_type", "periode_value",
            "total_tiket", "total_selesai",
            "sum_prioritas", "sum_prioritas_selesai",
            "tingkat_penyelesaian", "volume_score",
            "response_score", "resolution_score", "skor_produktivitas",
            "avg_response_minutes", "avg_resolution_minutes",
        ]])

    df_result = pd.concat(results, ignore_index=True)

    # Upsert ke tabel
    df_result.to_sql("_temp_productivity", engine, if_exists="replace", index=False)
    with get_connection() as conn:
        conn.execute(text("""
            INSERT INTO fact_productivity_summary (
                id_petugas, periode_type, periode_value,
                total_tiket, total_selesai, sum_prioritas, sum_prioritas_selesai,
                tingkat_penyelesaian, volume_score, response_score, resolution_score,
                skor_produktivitas, avg_response_minutes, avg_resolution_minutes,
                aggregated_at
            )
            SELECT *, NOW() FROM _temp_productivity
            ON CONFLICT (id_petugas, periode_type, periode_value)
            DO UPDATE SET
                total_tiket              = EXCLUDED.total_tiket,
                total_selesai            = EXCLUDED.total_selesai,
                skor_produktivitas       = EXCLUDED.skor_produktivitas,
                tingkat_penyelesaian     = EXCLUDED.tingkat_penyelesaian,
                volume_score             = EXCLUDED.volume_score,
                response_score           = EXCLUDED.response_score,
                resolution_score         = EXCLUDED.resolution_score,
                avg_response_minutes     = EXCLUDED.avg_response_minutes,
                avg_resolution_minutes   = EXCLUDED.avg_resolution_minutes,
                aggregated_at            = NOW()
        """))
        conn.execute(text("DROP TABLE IF EXISTS _temp_productivity"))

    logger.info(f"fact_productivity_summary: {len(df_result)} baris diupsert")


def aggregate_hourly_pattern():
    """Hitung pola jam kerja per petugas (fact_hourly_pattern)."""
    logger.info("=== AGGREGASI: fact_hourly_pattern ===")

    df = pd.read_sql(
        "SELECT petugas AS id_petugas, created_hour, COUNT(*) AS total_tiket "
        "FROM fact_ticket_clean WHERE petugas IS NOT NULL GROUP BY petugas, created_hour",
        engine,
    )
    if df.empty:
        return

    df.to_sql("_temp_hourly", engine, if_exists="replace", index=False)
    with get_connection() as conn:
        conn.execute(text("""
            INSERT INTO fact_hourly_pattern (id_petugas, created_hour, total_tiket, aggregated_at)
            SELECT id_petugas, created_hour, total_tiket, NOW() FROM _temp_hourly
            ON CONFLICT (id_petugas, created_hour)
            DO UPDATE SET total_tiket = EXCLUDED.total_tiket, aggregated_at = NOW()
        """))
        conn.execute(text("DROP TABLE IF EXISTS _temp_hourly"))

    logger.info(f"fact_hourly_pattern: {len(df)} baris diupsert")


def aggregate_ticket_trend():
    """Hitung trend tiket (fact_ticket_trend)."""
    logger.info("=== AGGREGASI: fact_ticket_trend ===")

    df = pd.read_sql(
        "SELECT created_date, created_week, created_month, created_year, is_selesai "
        "FROM fact_ticket_clean",
        engine,
    )
    if df.empty:
        return

    results = []
    for periode_type, cols in [
        ("daily",   ["created_date"]),
        ("weekly",  ["created_year", "created_week"]),
        ("monthly", ["created_year", "created_month"]),
    ]:
        grp = df.groupby(cols).agg(
            total_tiket   = ("is_selesai", "count"),
            total_selesai = ("is_selesai", "sum"),
        ).reset_index()

        if periode_type == "daily":
            grp["periode_value"] = grp["created_date"].astype(str)
        elif periode_type == "weekly":
            grp["periode_value"] = grp["created_year"].astype(str) + "-W" + grp["created_week"].astype(str).str.zfill(2)
        else:
            grp["periode_value"] = grp["created_year"].astype(str) + "-" + grp["created_month"].astype(str).str.zfill(2)

        grp["periode_type"] = periode_type
        results.append(grp[["periode_type", "periode_value", "total_tiket", "total_selesai"]])

    df_result = pd.concat(results, ignore_index=True)
    df_result.to_sql("_temp_trend", engine, if_exists="replace", index=False)

    with get_connection() as conn:
        conn.execute(text("""
            INSERT INTO fact_ticket_trend (periode_type, periode_value, total_tiket, total_selesai, aggregated_at)
            SELECT periode_type, periode_value, total_tiket, total_selesai, NOW() FROM _temp_trend
            ON CONFLICT (periode_type, periode_value)
            DO UPDATE SET total_tiket = EXCLUDED.total_tiket, total_selesai = EXCLUDED.total_selesai, aggregated_at = NOW()
        """))
        conn.execute(text("DROP TABLE IF EXISTS _temp_trend"))

    logger.info(f"fact_ticket_trend: {len(df_result)} baris diupsert")


def aggregate_jenis_masalah():
    """Hitung distribusi jenis masalah (fact_jenis_masalah)."""
    logger.info("=== AGGREGASI: fact_jenis_masalah ===")

    df = pd.read_sql(
        "SELECT jenis_masalah, created_date, created_week, created_month, created_year "
        "FROM fact_ticket_clean WHERE jenis_masalah IS NOT NULL",
        engine,
    )
    if df.empty:
        return

    results = []
    for periode_type, cols in [
        ("weekly",  ["created_year", "created_week"]),
        ("monthly", ["created_year", "created_month"]),
    ]:
        grp = df.groupby(["jenis_masalah"] + cols).size().reset_index(name="total_tiket")
        if periode_type == "weekly":
            grp["periode_value"] = grp["created_year"].astype(str) + "-W" + grp["created_week"].astype(str).str.zfill(2)
        else:
            grp["periode_value"] = grp["created_year"].astype(str) + "-" + grp["created_month"].astype(str).str.zfill(2)
        grp["periode_type"] = periode_type
        results.append(grp[["jenis_masalah", "periode_type", "periode_value", "total_tiket"]])

    df_result = pd.concat(results, ignore_index=True)
    df_result.to_sql("_temp_jenis", engine, if_exists="replace", index=False)

    with get_connection() as conn:
        conn.execute(text("""
            INSERT INTO fact_jenis_masalah (jenis_masalah, periode_type, periode_value, total_tiket, aggregated_at)
            SELECT jenis_masalah, periode_type, periode_value, total_tiket, NOW() FROM _temp_jenis
            ON CONFLICT (jenis_masalah, periode_type, periode_value)
            DO UPDATE SET total_tiket = EXCLUDED.total_tiket, aggregated_at = NOW()
        """))
        conn.execute(text("DROP TABLE IF EXISTS _temp_jenis"))

    logger.info(f"fact_jenis_masalah: {len(df_result)} baris diupsert")


# ──────────────────────────────────────────────────────────────
# Entry point: jalankan semua transform
# ──────────────────────────────────────────────────────────────

def run_transform() -> dict:
    """Jalankan full transform pipeline."""
    logger.info("====== TRANSFORM PIPELINE DIMULAI ======")

    result = {"status": "success", "rows_inserted": 0, "error": None}

    try:
        # A. Cleaning
        df_clean = clean_raw_data()

        # B. Processing
        if not df_clean.empty:
            df_processed = process_to_fact_table(df_clean)
            result["rows_inserted"] = load_fact_ticket_clean(df_processed)

        # Update dimensi
        update_dim_petugas()

        # C. Aggregation
        aggregate_productivity_summary()
        aggregate_hourly_pattern()
        aggregate_ticket_trend()
        aggregate_jenis_masalah()

    except Exception as e:
        logger.error(f"Transform gagal: {e}", exc_info=True)
        result["status"] = "failed"
        result["error"]  = str(e)
        raise

    logger.info("====== TRANSFORM PIPELINE SELESAI ======")
    return result
