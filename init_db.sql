-- ============================================================
-- init_db.sql
-- Dijalankan otomatis saat PostgreSQL container pertama kali start
-- Membuat semua tabel yang dibutuhkan sistem ETL
-- ============================================================

-- ────────────────────────────────────────────────────────────
-- RAW TABLES (hasil langsung dari API – data mentah)
-- ────────────────────────────────────────────────────────────

-- Tabel raw hasil hit API /log_activity
-- ─────────────────────────────────────────────
-- RAW LOG ACTIVITY (UPSERT ENABLED)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS raw_log_activity (
    id               BIGSERIAL PRIMARY KEY,

    id_masalah       VARCHAR(100) NOT NULL,
    tiket            VARCHAR(100),
    waktu_kejadian   TEXT,
    prioritas        VARCHAR(50),
    dampak           TEXT,
    target           TEXT,
    pihak            TEXT,
    jenis_masalah    TEXT,
    klasifikasi      TEXT,
    tgl_diterima     TEXT,
    id_cabang        VARCHAR(100),
    "user"           TEXT,
    pelapor          TEXT,
    masalah          TEXT,
    waktu_tanggap    TEXT,
    penyebab         TEXT,
    penyelesaian     TEXT,
    waktu_penyelesaian TEXT,
    tgl_selesai      TEXT,
    tgl_esk          TEXT,
    status           TEXT,
    petugas          TEXT,
    komentar         TEXT,
    eskalasi         TEXT,
    petugas_esk      TEXT,

    fetched_at       TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at       TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    batch_id         VARCHAR(50),

    -- 🔥 INI YANG PALING PENTING
    CONSTRAINT unique_id_masalah UNIQUE (id_masalah)
);

-- Index tetap
CREATE INDEX IF NOT EXISTS idx_raw_log_tiket      ON raw_log_activity (tiket);
CREATE INDEX IF NOT EXISTS idx_raw_log_fetched_at ON raw_log_activity (fetched_at);


-- ─────────────────────────────────────────────
-- RAW PETUGAS (UPSERT ENABLED)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS raw_petugas (
    id          BIGSERIAL PRIMARY KEY,
    id_petugas  VARCHAR(100) NOT NULL,
    nama        TEXT,
    position    TEXT,
    fetched_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    batch_id    VARCHAR(50),

    CONSTRAINT unique_id_petugas UNIQUE (id_petugas)
);

CREATE INDEX IF NOT EXISTS idx_raw_petugas_id ON raw_petugas (id_petugas);


-- ─────────────────────────────────────────────
-- ❌ HAPUS INI (SUDAH TIDAK DIPAKAI)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS etl_processed_tickets (
    tiket       VARCHAR PRIMARY KEY,
    processed_at TIMESTAMPTZ DEFAULT NOW()
);
-- DROP TABLE IF EXISTS etl_processed_tickets;
-- ────────────────────────────────────────────────────────────
-- DIMENSION TABLES
-- ────────────────────────────────────────────────────────────

