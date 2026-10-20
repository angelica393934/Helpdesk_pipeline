# 📘 Sistem ETL – Panduan Lengkap
## Log Activity & Petugas → PostgreSQL via Celery + Redis

---

## 🗂️ Struktur Project

```
etl_sistem/
│
├── docker-compose.yml        ← Orkestrasi semua service
├── Dockerfile                ← Image Python untuk worker & beat
├── requirements.txt          ← Dependensi Python
├── .env.example              ← Template environment variables
├── init_db.sql               ← DDL semua tabel PostgreSQL
├── run_etl.py                ← Script manual jalankan ETL
│
├── config/
│   └── settings.py           ← Semua konfigurasi (baca dari .env)
│
├── etl/
│   ├── extractor.py          ← STEP 1: Extract dari API
│   └── transformer.py        ← STEP 2: Transform + Load
│
├── tasks/
│   └── celery_app.py         ← Celery app + definisi semua task
│
└── utils/
    ├── db.py                 ← Koneksi PostgreSQL (SQLAlchemy)
    └── logger.py             ← Logging terpusat

---

## ⚙️ Prasyarat

| Tool         | Versi minimum | Keterangan              |
|--------------|---------------|-------------------------|
| Docker       | 24.x          | Wajib                   |
| Docker Compose | 2.x         | Wajib                   |
| Python       | 3.11+         | Hanya untuk dev lokal   |

---

## 🚀 Langkah Setup (Step by Step)

### STEP 1 – Clone / Siapkan project

```bash
# Buat folder project
mkdir etl_sistem && cd etl_sistem

# Salin semua file ke sini
# (pastikan docker-compose.yml, Dockerfile, dll sudah ada)

``` 

### STEP 2 – Buat file .env

```bash
cp .env.example .env
```

Edit `.env` sesuai kebutuhan:

```env
# Database PostgreSQL
POSTGRES_DB=etl_db
POSTGRES_USER=etl_user
POSTGRES_PASSWORD=ganti_dengan_password_kuat

# Redis (tidak perlu diubah jika pakai Docker)
REDIS_HOST=redis
REDIS_PORT=6379

# API Sumber Data (sudah benar, tidak perlu diubah)
API_BASE_URL=http://220.112.111.88:5001

# Jadwal
SCHEDULE_FETCH_INTERVAL_HOURS=1   # fetch tiap 1 jam
SCHEDULE_ETL_HOUR=2               # ETL penuh jam 2 pagi
SCHEDULE_ETL_MINUTE=0
```

---

### STEP 3 – Build dan jalankan semua service

```bash
# Build image Python
docker compose build

# Jalankan semua service
docker compose up -d

# Cek status semua container
docker compose ps
```

Output yang diharapkan:
```
NAME             STATUS
etl_postgres     running (healthy)
etl_redis        running (healthy)
etl_worker       running
etl_beat         running
etl_flower       running
```

---

### STEP 4 – Verifikasi database terbuat

```bash
# Masuk ke PostgreSQL
docker exec -it etl_postgres psql -U etl_user -d etl_db

# Cek tabel yang ada
\dt

# Output yang diharapkan:
#  raw_log_activity
#  raw_petugas
#  etl_processed_tickets
#  dim_petugas
#  fact_ticket_clean
#  fact_productivity_summary
#  fact_hourly_pattern
#  fact_ticket_trend
#  fact_jenis_masalah
#  etl_run_log

\q
```

---

### STEP 5 – Test Extract Manual (Pertama Kali)

```bash
# Masuk ke container worker
docker exec -it etl_worker bash

# Jalankan ETL manual
python run_etl.py --mode all

# Atau hanya extract dulu
python run_etl.py --mode extract
```

---

### STEP 6 – Monitor di Flower (UI Celery)

Buka browser: **http://localhost:5555**

- Login: `admin / admin123` (sesuai .env)
- Lihat task yang berjalan, sukses, atau gagal
- Bisa trigger task manual dari UI

---

### STEP 7 – Verifikasi Data Masuk

```bash
docker exec -it etl_postgres psql -U etl_user -d etl_db -c "
SELECT
  (SELECT COUNT(*) FROM raw_log_activity)      AS raw_log,
  (SELECT COUNT(*) FROM raw_petugas)           AS raw_petugas,
  (SELECT COUNT(*) FROM fact_ticket_clean)     AS fact_ticket,
  (SELECT COUNT(*) FROM fact_productivity_summary) AS produktivitas,
  (SELECT COUNT(*) FROM etl_run_log)           AS log_etl;
"
```

---

## 🔄 Alur Data Lengkap

```
API /log_activity  ──┐
                     ├──► raw_log_activity ──► [Filter tiket baru]
