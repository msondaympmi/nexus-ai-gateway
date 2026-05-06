# Nexus AI Gateway

Pusat Layanan M2M AI Services Platform (MASP) terintegrasi untuk seluruh aplikasi internal di **MPM Insurance**. Nexus bertindak sebagai gerbang terpadu untuk Chat/RAG, OCR asinkron, perangkum dokumen, pencatatan biaya riil, pembatasan laju (*rate limiting*), serta pencegahan perulangan agen otomatis.

---

## 🚀 Fitur Utama

*   **Multi-tenant & Isolated API Keys**: Otentikasi aman berbasis prefiks dengan penyimpanan hash bcrypt untuk melindungi data transaksi antar aplikasi klien internal.
*   **Dual Response Mode (Sync/Async)**: Mendukung eksekusi AI langsung (*synchronous*) atau asinkron (*asynchronous*) menggunakan antrean Redis `arq` dan notifikasi webhooks bertanda tangan HMAC.
*   **Sliding Window Rate Limiter**: Pembatasan jumlah *request* berbasis Sorted Set Redis per menit (RPM) dan per hari (RPD).
*   **Loop Prevention (Hourly Budget)**: Penghentian otomatis jika total konsumsi token aplikasi klien melebihi **10,000,000 token per jam** guna mencegah loop tanpa akhir pada agen klien.
*   **Centralized Cost Tracking**: Audit biaya riil otomatis dalam USD untuk setiap transaksi LLM berdasarkan tabel tarif per model.
*   **Centralized Knowledge Base (RAG)**: Penyimpanan indeks dokumen pintar terisolasi berbasis pencarian vektor GCP Firestore.
*   **Streamlit Admin Dashboard**: Panel visual premium untuk pendaftaran aplikasi, pengelolaan rate-limits, serta grafik pengeluaran dana AI.

---

## 🛠️ Tech Stack

*   **Core API Framework**: Python 3.11 & FastAPI
*   **Background Jobs & Queues**: arq (Redis-backed task queue)
*   **Database & ORM**: MySQL 8.0 & SQLAlchemy 2.0 (Async Engine via `aiomysql`)
*   **AI Gateway Adaptor**: LiteLLM Proxy (menghubungkan ke Gemini 1.5 Pro & Flash)
*   **Knowledge Base**: Google Cloud Firestore (Vector Search)
*   **Admin Dashboard**: Streamlit (Premium Custom CSS & Outfit Typography)
*   **Encryption & Security**: `cryptography` (Fernet) & `passlib` (Bcrypt)

---

## 📋 Prasyarat Sistem

*   **Python 3.11** atau lebih tinggi
*   **Redis 7.0** atau lebih tinggi
*   **MySQL 8.0** atau lebih tinggi
*   **Docker & Docker Compose** (Sangat Direkomendasikan untuk instalasi cepat)

---

## 📥 Panduan Instalasi Lokal

### 1. Kloning Repositori
```powershell
git clone c:\Code\aigateway
cd aigateway
```

### 2. Pasang Dependensi Python
```powershell
pip install -r requirements.txt
```

### 3. Konfigurasi Lingkungan (.env)
Salin contoh file `.env.example` ke `.env`:
```powershell
cp .env.example .env
```

Isi dan sesuaikan variabel lingkungan berikut:

| Variabel | Deskripsi | Nilai Default / Contoh |
| :--- | :--- | :--- |
| `ENVIRONMENT` | Lingkungan runtime aplikasi | `development` / `production` |
| `DEBUG` | Mode debug FastAPI | `true` |
| `DATABASE_URL` | Koneksi database MySQL asinkron | `mysql+aiomysql://user:pass@localhost/nexus_db` |
| `REDIS_URL` | Koneksi Redis asinkron | `redis://localhost:6379/0` |
| `LITELLM_API_BASE` | Endpoint proxy LiteLLM | `http://localhost:4000` |
| `ADMIN_API_KEY` | Kunci akses endpoint Admin | `nexus_super_admin_key_2026` |
| `ENCRYPTION_KEY` | Kunci simetris enkripsi Webhook Secret | *Generate via Fernet.generate_key()* |

---

## 🐳 Eksekusi Menggunakan Docker (Rekomendasi)

Untuk menyalakan seluruh ekosistem (FastAPI Server, arq Worker, MySQL, dan Redis) secara instan menggunakan Docker Compose, jalankan:

```powershell
docker compose up --build
```

Setelah menyala:
*   **FastAPI API**: Dapat diakses di `http://localhost:8100` (terikat ke `127.0.0.1` demi keamanan).
*   **Dokumentasi Swagger (OpenAPI)**: Dapat diakses di `http://localhost:8100/docs` (jika `DEBUG=true`).
*   **MySQL Server**: Berjalan di port lokal `3306`.

---

## 🏛️ Arsitektur Direktori Proyek