-- Dimensi Petugas (SCD Type 1 – langsung overwrite)
CREATE TABLE IF NOT EXISTS dim_petugas (
    id_petugas   VARCHAR(100) PRIMARY KEY,
    nama         TEXT,
    position     TEXT,
    updated_at   TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ────────────────────────────────────────────────────────────
-- FACT TABLES
-- ────────────────────────────────────────────────────────────

-- Tabel utama tiket yang sudah dibersihkan & diperkaya
CREATE TABLE IF NOT EXISTS fact_ticket_clean (
    id                   BIGSERIAL PRIMARY KEY,
    tiket                VARCHAR(100) UNIQUE NOT NULL,
    id_masalah           VARCHAR(100),
    waktu_kejadian       TIMESTAMP WITH TIME ZONE,
    prioritas            INTEGER,             -- sudah dikonversi ke integer
    dampak               TEXT,
    target               TEXT,
    pihak                TEXT,
    jenis_masalah        TEXT,
    klasifikasi          TEXT,
    tgl_diterima         TIMESTAMP WITH TIME ZONE,
    id_cabang            VARCHAR(100),
    "user"               TEXT,
    pelapor              TEXT,
    masalah              TEXT,
    waktu_tanggap        TIMESTAMP WITH TIME ZONE,
    penyebab             TEXT,
    penyelesaian         TEXT,
    waktu_penyelesaian   TIMESTAMP WITH TIME ZONE,
    tgl_selesai          TIMESTAMP WITH TIME ZONE,
    tgl_esk              TIMESTAMP WITH TIME ZONE,
    status               INTEGER,
    petugas              TEXT,
    komentar             TEXT,
    eskalasi             TEXT,
    petugas_esk          TEXT,

    -- Kolom turunan (hasil transform)
    is_selesai           SMALLINT,            -- 1 = selesai, 0 = belum
    response_time_minutes NUMERIC(10,2),      -- menit antara tgl_diterima → waktu_tanggap
    resolution_time_minutes NUMERIC(10,2),   -- menit antara tgl_diterima → waktu_penyelesaian

    -- Breakdown waktu (untuk filter dashboard)
    created_hour         SMALLINT,
    created_date         DATE,
    created_week         SMALLINT,
    created_month        SMALLINT,
    created_year         SMALLINT,

    -- Metadata
    processed_at         TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fact_ticket_tiket    ON fact_ticket_clean (tiket);
CREATE INDEX IF NOT EXISTS idx_fact_ticket_petugas  ON fact_ticket_clean (petugas);
CREATE INDEX IF NOT EXISTS idx_fact_ticket_tanggal  ON fact_ticket_clean (created_date);
CREATE INDEX IF NOT EXISTS idx_fact_ticket_status   ON fact_ticket_clean (status);
CREATE INDEX IF NOT EXISTS idx_fact_ticket_cabang   ON fact_ticket_clean (id_cabang);

-- ────────────────────────────────────────────────────────────
-- SUMMARY / AGREGASI TABLES (untuk dashboard)
-- ────────────────────────────────────────────────────────────

-- 1. Produktivitas per petugas per periode
CREATE TABLE IF NOT EXISTS fact_productivity_summary (
    id                      BIGSERIAL PRIMARY KEY,
    id_petugas              VARCHAR(100),
    periode_type            VARCHAR(10),      -- 'daily','weekly','monthly'
    periode_value           TEXT,             -- '2024-01-15' / '2024-W03' / '2024-01'
    total_tiket             INTEGER,
    total_selesai           INTEGER,
    sum_prioritas           NUMERIC(10,2),
    sum_prioritas_selesai   NUMERIC(10,2),

    -- Komponen skor
    tingkat_penyelesaian    NUMERIC(5,4),     -- 0.0 – 1.0
    volume_score            NUMERIC(5,4),
    response_score          NUMERIC(5,4),
    resolution_score        NUMERIC(5,4),

    -- Skor akhir
    skor_produktivitas      NUMERIC(5,4),

    avg_response_minutes    NUMERIC(10,2),
    avg_resolution_minutes  NUMERIC(10,2),

    aggregated_at           TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE (id_petugas, periode_type, periode_value)
);

-- 2. Pola jam kerja per petugas
CREATE TABLE IF NOT EXISTS fact_hourly_pattern (
    id           BIGSERIAL PRIMARY KEY,
    id_petugas   VARCHAR(100),
    created_hour SMALLINT,
    total_tiket  INTEGER,
    aggregated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE (id_petugas, created_hour)
);

-- 3. Trend tiket harian/mingguan/bulanan
CREATE TABLE IF NOT EXISTS fact_ticket_trend (
    id            BIGSERIAL PRIMARY KEY,
    periode_type  VARCHAR(10),
    periode_value TEXT,
    total_tiket   INTEGER,
    total_selesai INTEGER,
    aggregated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE (periode_type, periode_value)
);

-- 4. Distribusi jenis masalah
CREATE TABLE IF NOT EXISTS fact_jenis_masalah (
    id            BIGSERIAL PRIMARY KEY,
    jenis_masalah TEXT,
    periode_type  VARCHAR(10),
    periode_value TEXT,
    total_tiket   INTEGER,
    aggregated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE (jenis_masalah, periode_type, periode_value)
);

-- ────────────────────────────────────────────────────────────
-- LOG SISTEM ETL
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS etl_run_log (
    id          BIGSERIAL PRIMARY KEY,
    task_name   TEXT,
    status      VARCHAR(20),   -- 'running','success','failed'
    rows_fetched INTEGER,
    rows_new    INTEGER,
    error_msg   TEXT,
    started_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    finished_at TIMESTAMP WITH TIME ZONE
);