API /petugas       ──┘    raw_petugas              │
                                                   ▼
                                          [A. Data Cleaning]
                                          - Hapus duplikat tiket
                                          - Handle null tgl_diterima
                                          - Parse datetime
                                                   │
                                                   ▼
                                          [B. Data Processing]
                                          - Hitung is_selesai
                                          - Hitung response_time
                                          - Hitung resolution_time
                                          - Breakdown waktu
                                                   │
                                          ┌────────┴────────┐
                                          ▼                 ▼
                                  fact_ticket_clean    dim_petugas
                                          │
                                          ▼
                                  [C. Aggregation]
                                  ┌───────┬───────┬───────┐
                                  ▼       ▼       ▼       ▼
                           produktiv  hourly  trend   jenis
                           _summary  _pattern _trend  _masalah
```

---

## 📊 Penjelasan Tabel

### Raw Tables (data mentah dari API)
| Tabel | Isi |
|-------|-----|
| `raw_log_activity` | Semua data log aktivitas dari API |
| `raw_petugas` | Data master petugas dari API |

### Kontrol Incremental
| Tabel | Isi |
|-------|-----|
| `etl_processed_tickets` | Tiket yang sudah pernah diproses (cegah duplikat) |

### Dimensi
| Tabel | Isi |
|-------|-----|
| `dim_petugas` | Master petugas yang sudah bersih |

### Fact Tables
| Tabel | Isi |
|-------|-----|
| `fact_ticket_clean` | Tiket bersih + kolom turunan (is_selesai, response_time, dll) |
| `fact_productivity_summary` | Skor produktivitas per petugas per periode |
| `fact_hourly_pattern` | Pola jam kerja per petugas |
| `fact_ticket_trend` | Trend jumlah tiket per waktu |
| `fact_jenis_masalah` | Distribusi jenis masalah |

---

## 🧮 Rumus Skor Produktivitas

```
Skor = (0.40 × tingkat_penyelesaian)
     + (0.30 × volume_score)
     + (0.15 × response_score)
     + (0.15 × resolution_score)

Dimana:
  tingkat_penyelesaian = Σ(prioritas × is_selesai) / Σ(prioritas)
  volume_score         = log(total_tiket + 1) / max(log(n + 1))
  response_score       = 1 - rank(avg_response_time) yang dinormalisasi
  resolution_score     = 1 - rank(avg_resolution_time) yang dinormalisasi
```

---

## 📅 Jadwal Otomatis (Celery Beat)

| Task | Jadwal | Deskripsi |
|------|--------|-----------|
| `task_fetch_data` | Setiap 1 jam | Ambil data terbaru dari API, simpan ke raw |
| `task_run_etl` | Jam 02:00 WIB | Full ETL: extract + transform semua agregasi |

---

## 🛠️ Perintah Berguna

```bash
# Lihat log worker
docker logs etl_worker -f

# Lihat log beat scheduler
docker logs etl_beat -f

# Trigger task manual tanpa masuk container
docker exec etl_worker celery -A tasks.celery_app call tasks.celery_app.task_run_etl

# Trigger hanya fetch
docker exec etl_worker celery -A tasks.celery_app call tasks.celery_app.task_fetch_data

# Cek log ETL di database
docker exec etl_postgres psql -U etl_user -d etl_db -c \
  "SELECT task_name, status, rows_new, started_at, finished_at FROM etl_run_log ORDER BY started_at DESC LIMIT 10;"

# Stop semua service
docker compose down

# Stop dan hapus semua data (hati-hati!)
docker compose down -v
```

---

## ❓ Troubleshooting

### Container tidak mau start
```bash
docker compose logs postgres  # cek log postgres
docker compose logs redis     # cek log redis
```

### Worker tidak bisa konek ke DB
```bash
# Pastikan .env POSTGRES_HOST=postgres (nama service di docker-compose)
# Bukan localhost!
```

### API tidak bisa diakses
```bash
# Test dari dalam container
docker exec etl_worker curl http://220.112.111.88:5001/log_activity
```

### Tabel tidak terbuat otomatis
```bash
# Jalankan init_db.sql manual
docker exec -i etl_postgres psql -U etl_user -d etl_db < init_db.sql
```

---

## 🔐 Keamanan (Production)

1. Ganti `POSTGRES_PASSWORD` dengan password kuat
2. Ganti `FLOWER_PASS` dengan password kuat
3. Jangan expose port 5432 ke internet
4. Gunakan network terpisah di Docker untuk isolasi
5. Simpan `.env` di luar version control (tambah ke `.gitignore`)
