"""Helpdesk Track – dashboard monitoring (FastAPI) di atas data hasil ETL."""
import hashlib, hmac, os, secrets

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware

from utils.db import engine

BASE = os.path.dirname(__file__)
app = FastAPI(title="Helpdesk Track")
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("DASHBOARD_SECRET", "ganti-secret-ini"),
    max_age=60 * 60 * 8,  # sesi login 8 jam
    same_site="lax",
)
app.mount("/static", StaticFiles(directory=os.path.join(BASE, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE, "templates"))


# ── Password (stdlib, tanpa dependensi tambahan) ─────────────
def hash_pw(pw: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(8)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 120_000).hex()
    return f"{salt}${h}"


def check_pw(pw: str, stored: str) -> bool:
    salt, _ = stored.split("$", 1)
    return hmac.compare_digest(hash_pw(pw, salt), stored)


@app.on_event("startup")
def init_users():
    with engine.begin() as c:
        c.execute(text("""
            CREATE TABLE IF NOT EXISTS app_users (
                id BIGSERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW())"""))
        if c.execute(text("SELECT COUNT(*) FROM app_users")).scalar() == 0:
            c.execute(text("INSERT INTO app_users (username, password_hash) VALUES (:u, :p)"), {
                "u": os.getenv("DASHBOARD_ADMIN_USER", "admin"),
                "p": hash_pw(os.getenv("DASHBOARD_ADMIN_PASS", "admin123")),
            })


def q(sql: str, **params):
    with engine.connect() as c:
        return [dict(r._mapping) for r in c.execute(text(sql), params)]


def need_login(request: Request):
    if not request.session.get("user"):
        raise HTTPException(401, "Belum login")


# ── Halaman ──────────────────────────────────────────────────
@app.get("/login")
def login_page(request: Request):
    if request.session.get("user"):
        return RedirectResponse("/", 302)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    rows = q("SELECT password_hash FROM app_users WHERE username = :u", u=username.strip())
    if not rows or not check_pw(password, rows[0]["password_hash"]):
        return templates.TemplateResponse(
            request, "login.html", {"error": "Username atau password salah."}, status_code=401)
    request.session["user"] = username.strip()
    return RedirectResponse("/", 303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", 302)


@app.get("/")
def home(request: Request):
    if not request.session.get("user"):
        return RedirectResponse("/login", 302)
    return templates.TemplateResponse(request, "dashboard.html", {"user": request.session["user"]})


# ── Pemetaan kode jenis masalah → nama masalah IT helpdesk ───
# SESUAIKAN dengan kode di sistem kamu. Kode yang belum terdaftar
# tampil sebagai "Jenis <kode>" supaya tetap terbaca.
JENIS_MAP = {
    "1": "Jaringan / Internet",
    "2": "Hardware (PC / Laptop)",
    "3": "Software / Aplikasi",
    "4": "Akun & Password",
    "5": "Email",
    "6": "Printer & Scanner",
    "7": "Server & Database",
    "8": "CCTV & Perangkat Pendukung",
    "9": "Lainnya",
}


def nama_jenis(v) -> str:
    k = str(v).strip()
    if k in JENIS_MAP:
        return JENIS_MAP[k]
    return f"Jenis {k}" if k.isdigit() else k


# ── API data (dipakai Chart.js) ──────────────────────────────
WHERE = "created_date >= CURRENT_DATE - CAST(:d AS integer)"


@app.get("/api/summary")
def summary(request: Request, d: int = 30):
    need_login(request)
    return q(f"""SELECT COUNT(*) AS total, COALESCE(SUM(is_selesai),0) AS selesai,
                 ROUND(AVG(response_time_minutes)::numeric,1) AS avg_response,
                 ROUND(AVG(resolution_time_minutes)::numeric,1) AS avg_resolution
                 FROM fact_ticket_clean WHERE {WHERE}""", d=d)[0]


@app.get("/api/trend")
def trend(request: Request, d: int = 30):
    need_login(request)
    return q(f"""SELECT created_date::text AS label, COUNT(*) AS total, COALESCE(SUM(is_selesai),0) AS selesai
                 FROM fact_ticket_clean WHERE {WHERE} GROUP BY created_date ORDER BY created_date""", d=d)


@app.get("/api/hourly")
def hourly(request: Request, d: int = 30):
    need_login(request)
    return q(f"""SELECT created_hour AS label, COUNT(*) AS total FROM fact_ticket_clean
                 WHERE {WHERE} GROUP BY created_hour ORDER BY created_hour""", d=d)


# Kode jenis_masalah -> nama masalah IT helpdesk.
# SESUAIKAN dengan kode di data kamu. Kode yang tidak ada di sini tampil sebagai "Lainnya (kode X)".
JENIS_MASALAH = {
    "1": "Jaringan & Internet",
    "2": "Hardware / Perangkat",
    "3": "Aplikasi / Software",
    "4": "Akun & Hak Akses",
    "5": "Printer & Scanner",
    "6": "Email",
    "7": "Server & Database",
    "8": "Instalasi & Konfigurasi",
}


def nama_jenis(kode: str) -> str:
    kode = (kode or "").strip()
    if kode in JENIS_MASALAH:
        return JENIS_MASALAH[kode]
    return f"Lainnya (kode {kode})" if kode.isdigit() else kode


@app.get("/api/jenis")
def jenis(request: Request, d: int = 30):
    need_login(request)
    rows = q(f"""SELECT TRIM(jenis_masalah) AS kode, COUNT(*) AS total FROM fact_ticket_clean
                 WHERE jenis_masalah IS NOT NULL AND {WHERE} GROUP BY TRIM(jenis_masalah)""", d=d)
    agg = {}
    for r in rows:
        n = nama_jenis(r["kode"])
        agg[n] = agg.get(n, 0) + r["total"]
    top = sorted(agg.items(), key=lambda x: -x[1])[:8]
    return [{"label": k, "total": v} for k, v in top]


@app.get("/api/leaderboard")
def leaderboard(request: Request):
    need_login(request)
    return q("""SELECT COALESCE(d.nama, p.id_petugas) AS petugas, p.total_tiket, p.total_selesai,
                p.skor_produktivitas AS skor, p.avg_response_minutes AS avg_response, p.periode_value AS periode
                FROM fact_productivity_summary p
                LEFT JOIN dim_petugas d ON d.id_petugas = p.id_petugas
                WHERE p.periode_type = 'monthly'
                  AND p.periode_value = (SELECT MAX(periode_value) FROM fact_productivity_summary WHERE periode_type='monthly')
                ORDER BY p.skor_produktivitas DESC LIMIT 10""")


@app.get("/api/etl-log")
def etl_log(request: Request):
    need_login(request)
    return q("""SELECT task_name, status, rows_new,
                TO_CHAR(started_at AT TIME ZONE 'Asia/Jakarta','DD Mon HH24:MI') AS mulai
                FROM etl_run_log ORDER BY started_at DESC LIMIT 6""")
