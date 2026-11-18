"""
seed_data.py
────────────
Mengisi tabel RAW secara manual (tanpa API) supaya dashboard tidak kosong:

  1. raw_petugas       → 12 petugas (data asli dari kamu)
  2. raw_log_activity  → tiket contoh (data buatan) dari tanggal MULAI sampai SELESAI

Default rentang tanggal:
  mulai   = hari ini
  selesai = 31 Desember TAHUN DEPAN
  (otomatis menyesuaikan kapan pun script dijalankan)

Cara pakai (dari folder project, Docker sudah menyala):
  docker exec -it etl_worker python seed_data.py
  docker exec -it etl_worker python seed_data.py --start 2026-11-18 --end 2028-12-31
  docker exec -it etl_worker python seed_data.py --no-transform   # isi raw saja

Aman dijalankan berulang kali:
  - Data tiap hari dibuat deterministik (hasil sama setiap dijalankan)
  - Tiket yang sudah ada dilewati (ON CONFLICT DO NOTHING), tidak dobel

Semua tiket buatan punya id_masalah berawalan "SEED-", sehingga mudah dihapus:
  DELETE FROM raw_log_activity   WHERE id_masalah LIKE 'SEED-%';
  DELETE FROM fact_ticket_clean  WHERE id_masalah LIKE 'SEED-%';
"""

import argparse
import random
from datetime import date, datetime, timedelta, time

# ──────────────────────────────────────────────────────────────
# DATA PETUGAS (dari tabel kamu)
# ──────────────────────────────────────────────────────────────
PETUGAS = [
    ("1",  "joen jungkook",                "Helpdesk Agent"),
    ("2",  "Judarna Khoirunnisa Anjalina", "Helpdesk Agent"),
    ("3",  "Destri Rahma Wani",            "Helpdesk Agent"),
    ("4",  "Devano Danendra Rafif",        "Helpdesk Agent"),
    ("5",  "Iman Carrazi Syamsidi",        "Helpdesk Agent"),
    ("6",  "Angelica Regina Irvan",        "Helpdesk Agent"),
    ("7",  "Muhammad Rafi Irvansyah",      "Helpdesk Agent"),
    ("8",  "Nadhila Bazhlina",             "Helpdesk Agent"),
    ("9",  "Reski Windradiaksa",           "Helpdesk Agent"),
    ("10", "Valencia Maharani Sonia Putri", "Helpdesk Agent"),
    ("11", "Anggieta Fatia",               "helpdesk"),
    ("12", "lin yi",                       "Agent"),
]
PETUGAS_IDS = [p[0] for p in PETUGAS]

# ──────────────────────────────────────────────────────────────
# KAMUS DATA TIKET (sesuaikan bila perlu)
# kode jenis_masalah sama dengan JENIS_MASALAH di dashboard/app.py
#   kode: (bobot, [masalah], [penyebab], [penyelesaian], (menit_min, menit_max))
# ──────────────────────────────────────────────────────────────
JENIS = {
    "1": (25, ["Internet lambat", "WiFi tidak bisa terhubung", "Koneksi jaringan sering putus"],
              ["Kabel LAN longgar", "Access point bermasalah", "Gangguan dari provider internet"],
              ["Kabel LAN diganti", "Access point di-restart", "Eskalasi ke provider internet"], (15, 180)),
    "2": (20, ["Laptop tidak mau menyala", "Komputer sering hang", "Keyboard atau mouse rusak"],
              ["Adaptor rusak", "RAM kurang", "Perangkat sudah aus"],
              ["Adaptor diganti", "RAM ditambah", "Perangkat diganti unit cadangan"], (30, 480)),
    "3": (18, ["Aplikasi error saat dibuka", "Aplikasi kantor tidak bisa login", "Aplikasi lambat"],
              ["Versi aplikasi usang", "Cache penuh", "Bug pada aplikasi"],
              ["Aplikasi diperbarui", "Cache dibersihkan", "Instal ulang aplikasi"], (20, 240)),
    "4": (12, ["Lupa password", "Akun terkunci", "Butuh akses folder bersama"],
              ["Password salah berulang kali", "Masa berlaku password habis", "Hak akses belum diberikan"],
              ["Password direset", "Akun dibuka kembali", "Hak akses ditambahkan"], (5, 60)),
    "5": (8,  ["Printer tidak mencetak", "Hasil cetak bergaris", "Scanner tidak terdeteksi"],
              ["Tinta atau toner habis", "Kepala printer kotor", "Driver belum terpasang"],
              ["Tinta atau toner diganti", "Kepala printer dibersihkan", "Driver dipasang ulang"], (15, 120)),
    "6": (7,  ["Email tidak bisa dikirim", "Email tidak masuk", "Kapasitas mailbox penuh"],
              ["Konfigurasi email salah", "Mailbox penuh", "Gangguan server email"],
              ["Konfigurasi diperbaiki", "Mailbox dibersihkan", "Menunggu pemulihan server email"], (10, 120)),
    "7": (4,  ["Database tidak bisa diakses", "Server aplikasi lambat", "Backup gagal"],
              ["Disk server penuh", "Service berhenti", "Beban server tinggi"],
              ["Disk dibersihkan", "Service dijalankan ulang", "Resource server ditambah"], (60, 600)),
    "8": (6,  ["Permintaan instalasi aplikasi", "Setup perangkat baru", "Konfigurasi VPN"],
              ["Permintaan karyawan baru", "Pergantian perangkat", "Kebutuhan kerja remote"],
              ["Aplikasi diinstal", "Perangkat dikonfigurasi", "VPN dikonfigurasi"], (20, 180)),
}
JENIS_KODE = list(JENIS.keys())
JENIS_BOBOT = [JENIS[k][0] for k in JENIS_KODE]

