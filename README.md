# 🎫 Helpdesk Track – Sistem ETL & Dashboard Monitoring

Program ini **mengambil data tiket helpdesk dari sebuah API**, **membersihkannya**, lalu **menampilkannya di dashboard.

Semua berjalan otomatis di dalam **Docker**, jadi kamu tidak perlu menginstal Python, PostgreSQL, atau Redis satu per satu.
---

Ini kalau perandaian berjalan Data yang harus ada di API. semua table otomatis dibuat tapi isinya kosng.
jadi untuk biar datanya ada yakni table:
/log_activity (tiket)
/petugas 
        Jadi seed_data.py untuk mengisi tabel tanpa API. ini datanay untuk sampai desember 2027 hati hati karena tidak ad filter untuk menampilkan data yg berjalan ssat ini saja.

        Cara pakai
        1. Taruh seed_data.py di folder utama project, sejajar dengan run_etl.py. Tidak perlu build ulang karena folder project sudah di-mount ke Docker.
        2. Jalankan:
            docker exec -it etl_worker python seed_data.py
        3. Cek di DBeaver atau buka http://localhost:8000.
        Yang dilakukan script:
            raw_petugas: memasukkan 12 petugas persis dari data kamu.
            raw_log_activity: membuat tiket contoh dari hari ini sampai 31 Desember tahun depan. Rentang ini otomatis menyesuaikan kapan pun script dijalankan, jadi sekarang sekitar 5.000 tiket (18 Nov 2026 sampai 31 Des 2027).
            Transform: setelah raw terisi, script langsung menjalankan Transform, jadi fact_* dan dim_petugas ikut terisi.

        Rentang tanggal bisa diubah:

        bash
        docker exec -it etl_worker python seed_data.py --start 2026-11-18 --end 2028-12-31

## 📑 Daftar Isi