```
c:\Code\aigateway\
├── requirements.txt            # Dependensi pustaka terkuci
├── Dockerfile                  # Setelan containerization app
├── docker-compose.yml          # Orkestrasi multi-container lokal
├── config.py                   # Validasi Pydantic global settings
├── database.py                 # Async engine & sesi SQLAlchemy
├── models.py                   # Skema tabel database MySQL
├── main.py                     # Entrypoint FastAPI & middleware pelacak
├── worker.py                   # Eksekutor antrean asinkron (arq)
├── webhook_dispatcher.py       # Pengirim callback HMAC & Tenacity retries
├── admin_dashboard.py          # Visualisasi panel Admin Streamlit
├── middleware/
│   ├── auth.py                 # Otentikasi kunci & Redis Auth Cache
│   └── rate_limiter.py         # Sliding window limiter & Loop Prevention
└── modules/
    ├── chat/                   # POST /v1/ai/chat (Gemini, RAG, Tools)
    ├── ocr/                    # POST /v1/ai/ocr (Multimodality OCR)
    ├── summarize/              # POST /v1/ai/summarize (Dual-mode summarization)
    ├── knowledge/              # POST /v1/ai/knowledge (Ingestion Firestore)
    ├── jobs/                   # GET /v1/ai/jobs/{job_id} (Pemantauan antrean)
    └── admin/                  # /v1/admin/* (CRUD Apps, Cost Auditing)
```

---

## 🔌 Referensi API Utama

Seluruh request wajib menyertakan header otentikasi kunci aplikasi klien:
*   Header: `Authorization: Bearer <API_KEY_ANDA>` atau `X-API-Key: <API_KEY_ANDA>`

### 1. Chat Completion & RAG (`POST /v1/ai/chat`)
Eksekusi obrolan AI cerdas dengan opsional pelengkap dokumen asuransi:
```json
{
  "messages": [
    {"role": "user", "content": "Bagaimana prosedur pelaporan klaim?"}
  ],
  "model": "gemini-1.5-pro",
  "use_rag": true
}
```

### 2. Dual-Mode Text Summarization (`POST /v1/ai/summarize`)
Untuk meringkas teks secara langsung atau asinkron di background:
*   Header opsional: `X-Response-Mode: async`
*   Header opsional: `X-Webhook-Callback-URI: https://klien.app/callback`

**JSON Request:**
```json
{
  "text": "Konten teks dokumen panjang MPM Insurance...",
  "length": "short",
  "model": "gemini-1.5-flash"
}
```

**Response Asinkron (HTTP 202):**
```json
{
  "job_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3d4bad",
  "status": "queued",
  "poll_url": "/v1/ai/jobs/9b1deb4d-3b7d-4bad-9bdd-2b0d7b3d4bad"
}
```

### 3. Pemantauan Status Pekerjaan (`GET /v1/ai/jobs/{job_id}`)
Gunakan untuk polling berkala guna mengetahui hasil pemrosesan asinkron:
```json
{
  "job_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3d4bad",
  "status": "done",
  "endpoint": "/v1/ai/summarize",
  "queued_at": "2026-05-07T03:40:00",
  "completed_at": "2026-05-07T03:40:12",
  "latency_ms": 12000,
  "result": {
    "summary": "Ini adalah rangkuman otomatis asinkron dari dokumen Anda."
  }
}
```

---

## 🖥️ Panel Manajemen Visual

Nyalakan Streamlit Admin Web Dashboard untuk mendaftarkan sistem aplikasi klien internal baru secara visual:

```powershell
streamlit run admin_dashboard.py
```
Akses langsung di browser Anda: **`http://localhost:8501`**

---

## 🔒 Skema Keamanan & Verifikasi Tanda Tangan Webhook

Ketika pekerjaan asinkron selesai, Nexus akan mengirimkan POST request ke URL yang didaftarkan di header `X-Webhook-Callback-URI`.

Untuk memvalidasi keaslian payload, sistem klien wajib menghitung HMAC-SHA256:
```python
import hmac
import hashlib

# Ambil dari header request webhook
signature_client = request.headers["X-Nexus-Signature"]
timestamp = request.headers["X-Nexus-Timestamp"]
payload_bytes = await request.body()

# Hitung verifikasi lokal
message = payload_bytes + b"." + timestamp.encode()
expected_signature = hmac.new(secret_api_key, message, hashlib.sha256).hexdigest()

assert hmac.compare_digest(signature_client, expected_signature)
```

---

## 🛡️ Langkah Penanganan Masalah (Troubleshooting)

### Koneksi Database Gagal
*   **Gejala**: `Connection refused` atau `Can't connect to MySQL server`.
*   **Solusi**: Pastikan kontainer MySQL menyala sempurna (`docker ps`). Jika berjalan lokal tanpa Docker, pastikan kredensial di `.env` sudah sesuai dengan MySQL lokal Anda.

### Pekerjaan Asinkron Tersangkut 'queued'
*   **Gejala**: Pekerjaan di `GET /v1/ai/jobs/{job_id}` berstatus `queued` terus menerus.
*   **Solusi**: Pastikan proses arq worker sudah berjalan lancar di terminal terpisah (`arq worker.WorkerSettings`) atau kontainer `nexus-worker` aktif.