NAMA_KARYAWAN = [
    "Budi Santoso", "Siti Aminah", "Agus Pratama", "Dewi Lestari", "Rizky Hidayat",
    "Maya Sari", "Hendra Wijaya", "Putri Ayu", "Eko Saputra", "Rina Marlina",
    "Fajar Nugroho", "Lestari Wulandari", "Doni Kurniawan", "Yuni Astuti", "Andi Firmansyah",
]
CABANG = ["CBG-01", "CBG-02", "CBG-03", "CBG-04", "CBG-05"]
DAMPAK = ["Rendah", "Sedang", "Tinggi"]
TARGET = ["Individu", "Satu divisi", "Seluruh kantor"]
KLASIFIKASI = ["Incident", "Request"]
KOMENTAR = [None, None, None, "Sudah dikonfirmasi ke pelapor", "Menunggu konfirmasi pelapor",
            "Perlu dipantau beberapa hari"]

# Jam tiket masuk (08:00 – 17:59), ramai pagi & setelah makan siang
JAM = list(range(8, 18))
JAM_BOBOT = [6, 12, 14, 12, 5, 8, 12, 10, 7, 4]

FMT_FULL = "%Y-%m-%d %H:%M:%S"
FMT_JAM = "%H:%M:%S"


# ──────────────────────────────────────────────────────────────
# GENERATOR TIKET
# ──────────────────────────────────────────────────────────────
def generate_day(day: date) -> list[dict]:
    """Buat tiket untuk satu hari. Hasil selalu sama untuk tanggal yang sama."""
    rng = random.Random(day.isoformat())
    jumlah = rng.randint(2, 6) if day.weekday() >= 5 else rng.randint(8, 25)
    rows = []

    for n in range(1, jumlah + 1):
        kode = rng.choices(JENIS_KODE, weights=JENIS_BOBOT)[0]
        _, masalah, penyebab, penyelesaian, (res_min, res_max) = JENIS[kode]
        idx = rng.randrange(len(masalah))

        jam = rng.choices(JAM, weights=JAM_BOBOT)[0]
        diterima = datetime.combine(day, time(jam, rng.randint(0, 59), rng.randint(0, 59)))
        kejadian = diterima - timedelta(minutes=rng.randint(0, 30))

        prioritas = rng.choices(["1", "2", "3"], weights=[55, 30, 15])[0]
        petugas = rng.choice(PETUGAS_IDS)
        status = rng.choices(["2", "1", "0"], weights=[90, 7, 3])[0]  # 2=selesai, 1=proses, 0=baru

        respon_menit = rng.randint(2, 15) if prioritas == "3" else rng.randint(5, 45)
        tanggap = diterima + timedelta(minutes=respon_menit)
        selesai = diterima + timedelta(minutes=respon_menit + rng.randint(res_min, res_max))

        row = {
            "id_masalah": f"SEED-{day:%Y%m%d}-{n:03d}",
            "tiket": f"TKT-{day:%Y%m%d}-{n:03d}",
            "waktu_kejadian": kejadian.strftime(FMT_FULL),
            "prioritas": prioritas,
            "dampak": rng.choice(DAMPAK),
            "target": rng.choice(TARGET),
            "pihak": "Internal",
            "jenis_masalah": kode,
            "klasifikasi": rng.choice(KLASIFIKASI),
            "tgl_diterima": diterima.strftime(FMT_FULL),
            "id_cabang": rng.choice(CABANG),
            "usr": rng.choice(NAMA_KARYAWAN),
            "pelapor": rng.choice(NAMA_KARYAWAN),
            "masalah": masalah[idx],
            "waktu_tanggap": None,
            "penyebab": None,
            "penyelesaian": None,
            "waktu_penyelesaian": None,
            "tgl_selesai": None,
            "tgl_esk": None,
            "status": status,
            "petugas": petugas,
            "komentar": rng.choice(KOMENTAR),
            "eskalasi": None,
            "petugas_esk": None,
            "batch_id": "seed",
        }

        # Kolom jam saja ("09:15:00") – sama seperti format data asli
        if status in ("1", "2"):
            row["waktu_tanggap"] = tanggap.strftime(FMT_JAM)
        if status == "2":
            row["penyebab"] = penyebab[idx]
            row["penyelesaian"] = penyelesaian[idx]
            row["waktu_penyelesaian"] = selesai.strftime(FMT_JAM)
            row["tgl_selesai"] = selesai.strftime(FMT_FULL)

        # ±8% tiket dieskalasi ke petugas lain
        if rng.random() < 0.08:
            row["eskalasi"] = "1"
            row["petugas_esk"] = rng.choice([p for p in PETUGAS_IDS if p != petugas])
            row["tgl_esk"] = (tanggap + timedelta(minutes=rng.randint(10, 60))).strftime(FMT_FULL)

        rows.append(row)

    return rows