1. [Program ini fungsinya apa?](#1--program-ini-fungsinya-apa)
2. [Istilah yang perlu diketahui](#2--istilah-yang-perlu-diketahui-untuk-pemula)
3. [Cara kerja program (gambaran besar)](#3--cara-kerja-program-gambaran-besar)
4. [Fungsi setiap file & folder](#4--fungsi-setiap-file--folder)
5. [Setup pertama kali di device baru](#5--setup-pertama-kali-di-device-baru-step-by-step)
6. [Melihat tabel database dengan DBeaver](#6--melihat-tabel-database-dengan-dbeaver)
7. [Cara menjalankan lagi setelah dimatikan](#7--cara-menjalankan-lagi-setelah-dimatikan)
8. [Membuka dashboard & Flower](#8--membuka-dashboard--flower)
9. [Jadwal otomatis](#9--jadwal-otomatis)
10. [Perintah berguna](#10--perintah-berguna)
11. [Troubleshooting (kalau ada masalah)](#11--troubleshooting-kalau-ada-masalah)
12. [Keamanan sebelum dipakai sungguhan](#12--keamanan-sebelum-dipakai-sungguhan)

---

## 1. 🎯 Program ini fungsinya apa?

Bayangkan kamu punya sistem helpdesk yang menyimpan semua tiket keluhan (misal: "internet mati", "printer rusak"). Datanya berantakan dan sulit dibaca langsung.

Program ini melakukan 3 hal:

| Langkah | Nama | Penjelasan sederhana |
|---|---|---|
| 1 | **Extract** (Ambil) | Mengambil data tiket & data petugas dari API sumber, lalu menyimpannya apa adanya ke database. |
| 2 | **Transform** (Olah) | Membersihkan data, menghitung waktu respon & waktu penyelesaian, lalu membuat ringkasan (tren, skor petugas, dll). |
| 3 | **Dashboard** (Tampilkan) | Menampilkan hasil olahan di halaman web yang mudah dibaca. |

Semua ini berjalan sendiri sesuai jadwal (tiap 1 jam ambil data, tiap jam 2 pagi olah data).

**Yang bisa kamu lihat di dashboard:**
- Total tiket, tingkat penyelesaian, rata-rata waktu respon, rata-rata waktu penyelesaian
- Grafik tren tiket harian (masuk vs selesai)
- Jenis masalah teratas
- Jam-jam tiket paling banyak masuk
- Peringkat petugas berdasarkan skor produktivitas
- Riwayat proses ETL (berhasil / gagal)

---

## 2. 📖 Istilah yang perlu diketahui ()

| Istilah | Artinya |
|---|---|
| **ETL** | Extract – Transform – Load. Proses ambil data → olah data → simpan hasilnya. |
| **API** | "Pintu" dari sistem lain untuk meminta datanya. Di sini API menyediakan data `/log_activity` (tiket) dan `/petugas`. |
| **Docker** | Aplikasi yang membungkus program beserta semua kebutuhannya dalam "kotak" (container) sehingga bisa jalan di komputer mana pun dengan cara yang sama. |
| **Container** | Satu "kotak" program yang berjalan di Docker (misal: container database, container dashboard). |
| **Docker Compose** | Alat untuk menyalakan banyak container sekaligus dengan 1 perintah, berdasarkan file `docker-compose.yml`. |
| **PostgreSQL** | Database tempat semua data disimpan dalam bentuk tabel. |
| **Redis** | "Kotak surat" yang dipakai Celery untuk menyimpan antrean pekerjaan. |
| **Celery** | Pekerja yang menjalankan tugas (ambil data, olah data) di belakang layar. |
| **Celery Beat** | "Alarm/penjadwal" yang membangunkan Celery pada jam-jam tertentu. |
| **Flower** | Halaman web untuk memantau pekerjaan Celery. |
| **DBeaver** | Aplikasi untuk *melihat isi tabel database* dengan tampilan seperti Excel. |
| **Raw table** | Tabel berisi data mentah persis seperti dari API. |
| **Fact table** | Tabel berisi data yang sudah bersih dan sudah dihitung. |
| **Upsert** | Kalau data belum ada → tambah (insert). Kalau sudah ada → perbarui (update). |

---

## 3. 🧭 Cara kerja program (gambaran besar)

```
┌──────────────┐
│  API Sumber  │  (/log_activity  dan  /petugas)
└──────┬───────┘
       │  tiap 1 jam (Celery Beat → Celery Worker)sekarang masih data dummy jadi kek ditambahi manual di table
       ▼
┌─────────────────────────────┐
│  STEP 1: EXTRACT            │  etl/extractor.py
│  Simpan data mentah         │
└──────┬──────────────────────┘
       ▼
┌─────────────────────────────┐
│  raw_log_activity           │  ← data mentah tiket
│  raw_petugas                │  ← data mentah petugas
└──────┬──────────────────────┘
       │  tiap jam 02:00 pagi (atau manual)
       ▼
┌─────────────────────────────┐
│  STEP 2: TRANSFORM          │  etl/transformer.py
│  A. Cleaning                │  hapus duplikat, perbaiki format tanggal
│  B. Processing              │  hitung is_selesai, response time, dll
│  C. Aggregation             │  buat tabel ringkasan
└──────┬──────────────────────┘
       ▼
┌─────────────────────────────────────────────┐
│  dim_petugas                  (master petugas)
│  fact_ticket_clean            (tiket bersih)
│  fact_productivity_summary    (skor petugas)
│  fact_hourly_pattern          (pola jam)
│  fact_ticket_trend            (tren tiket)
│  fact_jenis_masalah           (jenis masalah)
└──────┬──────────────────────────────────────┘
       ▼
┌─────────────────────────────┐
│  DASHBOARD (FastAPI)        │  dashboard/app.py
│  http://localhost:8000      │  grafik & tabel
└─────────────────────────────┘
```

> ⚠️ **Penting dipahami:** Pengambilan data (tiap 1 jam) hanya mengisi tabel *raw*. Tabel yang dibaca dashboard (`fact_...`) baru terisi saat proses **Transform** berjalan (otomatis jam 02:00, atau manual — lihat Step 9 di bagian setup).
> Itu sebabnya setelah pertama kali menyalakan program, dashboard bisa kosong sampai kamu menjalankan ETL manual.

### Rumus skor produktivitas petugas

```
Skor = (0.40 × tingkat_penyelesaian)
     + (0.30 × volume_score)
     + (0.15 × response_score)
     + (0.15 × resolution_score)
```

- **tingkat_penyelesaian** → seberapa banyak tiket (dibobot prioritas) yang diselesaikan
- **volume_score** → seberapa banyak tiket yang ditangani
- **response_score** → seberapa cepat merespon (lebih cepat = skor lebih tinggi)
- **resolution_score** → seberapa cepat menyelesaikan (lebih cepat = skor lebih tinggi)

---

## 4. 🗂️ Fungsi setiap file & folder

```
etl_sistem/
│
├── docker-compose.yml     ← Daftar semua "kotak" yang dinyalakan (database, redis, worker, dashboard, dll)
├── Dockerfile             ← Resep membuat image Python untuk worker, beat, flower, dashboard
├── requirements.txt       ← Daftar library Python yang dibutuhkan
├── .env                   ← PENGATURAN (password, alamat API, jadwal). File terpenting untuk diedit!
├── init_db.sql            ← Perintah pembuat semua tabel database (jalan otomatis pertama kali)
├── run_etl.py             ← Script untuk menjalankan ETL secara manual
├── README.md              ← File ini
│
├── config/
│   └── settings.py        ← Membaca isi .env dan membagikannya ke seluruh program
│
├── etl/
│   ├── extractor.py       ← STEP 1: ambil data dari API → simpan ke tabel raw
│   └── transformer.py     ← STEP 2: bersihkan, hitung, dan buat ringkasan
│
├── tasks/
│   └── celery_app.py      ← Mendefinisikan tugas Celery + jadwal otomatisnya
│
├── utils/
│   ├── db.py              ← Koneksi ke PostgreSQL
│   └── logger.py          ← Pencatat log (ke layar dan ke logs/etl.log)
│
├── dashboard/
│   ├── app.py             ← Backend dashboard (login + penyedia data untuk grafik)
│   ├── templates/
│   │   ├── login.html     ← Halaman login
│   │   └── dashboard.html ← Halaman dashboard
│   └── static/
│       ├── style.css      ← Tampilan/warna dashboard
│       └── logo.png       ← Logo (harus ada, kalau tidak dashboard error)
│
├── docs/guide.md          ← Panduan teknis lama
└── logs/etl.log           ← Catatan aktivitas program
```

### Container yang berjalan (dari `docker-compose.yml`)

| Container | Fungsi | Port |
|---|---|---|
| `etl_postgres` | Database PostgreSQL – tempat semua data | 5432 |
| `etl_redis` | Antrean tugas untuk Celery | 6379 |
| `etl_worker` | Pekerja yang menjalankan ETL | – |
| `etl_beat` | Penjadwal (alarm) yang memerintahkan worker | – |
| `etl_flower` | Halaman monitoring tugas Celery | 5555 |
| `etl_dashboard` | Dashboard web yang bisa dibuka di browser | 8000 |

---

## 5. 🚀 Setup pertama kali di device baru (step by step)

Ikuti urutan ini dari atas ke bawah. **Tidak perlu membuat tabel secara manual** – tabel dibuat otomatis oleh Docker lewat `init_db.sql`.

### ✅ STEP 1 – Install aplikasi yang dibutuhkan

| Aplikasi | Untuk apa | Download |
|---|---|---|
| **Docker Desktop** (wajib) | Menjalankan seluruh program | https://www.docker.com/products/docker-desktop |
| **DBeaver Community** (disarankan) | Melihat isi tabel database | https://dbeaver.io/download |

Setelah install Docker Desktop:
1. **Buka Docker Desktop** dan tunggu sampai statusnya hijau / "Engine running".
2. (Windows) Jika diminta, aktifkan **WSL 2** dan restart komputer.

Cek di terminal / PowerShell / CMD:

```bash
docker --version
docker compose version
```

Jika muncul nomor versi, Docker sudah siap.

### ✅ STEP 2 – Siapkan folder project

Salin seluruh folder project ke device baru (lewat flashdisk, Git, atau zip), misalnya ke `C:\etl_sistem` atau `~/etl_sistem`.

Pastikan file-file ini ada:
`docker-compose.yml`, `Dockerfile`, `requirements.txt`, `init_db.sql`, `.env`, dan folder `config`, `etl`, `tasks`, `utils`, `dashboard`.

> 💡 File `.env` kadang tersembunyi (nama diawali titik). Pastikan ikut tersalin.

### ✅ STEP 3 – Buka terminal di folder project

- **Windows:** buka folder project → klik kolom alamat → ketik `cmd` → Enter. Atau klik kanan → *Open in Terminal*.
- **Mac/Linux:** buka Terminal lalu `cd` ke folder project.

```bash
cd /lokasi/folder/etl_sistem
```

### ✅ STEP 4 – Atur file `.env`

Buka `.env` dengan Notepad / VS Code. Bagian yang **wajib dicek**:

```env
# Alamat API sumber data. SESUAIKAN dengan alamat API yang benar!
API_BASE_URL=http://host.docker.internal:7001
```

Penjelasan `API_BASE_URL`:
- Jika API berjalan **di komputer yang sama** dengan Docker → pakai `http://host.docker.internal:7001`
- Jika API berada di **komputer/server lain** → ganti dengan IP-nya, contoh `http://192.168.1.50:7001`

Bagian lain yang sebaiknya diganti (terutama jika dipakai sungguhan):

```env
POSTGRES_PASSWORD=etl_pass          # ganti dengan password kuat
FLOWER_USER=Admin
FLOWER_PASS=admin123                # ganti
DASHBOARD_SECRET=isi-kalimat-acak-panjang
DASHBOARD_ADMIN_USER=admin01        # username login dashboard
DASHBOARD_ADMIN_PASS=admin01        # password login dashboard (ganti!)
```

> ⚠️ **Jangan ubah** `POSTGRES_HOST=postgres` dan `REDIS_HOST=redis`. Itu nama container di dalam Docker, bukan `localhost`.

### ✅ STEP 5 – Build (pertama kali saja)

```bash
docker compose build
```

Proses ini mengunduh dan menyiapkan semuanya. **Butuh internet** dan bisa memakan beberapa menit. Tunggu sampai selesai tanpa error merah.

### ✅ STEP 6 – Nyalakan semua service

```bash
docker compose up -d
```

`-d` artinya berjalan di latar belakang. Saat pertama kali, PostgreSQL otomatis menjalankan `init_db.sql` dan **membuat semua tabel**.

### ✅ STEP 7 – Cek semua container berjalan

```bash
docker compose ps
```

Hasil yang diharapkan: `etl_postgres`, `etl_redis`, `etl_worker`, `etl_beat`, `etl_flower`, `etl_dashboard` berstatus **running** (postgres & redis: **healthy**).

Jika ada yang `exited` atau terus restart, lihat bagian [Troubleshooting](#11--troubleshooting-kalau-ada-masalah).

### ✅ STEP 8 – Pastikan tabel sudah terbuat

Cara cepat lewat terminal:

```bash
docker exec -it etl_postgres psql -U etl_user -d etl_db -c "\dt"
```

Harus muncul tabel-tabel seperti: `raw_log_activity`, `raw_petugas`, `dim_petugas`, `fact_ticket_clean`, `fact_productivity_summary`, `fact_hourly_pattern`, `fact_ticket_trend`, `fact_jenis_masalah`, `etl_run_log`, `etl_processed_tickets`, dan `app_users` (dibuat oleh dashboard).

Cara yang lebih enak dilihat → pakai **DBeaver** (lihat [bagian 6](#6--melihat-tabel-database-dengan-dbeaver)).

### ✅ STEP 9 – Jalankan ETL manual pertama kali (PENTING!)

Supaya dashboard langsung berisi data tanpa menunggu jadwal:

```bash
docker exec -it etl_worker python run_etl.py --mode all
```

Pilihan mode:

| Perintah | Fungsi |
|---|---|
| `--mode all` | Ambil data **dan** olah data (disarankan pertama kali) |
| `--mode extract` | Hanya ambil data dari API |
| `--mode transform` | Hanya olah data yang sudah ada di tabel raw |

Jika berhasil, akan muncul tulisan `✅ ETL selesai sukses!`.

### ✅ STEP 10 – Buka dashboard

Buka browser → **http://localhost:8000** → login dengan `DASHBOARD_ADMIN_USER` dan `DASHBOARD_ADMIN_PASS` dari `.env`.

🎉 **Selesai!** Program sudah aktif.

> 📝 Akun admin dashboard dibuat **sekali saja** saat pertama kali dashboard menyala (jika tabel `app_users` masih kosong). Jika kamu mengganti `DASHBOARD_ADMIN_PASS` di `.env` *setelah* akun terbuat, password lama tetap berlaku. Untuk mengulang dari awal, hapus akun lewat DBeaver (tabel `app_users`) lalu restart dashboard: `docker compose restart dashboard`.

---

## 6. 🔍 Melihat tabel database dengan DBeaver

DBeaver membantu kamu melihat isi tabel seperti melihat Excel.

### Cara menyambungkan DBeaver ke database Docker

1. Pastikan Docker sudah jalan (`docker compose ps` → `etl_postgres` healthy).
2. Buka **DBeaver** → klik ikon **colokan (+)** *New Database Connection* → pilih **PostgreSQL** → *Next*.
3. Isi sesuai `.env`:

| Kolom | Isi |
|---|---|
| Host | `localhost` |
| Port | `5432` |
| Database | `etl_db` |
| Username | `etl_user` |
| Password | `etl_pass` (atau sesuai `POSTGRES_PASSWORD` di `.env`) |

4. Klik **Test Connection**. Jika DBeaver meminta download *driver*, klik **Download**.
5. Klik **Finish**.

### Melihat tabel

Di panel kiri: `etl_db` → `Schemas` → `public` → `Tables`.
Klik dua kali tabel → tab **Data** untuk melihat isinya.

### Tabel apa saja yang ada?

| Tabel | Isi | Terisi saat |
|---|---|---|
| `raw_log_activity` | Data tiket mentah dari API | Extract |
| `raw_petugas` | Data petugas mentah dari API | Extract |
| `dim_petugas` | Master petugas bersih (id, nama, jabatan) | Transform |
| `fact_ticket_clean` | **Tiket bersih** + waktu respon, waktu penyelesaian, dll | Transform |
| `fact_productivity_summary` | Skor produktivitas petugas (harian/mingguan/bulanan) | Transform |
| `fact_hourly_pattern` | Jumlah tiket per jam per petugas | Transform |
| `fact_ticket_trend` | Tren jumlah tiket per hari/minggu/bulan | Transform |
| `fact_jenis_masalah` | Distribusi jenis masalah | Transform |
| `etl_run_log` | Riwayat setiap ETL berjalan (sukses/gagal) | Setiap task |
| `app_users` | Akun login dashboard | Dashboard menyala |
| `etl_processed_tickets` | *Sudah tidak dipakai* (sisa versi lama) | – |

> 💡 **Tips:** Tabel `etl_run_log` paling berguna untuk mengecek apakah program berjalan lancar. Kolom `status` berisi `running`, `success`, atau `failed`, dan kolom `error_msg` menjelaskan penyebab gagal.

---

## 7. 🔁 Cara menjalankan lagi setelah dimatikan

Ini yang dilakukan **setiap hari / setiap kali komputer menyala kembali**. Tidak perlu build ulang dan tidak perlu setup ulang. Data kamu **aman** karena tersimpan di Docker volume.

### Skenario A – Komputer dimatikan / restart

1. Nyalakan komputer.
2. **Buka Docker Desktop** dan tunggu sampai *Engine running*.
3. Biasanya semua container **otomatis hidup sendiri** (karena `restart: unless-stopped`). Cek:

```bash
docker compose ps
```

4. Jika belum hidup, buka terminal di folder project lalu:

```bash
docker compose up -d
```

5. Buka dashboard → http://localhost:8000

### Skenario B – Mau mematikan program dengan rapi

```bash
docker compose down
```

Semua container berhenti, **data tetap tersimpan**.

### Skenario C – Restart saja (misal habis ubah `.env` atau kode)

```bash
docker compose restart
```

Jika yang diubah adalah `requirements.txt` atau `Dockerfile`, harus build ulang:

```bash
docker compose up -d --build
```

### ⛔ JANGAN jalankan ini kecuali mau menghapus SEMUA data

```bash
docker compose down -v
```

Tanda `-v` **menghapus seluruh data database** (tiket, petugas, akun dashboard). Setelah itu kamu harus mengulang setup dari Step 6.

### Ringkasan cepat

| Situasi | Perintah |
|---|---|
| Menyalakan | `docker compose up -d` |
| Mengecek status | `docker compose ps` |
| Mematikan (data aman) | `docker compose down` |
| Restart | `docker compose restart` |
| Setelah ubah requirements/Dockerfile | `docker compose up -d --build` |
| Hapus semuanya + data ⚠️ | `docker compose down -v` |

---

## 8. 🌐 Membuka dashboard & Flower

| Layanan | Alamat | Login |
|---|---|---|
| **Dashboard Helpdesk** | http://localhost:8000 | `DASHBOARD_ADMIN_USER` / `DASHBOARD_ADMIN_PASS` di `.env` |
| **Flower** (monitor tugas) | http://localhost:5555 | `FLOWER_USER` / `FLOWER_PASS` di `.env` |

Mengakses dari komputer lain di jaringan yang sama: ganti `localhost` dengan IP komputer yang menjalankan Docker, misal `http://192.168.1.20:8000`.

Dashboard memperbarui datanya sendiri setiap 60 detik. Pilihan rentang waktu (7 / 30 / 90 / 365 hari) ada di kanan atas.

Jika dashboard menampilkan **"Belum ada data. Jalankan ETL dulu."** → jalankan Step 9 di atas.

---

## 9. ⏰ Jadwal otomatis

Diatur oleh **Celery Beat** dan bisa diubah di `.env`.

| Tugas | Jadwal default | Yang dilakukan |
|---|---|---|
| `task_fetch_data` | Setiap 1 jam | Ambil data terbaru dari API → tabel raw |
| `task_run_etl` | Setiap hari jam 02:00 (WIB) | Ambil data **+** olah data + buat semua ringkasan |

Mengubah jadwal di `.env`:

```env
SCHEDULE_FETCH_INTERVAL_HOURS=1   # ambil data tiap berapa jam
SCHEDULE_ETL_HOUR=2               # jam ETL penuh (0–23)
SCHEDULE_ETL_MINUTE=0
```

Setelah mengubah `.env`, jalankan: `docker compose restart celery_beat celery_worker`

> Jika tugas gagal, Celery otomatis mencoba lagi (maksimal 2–3 kali). Hasilnya tercatat di tabel `etl_run_log` dan terlihat di bagian **Riwayat proses ETL** pada dashboard.

---

## 10. 🛠️ Perintah berguna

```bash
# Melihat log (tekan Ctrl+C untuk berhenti melihat)
docker logs etl_worker -f          # log pekerja ETL
docker logs etl_beat -f            # log penjadwal
docker logs etl_dashboard -f       # log dashboard
docker logs etl_postgres           # log database

# Menjalankan ETL manual
docker exec -it etl_worker python run_etl.py --mode all
docker exec -it etl_worker python run_etl.py --mode extract
docker exec -it etl_worker python run_etl.py --mode transform

# Memicu tugas Celery manual
docker exec etl_worker celery -A tasks.celery_app call tasks.celery_app.task_run_etl
docker exec etl_worker celery -A tasks.celery_app call tasks.celery_app.task_fetch_data

# Cek riwayat ETL langsung dari terminal
docker exec etl_postgres psql -U etl_user -d etl_db -c \
  "SELECT task_name, status, rows_new, started_at FROM etl_run_log ORDER BY started_at DESC LIMIT 10;"

# Menghitung isi tabel utama
docker exec etl_postgres psql -U etl_user -d etl_db -c \
  "SELECT (SELECT COUNT(*) FROM raw_log_activity) AS raw_log,
          (SELECT COUNT(*) FROM raw_petugas) AS raw_petugas,
          (SELECT COUNT(*) FROM fact_ticket_clean) AS fact_ticket;"
```

---

## 11. ❓ Troubleshooting (kalau ada masalah)

### Docker error / `Cannot connect to the Docker daemon`
→ Docker Desktop belum jalan. Buka Docker Desktop dan tunggu sampai *Engine running*.

### Port sudah dipakai (`port is already allocated`)
→ Ada program lain yang memakai port 5432 / 6379 / 8000 / 5555. Tutup program tersebut, atau ubah angka di kiri pada bagian `ports:` di `docker-compose.yml` (misal `"5433:5432"`).

### Dashboard kosong / "Belum ada data"
→ Jalankan `docker exec -it etl_worker python run_etl.py --mode all`. Lalu cek apakah tabel `raw_log_activity` ada isinya di DBeaver. Jika raw kosong → masalahnya di API (lihat di bawah).

### Data tidak masuk / API tidak bisa diakses
1. Cek `API_BASE_URL` di `.env`.
2. Tes dari dalam container:
   ```bash
   docker exec etl_worker curl http://host.docker.internal:7001/log_activity
   ```
3. Jika API ada di komputer lain, pastikan kedua perangkat satu jaringan (atau VPN seperti Tailscale menyala) dan firewall tidak memblokir.
4. **Linux:** `host.docker.internal` tidak selalu tersedia. Gunakan IP komputer langsung, atau tambahkan pada service di `docker-compose.yml`:
   ```yaml
   extra_hosts:
     - "host.docker.internal:host-gateway"
   ```
5. Setelah mengubah `.env`: `docker compose restart`.

### Worker tidak bisa konek ke database
→ Pastikan di `.env`: `POSTGRES_HOST=postgres` (**bukan** `localhost`).

### Tabel tidak terbuat otomatis
`init_db.sql` hanya berjalan saat volume database masih kosong (pertama kali). Jika terlewat, jalankan manual:

```bash
docker exec -i etl_postgres psql -U etl_user -d etl_db < init_db.sql
```

### Dashboard error karena `logo.png` / `static` tidak ditemukan
→ Pastikan folder `dashboard/static/` berisi `style.css` dan `logo.png`.

### Lupa password dashboard
→ Buka DBeaver → tabel `app_users` → hapus barisnya → `docker compose restart dashboard` (akun admin dibuat ulang dari `.env`).

### Container terus restart
```bash
docker compose logs <nama_service>
# contoh:
docker compose logs celery_worker
```
Baca baris error paling bawah.

### Mau mengulang dari nol
```bash
docker compose down -v      # ⚠️ menghapus semua data
docker compose up -d --build
docker exec -it etl_worker python run_etl.py --mode all
```

---

## 12. 🔐 Keamanan sebelum dipakai sungguhan

1. Ganti `POSTGRES_PASSWORD`, `FLOWER_PASS`, `DASHBOARD_ADMIN_PASS`, dan `DASHBOARD_SECRET` di `.env` dengan nilai yang kuat.
2. **Jangan** buka port 5432 (database) dan 6379 (Redis) ke internet.
3. Jangan upload `.env` ke GitHub / publik (tambahkan ke `.gitignore`).
4. Jika server bisa diakses dari luar, batasi akses dashboard (port 8000) dan Flower (port 5555) lewat firewall atau VPN.

---

## ✅ Ringkasan Super Singkat

**Pertama kali di device baru:**
1. Install **Docker Desktop** (+ **DBeaver** untuk melihat tabel)
2. Salin folder project, cek & atur `.env`
3. `docker compose build`
4. `docker compose up -d`
5. `docker exec -it etl_worker python run_etl.py --mode all`
6. Buka http://localhost:8000

**Hari-hari berikutnya:**
1. Buka Docker Desktop
2. `docker compose up -d` (jika belum otomatis hidup)
3. Buka http://localhost:8000