def generate_range(start: date, end: date) -> list[dict]:
    rows, day = [], start
    while day <= end:
        rows.extend(generate_day(day))
        day += timedelta(days=1)
    return rows


# ──────────────────────────────────────────────────────────────
# INSERT KE DATABASE
# ──────────────────────────────────────────────────────────────
def seed_petugas() -> int:
    from sqlalchemy import text
    from utils.db import get_connection

    sql = text("""
        INSERT INTO raw_petugas (id_petugas, nama, position, batch_id)
        VALUES (:id_petugas, :nama, :position, 'seed')
        ON CONFLICT (id_petugas) DO UPDATE SET
            nama       = EXCLUDED.nama,
            position   = EXCLUDED.position,
            fetched_at = NOW(),
            updated_at = NOW()
    """)
    rows = [{"id_petugas": i, "nama": n.strip(), "position": p.strip()} for i, n, p in PETUGAS]
    with get_connection() as conn:
        conn.execute(sql, rows)
    return len(rows)


def seed_tickets(rows: list[dict], chunk: int = 1000) -> int:
    from sqlalchemy import text
    from utils.db import get_connection

    sql = text("""
        INSERT INTO raw_log_activity (
            id_masalah, tiket, waktu_kejadian, prioritas, dampak,
            target, pihak, jenis_masalah, klasifikasi, tgl_diterima,
            id_cabang, "user", pelapor, masalah, waktu_tanggap,
            penyebab, penyelesaian, waktu_penyelesaian, tgl_selesai,
            tgl_esk, status, petugas, komentar, eskalasi,
            petugas_esk, batch_id
        ) VALUES (
            :id_masalah, :tiket, :waktu_kejadian, :prioritas, :dampak,
            :target, :pihak, :jenis_masalah, :klasifikasi, :tgl_diterima,
            :id_cabang, :usr, :pelapor, :masalah, :waktu_tanggap,
            :penyebab, :penyelesaian, :waktu_penyelesaian, :tgl_selesai,
            :tgl_esk, :status, :petugas, :komentar, :eskalasi,
            :petugas_esk, :batch_id
        )
        ON CONFLICT (id_masalah) DO NOTHING
    """)

    with get_connection() as conn:
        before = conn.execute(text("SELECT COUNT(*) FROM raw_log_activity")).scalar()
        for i in range(0, len(rows), chunk):
            conn.execute(sql, rows[i:i + chunk])
        after = conn.execute(text("SELECT COUNT(*) FROM raw_log_activity")).scalar()
    return after - before


# ──────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────
def main():
    today = date.today()
    parser = argparse.ArgumentParser(description="Isi tabel raw dengan data petugas & tiket contoh")
    parser.add_argument("--start", type=date.fromisoformat, default=today,
                        help="tanggal mulai YYYY-MM-DD (default: hari ini)")
    parser.add_argument("--end", type=date.fromisoformat, default=date(today.year + 1, 12, 31),
                        help="tanggal selesai YYYY-MM-DD (default: 31 Des tahun depan)")
    parser.add_argument("--no-transform", action="store_true",
                        help="jangan jalankan Transform setelah mengisi raw")
    args = parser.parse_args()

    if args.end < args.start:
        raise SystemExit("❌ --end tidak boleh lebih kecil dari --start")

    print(f"▶ Mengisi raw_petugas ...")
    print(f"  {seed_petugas()} petugas di-upsert")

    print(f"▶ Membuat tiket {args.start} s/d {args.end} ...")
    rows = generate_range(args.start, args.end)
    print(f"  {len(rows)} tiket dibuat, memasukkan ke raw_log_activity ...")
    baru = seed_tickets(rows)
    print(f"  {baru} tiket BARU masuk ({len(rows) - baru} sudah ada, dilewati)")

    if args.no_transform:
        print("⏭  Transform dilewati (--no-transform). Jalankan: python run_etl.py --mode transform")
    else:
        print("▶ Menjalankan Transform (isi fact_* dan dim_petugas) ...")
        from etl.transformer import run_transform
        hasil = run_transform()
        print(f"  Transform selesai: {hasil}")

    print("✅ Selesai! Buka dashboard: http://localhost:8000")


if __name__ == "__main__":
    main()
