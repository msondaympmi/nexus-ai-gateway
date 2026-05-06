# Software Requirements Specification
# MPM AI Services Platform (Nexus)

**Version:** 0.4  
**Status:** Final (Ready for Development)  
**Date:** Mei 2026  
**Author:** BD & Technology Division — PT Asuransi Mitra Pelindung Mustika  
**Audience:** Internal — Engineering & BD Division

---

## Daftar Isi

1. [Overview](#1-overview)
2. [Tujuan & Latar Belakang](#2-tujuan--latar-belakang)
3. [Scope](#3-scope)
4. [Asumsi & Constraint](#4-asumsi--constraint)
5. [Proyeksi Traffic & Scale Plan](#5-proyeksi-traffic--scale-plan)
6. [Arsitektur Sistem](#6-arsitektur-sistem)
7. [Auth & Authorization](#7-auth--authorization)
8. [API Specification](#8-api-specification)
9. [Async Job System](#9-async-job-system)
10. [Webhook System](#10-webhook-system)
11. [Database Schema](#11-database-schema)
12. [Docker Compose & Deployment](#12-docker-compose--deployment)
13. [Nginx Integration](#13-nginx-integration)
14. [Struktur Project](#14-struktur-project)
15. [Non-Functional Requirements](#15-non-functional-requirements)
16. [Tech Stack](#16-tech-stack)
17. [Error Handling & Standar Response](#17-error-handling--standar-response)
18. [Logging & Observability](#18-logging--observability)
19. [Security Considerations](#19-security-considerations)
20. [Roadmap](#20-roadmap)
21. [Open Questions](#21-open-questions)

---

## 1. Overview

**MPM AI Services Platform (Nexus)** adalah internal AI services gateway yang berfungsi sebagai centralized layer antara aplikasi-aplikasi internal MPM Insurance dan model AI generatif (via LiteLLM Proxy / Vertex AI Gemini).

Nexus mengekspos fungsi-fungsi AI sebagai modular REST API endpoint sehingga setiap aplikasi client tidak perlu mengelola koneksi ke LLM secara mandiri. Semua hal terkait autentikasi mesin, permission, rate limiting, job queuing, logging, dan routing ke model AI ditangani oleh Nexus secara terpusat.

Platform ini dirancang untuk berjalan stabil selama minimal **3 tahun** dengan arsitektur yang memungkinkan scale-out horizontal tanpa refactor besar.

---

## 2. Tujuan & Latar Belakang

### 2.1 Latar Belakang

MPM Insurance memiliki beberapa aplikasi internal (CARE, eLogbook, eQuotation, Cover Note, dan lainnya) yang berpotensi memanfaatkan kemampuan AI untuk meningkatkan efisiensi operasional. Sebelum Nexus, setiap aplikasi harus:

- Mengelola koneksi ke Vertex AI atau LiteLLM secara mandiri
- Menduplikasi logic auth, rate limiting, dan logging
- Tidak ada visibilitas terpusat atas penggunaan dan biaya AI per aplikasi

### 2.2 Tujuan

- Menyediakan **single entry point** untuk semua kebutuhan AI di ekosistem aplikasi MPM
- Mengimplementasikan **machine-to-machine (M2M) auth** dengan API key per aplikasi
- Mendukung **3 fungsi AI modular**: Chatbot/RAG, OCR, Summarization
- Mendukung **dual response mode**: synchronous dan asynchronous via job queue
- Memberikan **audit trail lengkap** per aplikasi dan per user yang memicu request
- Memastikan arsitektur siap untuk **scale-out** seiring pertumbuhan penggunaan

### 2.3 Prinsip Desain

| Prinsip | Deskripsi |
|---|---|
| Modular | Tiap fungsi AI adalah independent service endpoint |
| M2M-first | Auth berbasis API key per aplikasi, bukan per user manusia |
| Layered identity | App identity + forwarded user context untuk audit |
| Dual-mode | Semua endpoint support sync dan async |
| Observable | Semua request tercatat untuk audit, cost tracking, debugging |
| Container-first | Docker dari day one, siap scale out tanpa refactor |
| Backend-agnostic | Bisa swap model atau provider tanpa ubah interface client |

---

## 3. Scope

### 3.1 In Scope (v1)

- API gateway layer (Python / FastAPI)
- M2M authentication via API key per aplikasi
- Layered user context via forwarded headers
- 3 modul AI: Chatbot/RAG, OCR, Summarization
- Async job queue (Redis + background worker)
- Polling endpoint untuk status job
- Webhook callback dengan HMAC signature verification
- **[Baru] Per-request Webhook Override via Header**
- Admin endpoints untuk manage apps, permissions, dan monitoring
- **[Baru] Admin UI Web Dashboard (Streamlit)**
- **[Baru] Streaming Response (SSE) untuk Endpoint Chat**
- **[Baru] RAG (Retrieval-Augmented Generation) menggunakan GCP Firestore Vector Search**
- Usage logging per app, per user, per endpoint
- Rate limiting per app per endpoint
- Containerized deployment (Docker Compose) di GCP VM existing
- Integrasi dengan Nginx reverse proxy existing
- Integrasi dengan LiteLLM proxy existing
- Integrasi dengan MySQL instance existing

### 3.2 Out of Scope (v1)

| Item | Keterangan |
|---|---|
| Frontend chat UI | Hanya API, tidak ada UI untuk end user |
| RAG dengan vector DB | Masuk roadmap v2 (ChromaDB / Vertex Matching Engine) |
| Fine-tuning / training model | Tidak dalam scope platform ini |
| Multi-tenant / external access | Hanya untuk aplikasi internal MPM |
| SSO / user login flow | Tidak ada — ini M2M platform |
| File storage permanen untuk OCR | Nexus tidak menyimpan file. File original berada di GCP Bucket milik klien |

---

## 4. Asumsi & Constraint

### 4.1 Asumsi

- LiteLLM proxy sudah berjalan di `integration-vm` port 4000 dan dapat diakses dari container Docker via `host.docker.internal` atau network bridge
- MySQL instance sudah tersedia di VM yang sama dan dapat diakses oleh container
- Nginx reverse proxy sudah berjalan dan hanya perlu tambahan server block baru
- Semua aplikasi client berada dalam jaringan internal GCP VPC atau dapat menjangkau endpoint Nexus via Nginx
- Model Gemini (1.5 Pro dan 1.5 Flash) sudah dikonfigurasi di LiteLLM dan aktif di Vertex AI project `big-bliss-302909`

### 4.2 Constraint

- Deployment harus di `integration-vm` GCP (Jakarta region `asia-southeast2`)
- Tidak ada Tailscale — koneksi antar service via Docker internal network dan GCP VPC
- Tidak ada budget tambahan untuk VM baru di v1 — semua service dalam satu VM
- Tech stack: Python 3.11 / FastAPI (bukan .NET Core) karena ekosistem AI library
- Database: MySQL (bukan PostgreSQL) untuk konsistensi dengan aplikasi existing

---

## 5. Proyeksi Traffic & Scale Plan

### 5.1 Estimasi Traffic

| Periode | Est. req/bulan | Peak req/jam | Peak req/menit |
|---|---|---|---|
| v1 — 2026 | 5.000 | ~20 | ~0.33 |
| v2 — 2027 | 15.000 | ~60 | ~1.0 |
| v3 — 2028 | 45.000 | ~150 | ~2.5 |

Asumsi growth 3x per tahun (konservatif, sejalan dengan onboarding aplikasi baru).

### 5.2 Analisis Bottleneck

Bottleneck utama bukan compute tapi **LLM latency**:

- Chat / Summarize: 3–15 detik per request
- OCR (single page): 5–15 detik
- OCR (multi-page PDF): 15–60 detik

Dengan peak 150 req/jam = 2.5 req/menit, jika rata-rata latency 10 detik maka concurrent requests maksimum ~0.4 — sangat rendah. Arsitektur async + worker pool adalah mitigasi utama agar gateway tidak blocking saat ada request dengan latency tinggi.

### 5.3 Resource Estimate di integration-vm (v1)

| Komponen | RAM | CPU |
|---|---|---|
| nexus-gateway (2 uvicorn workers) | ~256 MB | ~0.3 core idle |
| nexus-worker × 2 | ~512 MB total | ~0.5 core idle |
| nexus-redis | ~64 MB | minimal |
| LiteLLM (existing) | sudah berjalan | — |
| MySQL (existing) | sudah berjalan | — |
| **Total tambahan** | **~832 MB** | **~0.8 core** |

### 5.4 Scale-out Strategy

```
v1 (2026): 1 gateway container, 2 worker containers — single VM
v2 (2027): scale worker to 4 replicas (docker compose scale)
v3 (2028): pindahkan worker ke dedicated VM, Redis accessible via GCP VPC internal IP
```

Prosedur scale worker tanpa downtime:
```bash
docker compose up -d --scale nexus-worker=4
```

---

## 6. Arsitektur Sistem

### 6.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     GCP VM: integration-vm                       │
│                   (asia-southeast2, big-bliss-302909)            │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Nginx (existing)  :80 / :443                            │   │
│  │  SSL termination, reverse proxy, client_max_body 15M     │   │
│  └───────────────────────┬──────────────────────────────────┘   │
│                          │ proxy_pass http://127.0.0.1:8100      │
│  ┌───────────────────────▼──────────────────────────────────┐   │
│  │  Docker Compose Stack                                     │   │
│  │                                                           │   │
│  │  ┌─────────────────────────────────────────────────┐     │   │
│  │  │  nexus-gateway  (FastAPI, port 8100 internal)    │     │   │
│  │  │  - Auth middleware (API key validation)         │     │   │
│  │  │  - Permission check                             │     │   │
│  │  │  - Rate limiter                                 │     │   │
│  │  │  - Request router (sync / async dispatch)       │     │   │
│  │  │  - Usage logger                                 │     │   │
│  │  └────────────────────┬────────────────────────────┘     │   │
│  │                       │                                   │   │
│  │           ┌───────────┴──────────┐                       │   │
│  │           │ sync                 │ async                  │   │
│  │           ▼                      ▼                        │   │
│  │  ┌─────────────────┐   ┌──────────────────────┐         │   │
│  │  │ Module handlers │   │  nexus-redis  :6379   │         │   │
│  │  │ (inline, sync)  │   │  (job queue)         │         │   │
│  │  └────────┬────────┘   └──────────┬───────────┘         │   │
│  │           │                       │ worker polls          │   │
│  │           │            ┌──────────▼───────────┐         │   │
│  │           │            │  nexus-worker × 2     │         │   │
│  │           │            │  (background process) │         │   │
│  │           │            └──────────┬────────────┘         │   │
│  │           │                       │                       │   │
│  │           └───────────┬───────────┘                       │   │
│  │                       ▼                                   │   │
│  │  ┌─────────────────────────────────────────────────┐     │   │
│  │  │  LiteLLM Proxy  :4000  (existing)               │     │   │
│  │  │  Vertex AI — Gemini 1.5 Pro / Flash             │     │   │
│  │  └─────────────────────────────────────────────────┘     │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  MySQL (existing)  — database: nexus_db                          │
│  nexus_apps · nexus_app_permissions · nexus_jobs · nexus_usage_log  │
└─────────────────────────────────────────────────────────────────┘
         ▲
         │ HTTPS via Nginx
         │
Client Apps (CARE, eLogbook, eQuotation, Cover Note, dll)
di GCP VPC internal / app server lain
```

### 6.2 Sync Request Flow

```
Client
  │  POST /v1/ai/chat
  │  Authorization: Bearer <api_key>
  │  X-Response-Mode: sync  (atau omit)
  │  X-User-Id: usr-123
  ▼
Nginx
  │  proxy_pass :8100
  ▼
nexus-gateway
  │  1. Validate API key → lookup nexus_apps (cached 5 menit)
  │  2. Check permission → nexus_app_permissions
  │  3. Check rate limit → Redis counter
  │  4. Dispatch ke module handler (sync)
  │  5. Module handler → call LiteLLM :4000
  │  6. Write usage log → nexus_usage_log (async, non-blocking)
  │  7. Return response
  ▼
Client  ←  response JSON (latency = LLM latency)
```

### 6.3 Async Request Flow

```
Client
  │  POST /v1/ai/ocr
  │  Authorization: Bearer <api_key>
  │  X-Response-Mode: async
  │  X-User-Id: usr-123
  ▼
nexus-gateway
  │  1. Validate API key, permission, rate limit
  │  2. Generate job_id (UUID)
  │  3. Write job ke nexus_jobs (status: queued)
  │  4. Push job payload ke Redis queue
  │  5. Return {job_id, poll_url} immediately (< 500ms)
  ▼
Client  ←  {"job_id": "uuid", "status": "queued", "poll_url": "/v1/ai/jobs/uuid"}

--- background ---

nexus-worker
  │  1. Poll Redis queue (blocking pop, timeout 1s)
  │  2. Update nexus_jobs status → processing
  │  3. Invoke module handler → LiteLLM
  │  4. Write result → nexus_jobs (status: done / failed)
  │  5. Write usage log → nexus_usage_log
  │  6. Trigger webhook dispatcher (bila callback_url terdaftar)

Client (polling)
  │  GET /v1/ai/jobs/{job_id}  → cek status
  ▼
  {"status": "done", "result": {...}}

Client (webhook)
  ←  POST {callback_url}  dari webhook dispatcher
     {"event": "job.completed", "job_id": "...", "result": {...}}
```

---

## 7. Auth & Authorization

### 7.1 Authentication Model: M2M API Key

Nexus menggunakan **machine-to-machine (M2M) authentication**. Tidak ada user login flow. Setiap aplikasi client mendapat satu API key permanen yang digenerate saat registrasi oleh admin.

Format API key: `nexus-live-{32 random hex chars}`  
Contoh: `nexus-live-a3f8c2d19e4b7a6f0c1d2e3f4a5b6c7d`

API key disimpan sebagai **bcrypt hash** di `nexus_apps.api_key_hash`. Plaintext key hanya ditampilkan satu kali saat generate — tidak bisa diambil ulang. Jika bocor, harus di-rotate via endpoint admin.

### 7.2 Request Authentication

Setiap request wajib menyertakan API key di header:

```
Authorization: Bearer nexus-live-a3f8c2d19e4b7a6f0c1d2e3f4a5b6c7d
```

Proses validasi di middleware:

1. Extract bearer token dari header `Authorization`
2. Lookup `nexus_apps` berdasarkan prefix key (4 karakter pertama setelah `nexus-live-`) untuk efisiensi — tidak perlu compare hash semua rows
3. Compare bcrypt hash
4. Cache hasil validasi di Redis dengan key `auth_cache:{token_hash}` TTL 300 detik
5. Jika app `is_active = false` → 401 Unauthorized

Response jika auth gagal:
```json
HTTP 401
{
  "error": "unauthorized",
  "message": "API key tidak valid atau tidak aktif",
  "request_id": "uuid"
}
```

### 7.3 Layered User Context

Aplikasi client **dianjurkan** (tidak diwajibkan) menyertakan context user yang memicu request di sisi aplikasi mereka:

```
X-User-Id: usr-4821
X-User-Name: budi.santoso
```

Nexus tidak memvalidasi nilai ini — tanggung jawab kebenaran ada di app client. Nilai ini hanya dicatat di `nexus_usage_log` dan disertakan di webhook payload untuk keperluan audit. Jika tidak dikirim, dicatat sebagai `null` (ditampilkan sebagai `system` di laporan).

### 7.4 App Permission Model

Setiap app memiliki whitelist endpoint yang diizinkan, disimpan di tabel `nexus_app_permissions`. Request ke endpoint yang tidak ada di whitelist → `403 Forbidden`.

Permission ditentukan saat registrasi app dan bisa diupdate via admin endpoint.

**Contoh konfigurasi permission per app:**

| App | Endpoints yang diizinkan |
|---|---|
| CARE | `/v1/ai/ocr`, `/v1/ai/summarize` |
| eLogbook | `/v1/ai/chat`, `/v1/ai/summarize` |
| eQuotation | `/v1/ai/chat` |
| Cover Note | `/v1/ai/ocr` |
| Internal Admin Tool | semua endpoint + `/v1/admin/*` |

Response jika permission ditolak:
```json
HTTP 403
{
  "error": "permission_denied",
  "message": "Aplikasi ini tidak memiliki akses ke endpoint /v1/ai/analyze",
  "request_id": "uuid"
}
```

### 7.5 Rate Limiting

Rate limit dikonfigurasi per app per endpoint di tabel `nexus_rate_limits`. Counter disimpan di Redis dengan sliding window 1 jam.

Default jika tidak ada konfigurasi spesifik:

| Parameter | Default |
|---|---|
| `requests_per_hour` | 200 req/jam |
| `max_tokens_per_day` | 2.000.000 token/hari |

Response jika rate limit tercapai:
```json
HTTP 429
{
  "error": "rate_limit_exceeded",
  "message": "Limit 200 request/jam tercapai. Reset dalam 1847 detik.",
  "retry_after_seconds": 1847,
  "request_id": "uuid"
}
```

---

## 8. API Specification

### 8.1 Base URL & Versi

```
Base URL  : https://{nexus_hostname}/
API versi : v1 (explicit dalam URL path)
```

### 8.2 Headers Standar

**Headers wajib di semua request:**

```
Authorization: Bearer <api_key>
Content-Type: application/json
```

**Headers opsional:**

```
X-Response-Mode: sync | async    (default: sync)
X-User-Id: string                (user ID di sistem app client)
X-User-Name: string              (nama user, untuk readability di log)
```

### 8.3 Format Response

Semua response menggunakan JSON. Field `request_id` selalu ada untuk tracing.

**Response sukses (sync):**
```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "mode": "sync",
  "endpoint": "/v1/ai/chat",
  ... (field spesifik per endpoint)
}
```

**Response sukses (async — job diterima):**
```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "mode": "async",
  "job_id": "660e8400-e29b-41d4-a716-446655440001",
  "status": "queued",
  "poll_url": "/v1/ai/jobs/660e8400-e29b-41d4-a716-446655440001",
  "estimated_seconds": 10
}
```

---

### 8.4 POST /v1/ai/chat — Modul Chatbot / RAG

Conversational AI dengan optional context injection untuk RAG sederhana, serta dukungan untuk Multi-Tenant RAG Firestore dan Agentic Tool Calling.

**Request:**
```json
{
  "messages": [
    { "role": "system", "content": "Kamu adalah asisten asuransi MPM." },
    { "role": "user", "content": "Apa syarat klaim asuransi kendaraan?" }
  ],
  "document_context": "string | null",
  "system_prompt": "string | null",
  "model": "gemini-1.5-pro | gemini-1.5-flash | null",
  "stream": false,
  "temperature": 0.7,
  "max_tokens": 2048,
  "use_rag": false,
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "get_policy_details",
        "description": "Ambil rincian polis berdasarkan nomor polis",
        "parameters": {
          "type": "object",
          "properties": {
            "policy_number": { "type": "string" }
          },
          "required": ["policy_number"]
        }
      }
    }
  ],
  "tool_choice": "auto"
}
```

| Field | Type | Required | Deskripsi |
|---|---|---|---|
| `messages` | array | ✓ | Array message dengan role `system`, `user`, atau `assistant` |
| `document_context` | string | — | Teks dokumen yang di-inject sebagai context tambahan (RAG sederhana) |
| `system_prompt` | string | — | Override system prompt. Jika ada, ditambahkan sebelum `document_context` |
| `model` | string | — | Default: `gemini-1.5-pro`. Gunakan `flash` untuk respons cepat dengan biaya lebih rendah |
| `stream` | boolean | — | Default: `false`. Bila `true`, response menggunakan SSE (Server-Sent Events) |
| `temperature` | float | — | Default: `0.7`. Range: 0.0–1.0 |
| `max_tokens` | int | — | Default: `2048`. Maksimum token output |
| `use_rag` | boolean | — | Default: `false`. Jika `true`, gunakan Multi-Tenant RAG Firestore (Filtered by `app_id`) |
| `tools` | array | — | Whitelist JSON schema untuk standard function calling yang dapat di-invoke model |
| `tool_choice` | string | — | Pilihan pemanggilan tool (`auto`, `none`, atau objek spesifik). Default: `auto` |

**Response (sync):**
```json
{
  "request_id": "uuid",
  "mode": "sync",
  "endpoint": "/v1/ai/chat",
  "reply": "Untuk mengajukan klaim asuransi kendaraan, Anda perlu...",
  "tool_calls": [
    {
      "id": "call_123",
      "type": "function",
      "function": {
        "name": "get_policy_details",
        "arguments": "{\"policy_number\": \"POL-9912\"}"
      }
    }
  ],
  "model_used": "gemini-1.5-pro",
  "finish_reason": "stop | tool_calls",
  "usage": {
    "prompt_tokens": 320,
    "completion_tokens": 185,
    "total_tokens": 505
  },
  "latency_ms": 3240
}
```

**Streaming response (bila stream: true):**
```
Content-Type: text/event-stream

data: {"chunk": "Untuk ", "index": 0}
data: {"chunk": "mengajukan ", "index": 1}
data: {"chunk": "klaim...", "index": 2}
data: [DONE]
```

**Catatan:**
- `document_context` di-inject sebagai system message tambahan — ini RAG sederhana tanpa vector DB.
- Jika `use_rag=true`, system akan melakukan kNN search otomatis pada Firestore Knowledge Base dengan filter ketat `app_id == caller_app.id` (Application Isolation).
- Bila `stream: true`, mode harus `sync`. Streaming tidak support async mode.
- `messages` maksimum 50 item. Lebih dari itu → 400 Bad Request.

---

### 8.5 POST /v1/ai/ocr — Modul OCR

Extract teks dari gambar atau PDF menggunakan vision capability Gemini.

**Request:** `Content-Type: application/json`

| Field | Type | Required | Deskripsi |
|---|---|---|---|
| `file_uri` | string | ✓ | URI file di GCP Bucket (contoh: `gs://bucket-client/file.pdf`) |
| `output_format` | string | ✓ | `text`, `json`, atau `markdown` |
| `extraction_schema` | JSON string | — | Hanya bila `output_format = json`. JSON object dengan key yang ingin diekstrak |
| `language_hint` | string | — | Hint bahasa dokumen. Default: `id`. Nilai: `id`, `en`, `auto` |
| `page_range` | string | — | Hanya untuk PDF. Format: `1-3`, `1,3,5`, atau `all`. Default: `all` |

**Contoh `extraction_schema` untuk KTP:**
```json
{
  "nik": "",
  "nama": "",
  "tempat_lahir": "",
  "tanggal_lahir": "",
  "jenis_kelamin": "",
  "alamat": "",
  "rt_rw": "",
  "kelurahan": "",
  "kecamatan": "",
  "agama": "",
  "status_perkawinan": "",
  "pekerjaan": "",
  "kewarganegaraan": ""
}
```

**Response (sync, single page):**
```json
{
  "request_id": "uuid",
  "mode": "sync",
  "endpoint": "/v1/ai/ocr",
  "filename": "ktp_budi.jpg",
  "output_format": "json",
  "page_count": 1,
  "result": {
    "nik": "3201234567890001",
    "nama": "BUDI SANTOSO",
    "tempat_lahir": "BANDUNG",
    "tanggal_lahir": "15-03-1985",
    "jenis_kelamin": "LAKI-LAKI",
    "alamat": "JL. MAWAR NO. 12",
    "rt_rw": "003/005",
    "kelurahan": "SUKASARI",
    "kecamatan": "BOGOR TIMUR",
    "agama": "ISLAM",
    "status_perkawinan": "KAWIN",
    "pekerjaan": "KARYAWAN SWASTA",
    "kewarganegaraan": "WNI"
  },
  "confidence_note": "high",
  "usage": {
    "prompt_tokens": 512,
    "completion_tokens": 148,
    "total_tokens": 660
  },
  "latency_ms": 4200
}
```

**Response (sync, multi-page PDF, output_format: text):**
```json
{
  "request_id": "uuid",
  "mode": "sync",
  "filename": "polis_kendaraan.pdf",
  "output_format": "text",
  "page_count": 4,
  "pages": [
    { "page": 1, "text": "POLIS ASURANSI KENDARAAN BERMOTOR..." },
    { "page": 2, "text": "PASAL 1 - DEFINISI..." },
    { "page": 3, "text": "PASAL 2 - JAMINAN..." },
    { "page": 4, "text": "PASAL 3 - PENGECUALIAN..." }
  ],
  "usage": { "prompt_tokens": 2048, "completion_tokens": 890, "total_tokens": 2938 },
  "latency_ms": 18400
}
```

**Catatan:**
- Nexus tidak menerima unggahan file secara langsung (*binary upload*). Klien wajib mengunggah file ke GCP Bucket mereka sendiri dan mengirimkan URI-nya ke endpoint ini.
- Async **sangat direkomendasikan** untuk PDF > 2 halaman.
- `confidence_note` bersifat kualitatif (`high`, `medium`, `low`) — estimasi dari model, bukan skor numerik terverifikasi.

---

### 8.6 POST /v1/ai/summarize — Modul Summarization

Meringkas teks panjang menjadi bentuk yang lebih singkat.

**Request:**
```json
{
  "text": "string — teks panjang yang akan diringkas",
  "language": "id | en",
  "style": "bullet | paragraph | executive",
  "max_length": 500,
  "focus": "string | null"
}
```

| Field | Type | Required | Deskripsi |
|---|---|---|---|
| `text` | string | ✓ | Teks yang akan diringkas. Maks 100.000 karakter |
| `language` | string | — | Bahasa output. Default: `id` |
| `style` | string | — | Format output: `bullet` (poin-poin), `paragraph` (paragraf), `executive` (ringkasan eksekutif 1 paragraf). Default: `paragraph` |
| `max_length` | int | — | Target panjang ringkasan dalam kata. Default: 300. Maks: 1000 |
| `focus` | string | — | Instruksi fokus khusus. Contoh: `"fokus pada aspek klaim dan pengecualian saja"` |

**Response:**
```json
{
  "request_id": "uuid",
  "mode": "sync",
  "endpoint": "/v1/ai/summarize",
  "language": "id",
  "style": "bullet",
  "summary": "• Polis berlaku untuk kendaraan roda empat kategori non-komersial\n• Jaminan mencakup...\n• Pengecualian meliputi...",
  "original_length_chars": 18420,
  "summary_length_chars": 612,
  "compression_ratio": 0.033,
  "usage": {
    "prompt_tokens": 4200,
    "completion_tokens": 210,
    "total_tokens": 4410
  },
  "latency_ms": 5100
}
```

**Style `executive` — contoh output:**
```
Polis ini memberikan jaminan komprehensif untuk kendaraan roda empat non-komersial 
dengan pertanggungan all-risk termasuk kerusakan akibat kecelakaan, pencurian, dan 
bencana alam, dengan pengecualian kerusakan akibat kelalaian pengemudi dan modifikasi 
tanpa persetujuan penanggung.
```

---

### 8.7 GET /health/liveness & /health/readiness

Tidak memerlukan autentikasi.
- **GET /health/liveness**: Mengembalikan HTTP 200 OK jika proses FastAPI berjalan (digunakan oleh Docker/Nginx).
- **GET /health/readiness**: Mengecek dependensi (DB, Redis, LiteLLM) untuk monitoring.

**Response /health/readiness:**
```json
{
  "status": "ok",
  "timestamp": "2026-05-05T10:30:00Z",
  "version": "1.0.0",
  "components": {
    "database": "ok",
    "redis": "ok",
    "litellm": "ok"
  }
}
```

Bila salah satu komponen tidak sehat:
```json
{
  "status": "degraded",
  "components": {
    "database": "ok",
    "redis": "error: connection refused",
    "litellm": "ok"
  }
}
```

---


---

### 8.9 POST /v1/ai/knowledge — RAG Ingestion (Knowledge Base)

Memasukkan dokumen ke dalam Vector Database (Firestore) agar bisa digunakan oleh modul Chat (RAG) secara aman dan terisolasi antar aplikasi klien.

**Request:** `Content-Type: application/json`

| Field | Type | Required | Deskripsi |
|---|---|---|---|
| `document_id` | string | ✓ | ID unik dokumen (misal dari database aplikasi klien) |
| `content` | string | ✓ | Teks isi dokumen yang akan di-*embed* (maks 10.000 karakter) |
| `metadata` | JSON | — | Data tambahan (contoh: `{"category": "policy", "author": "admin"}`) |

**Flow:**
1. Nexus memecah `content` menjadi *chunks* kecil (chunking).
2. Memanggil Vertex AI Text Embeddings API untuk mengubah teks menjadi *vector embeddings*.
3. Menyimpan *chunks* beserta *vector*-nya ke koleksi Firestore (`nexus_knowledge_base`) dengan menyertakan metadata wajib **`app_id`** dan **`app_name`** untuk menjamin **Application Isolation**.
4. Saat `POST /v1/ai/chat` dipanggil dengan `use_rag=true`, Nexus akan melakukan *kNN Search* di Firestore untuk mencari *chunk* paling relevan dengan memfilter hasil pencarian ketat berdasarkan: `app_id == caller_app.id`. Aplikasi tidak akan pernah bisa mengakses atau membaca data milik aplikasi lain.

## 9. Async Job System

### 9.1 Job Lifecycle

```
queued → processing → done
                    → failed
queued → cancelled  (bila cancel sebelum diproses)
```

| Status | Deskripsi |
|---|---|
| `queued` | Job diterima dan ada di Redis queue, belum diambil worker |
| `processing` | Worker sedang memproses job, LLM call sedang berjalan |
| `done` | Job selesai, result tersedia |
| `failed` | Job gagal setelah semua retry habis |
| `cancelled` | Job di-cancel oleh client sebelum worker mengambilnya |

### 9.2 Endpoint Job Management

**GET /v1/ai/jobs/{job_id}**

Cek status dan ambil result job.

```json
// Status: queued
{
  "job_id": "uuid",
  "status": "queued",
  "endpoint": "/v1/ai/ocr",
  "queued_at": "2026-05-05T10:30:00Z",
  "position_in_queue": 3,
  "estimated_wait_seconds": 45
}

// Status: processing
{
  "job_id": "uuid",
  "status": "processing",
  "endpoint": "/v1/ai/ocr",
  "queued_at": "2026-05-05T10:30:00Z",
  "started_at": "2026-05-05T10:30:15Z"
}

// Status: done
{
  "job_id": "uuid",
  "status": "done",
  "endpoint": "/v1/ai/ocr",
  "queued_at": "2026-05-05T10:30:00Z",
  "started_at": "2026-05-05T10:30:15Z",
  "completed_at": "2026-05-05T10:30:42Z",
  "latency_ms": 27000,
  "result": {
    ... (sama dengan response sync endpoint tersebut)
  }
}

// Status: failed
{
  "job_id": "uuid",
  "status": "failed",
  "endpoint": "/v1/ai/ocr",
  "queued_at": "2026-05-05T10:30:00Z",
  "started_at": "2026-05-05T10:30:15Z",
  "failed_at": "2026-05-05T10:31:15Z",
  "error": "LLM timeout: no response after 60 seconds"
}
```

**POST /v1/ai/jobs/{job_id}/cancel**

Cancel job. Hanya bisa dilakukan bila status masih `queued`. Setelah `processing` tidak bisa di-cancel.

```json
// Request: body kosong

// Response 200 - berhasil cancel
{ "job_id": "uuid", "status": "cancelled", "message": "Job berhasil di-cancel" }

// Response 409 - sudah processing
{
  "error": "cannot_cancel",
  "message": "Job sedang diproses dan tidak dapat di-cancel",
  "current_status": "processing"
}
```

**GET /v1/ai/jobs**

List jobs milik app yang memanggil (filtered otomatis berdasarkan API key).

Query parameters:
- `status`: `queued | processing | done | failed | cancelled` (optional)
- `endpoint`: `/v1/ai/ocr` (optional, untuk filter per modul)
- `after`: ISO datetime, filter job setelah tanggal ini
- `before`: ISO datetime
- `limit`: default 20, maks 100
- `offset`: untuk pagination

```json
{
  "total": 142,
  "limit": 20,
  "offset": 0,
  "jobs": [
    {
      "job_id": "uuid",
      "status": "done",
      "endpoint": "/v1/ai/ocr",
      "caller_user_id": "usr-123",
      "queued_at": "2026-05-05T10:30:00Z",
      "completed_at": "2026-05-05T10:30:42Z",
      "latency_ms": 27000
    },
    ...
  ]
}
```

### 9.3 Worker Configuration

Worker menggunakan library **`arq`** (Async Redis Queue) yang berjalan sebagai process terpisah.

Konfigurasi worker:
- `max_jobs`: 4 concurrent jobs per worker instance
- `job_timeout`: 300 detik (5 menit) per job — OCR multi-page PDF bisa memakan waktu, sehingga timeout harus lebih longgar.
- `retry_jobs`: false — tidak ada retry otomatis di worker level untuk job AI utama.
- Worker startup: auto re-queue jobs yang stuck di status `processing` lebih dari 5 menit (indikasi worker crash sebelumnya)

### 9.4 Redis Queue Structure

```
Key: arq:queue                 → Redis List/Set (dimanage oleh library arq)
Key: arq:job:*                 → Metadata job (dimanage oleh library arq)
Key: nexus:rate:{app_id}:{endpoint}:{hour}  → Redis Counter (sliding window rate limit)
Key: nexus:auth_cache:{key_prefix}  → Redis String (cached API key validation, TTL 300s)
```

---

## 10. Webhook System

### 10.1 Konfigurasi

Setiap app mendaftarkan satu `callback_url` saat registrasi. URL ini disimpan di `nexus_apps.callback_url`. 

**Per-Request Override:** Klien dapat mengganti tujuan webhook untuk satu *request* tertentu dengan menambahkan HTTP Header `X-Callback-Url` saat melakukan POST ke endpoint async. Jika header ini ada, Nexus akan menggunakannya sebagai prioritas utama.

Jika `callback_url` kosong/null, webhook tidak dikirim — app hanya bisa menggunakan polling.

### 10.2 Webhook Payload

Nexus mengirim HTTP POST ke `callback_url` setelah job selesai (status `done` atau `failed`):

```json
POST {callback_url}
Content-Type: application/json
X-Nexus-Event: job.completed
X-Nexus-Signature: sha256=a3f8c2d19e4b7a6f0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3
X-Nexus-Job-Id: 660e8400-e29b-41d4-a716-446655440001
X-Nexus-Timestamp: 1746441000

{
  "event": "job.completed",
  "job_id": "660e8400-e29b-41d4-a716-446655440001",
  "app_name": "care",
  "endpoint": "/v1/ai/ocr",
  "status": "done",
  "caller_user_id": "usr-4821",
  "caller_user_name": "budi.santoso",
  "queued_at": "2026-05-05T10:30:00Z",
  "completed_at": "2026-05-05T10:30:42Z",
  "latency_ms": 27000,
  "result": {
    ... (sama dengan response sync endpoint)
  }
}
```

Untuk job yang gagal (`event: job.failed`):
```json
{
  "event": "job.failed",
  "job_id": "uuid",
  "status": "failed",
  "error": "LLM timeout: no response after 60 seconds",
  "failed_at": "2026-05-05T10:31:15Z"
}
```

### 10.3 Signature Verification

`X-Nexus-Signature` dihasilkan dengan HMAC-SHA256 menggunakan `webhook_secret` yang diberikan saat registrasi app:

```python
# Python — cara Nexus generate signature
import hmac, hashlib, time

timestamp = str(int(time.time()))
payload_str = json.dumps(payload, separators=(',', ':'))
message = f"{timestamp}.{payload_str}"
signature = hmac.new(
    webhook_secret.encode(),
    message.encode(),
    hashlib.sha256
).hexdigest()
header = f"sha256={signature}"
```

```python
# Python — cara app client memverifikasi
import hmac, hashlib

received_sig = request.headers['X-Nexus-Signature']
timestamp = request.headers['X-Nexus-Timestamp']
payload_str = request.body.decode()
message = f"{timestamp}.{payload_str}"

expected = hmac.new(webhook_secret.encode(), message.encode(), hashlib.sha256).hexdigest()
expected_header = f"sha256={expected}"

if not hmac.compare_digest(received_sig, expected_header):
    return HTTP 401  # Webhook tidak valid

# Opsional: tolak webhook yang lebih dari 5 menit
if abs(time.time() - int(timestamp)) > 300:
    return HTTP 400  # Timestamp terlalu lama
```

**App client wajib:**
1. Return HTTP `2xx` jika webhook diterima dan diproses
2. Return HTTP `4xx` atau `5xx` jika gagal (akan di-retry oleh Nexus)

### 10.4 Retry Policy

| Attempt | Delay |
|---|---|
| 1 (original) | Langsung setelah job selesai |
| 2 | 10 detik setelah attempt 1 gagal |
| 3 | 30 detik setelah attempt 2 gagal |
| 4 | 90 detik setelah attempt 3 gagal |

**Mekanisme Implementasi:**
Retry tidak memblokir *worker pool* AI. Saat webhook perlu di-retry, sistem akan meng-*enqueue* *background task* khusus (`send_webhook`) ke dalam queue `arq` dengan parameter penundaan `_defer_by` sesuai tabel di atas.

Setelah attempt 4 gagal, `webhook_failed = true` dicatat di `nexus_jobs`. App harus fallback ke polling untuk mengambil result.


### 10.3 Webhook Failsafe & Retry Mechanism

Jika pengiriman webhook ke `callback_url` klien mengalami kegagalan (contoh: HTTP 500, Timeout, atau klien sedang down), Nexus akan melakukan **Auto-Retry** menggunakan pola *exponential backoff* yang dieksekusi oleh *worker* (`arq`).

Aturan Retry:
- Maksimal percobaan ulang (*max retries*) diatur secara global melalui variabel environment `WEBHOOK_MAX_RETRIES` (default: 3 kali).
- Setiap kegagalan dan percobaan ulang akan dicatat di log aplikasi (bisa dimonitor melalui Docker logs atau GCP Logging) untuk menjamin visibilitas penuh bagi tim operasional.
- Jika sudah mencapai batas maksimal dan klien tetap tidak bisa menerima *request*, *job* tersebut tetap berstatus `done` (karena proses AI-nya sendiri sudah sukses), dan klien harus mengambil hasilnya secara manual via *Polling* endpoint `GET /v1/ai/jobs/{job_id}`.

---

## 11. Database Schema

Database: `nexus_db` di MySQL instance existing di `integration-vm`. 
*(Catatan: Karena tabel menggunakan tipe data `JSON`, MySQL harus berjalan di versi minimal 5.7.8, direkomendasikan 8.0+).*

### 11.1 nexus_apps

Tabel master aplikasi yang terdaftar di Nexus.

```sql
CREATE TABLE nexus_apps (
  id               CHAR(36)      NOT NULL,
  app_name         VARCHAR(100)  NOT NULL,
  api_key_hash     VARCHAR(255)  NOT NULL,
  api_key_prefix   VARCHAR(10)   NOT NULL,     -- 4-8 char, untuk lookup efisien
  webhook_secret   VARCHAR(255),
  callback_url     VARCHAR(500),
  description      VARCHAR(255),
  is_admin         BOOLEAN       NOT NULL DEFAULT FALSE,
  is_active        BOOLEAN       NOT NULL DEFAULT TRUE,
  created_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at       DATETIME               ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_app_name (app_name),
  KEY idx_key_prefix (api_key_prefix)
);
```

### 11.2 nexus_app_permissions

Whitelist endpoint per app.

```sql
CREATE TABLE nexus_app_permissions (
  app_id    CHAR(36)     NOT NULL,
  endpoint  VARCHAR(100) NOT NULL,
  PRIMARY KEY (app_id, endpoint),
  CONSTRAINT fk_perm_app FOREIGN KEY (app_id) REFERENCES nexus_apps(id)
);
```

### 11.3 nexus_jobs

Tabel untuk tracking async jobs.

```sql
CREATE TABLE nexus_jobs (
  id                   CHAR(36)      NOT NULL,
  app_id               CHAR(36)      NOT NULL,
  app_name             VARCHAR(100)  NOT NULL,
  caller_user_id       VARCHAR(100),
  caller_user_name     VARCHAR(100),
  endpoint             VARCHAR(100)  NOT NULL,
  request_payload      JSON,
  status               ENUM('queued','processing','done','failed','cancelled')
                       NOT NULL DEFAULT 'queued',
  result_payload       JSON,
  error_message        TEXT,
  cost_usd             DECIMAL(10, 6) NOT NULL DEFAULT 0.000000, -- Financial Audit
  queued_at            DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  started_at           DATETIME,
  completed_at         DATETIME,
  webhook_sent         BOOLEAN       NOT NULL DEFAULT FALSE,
  webhook_attempts     TINYINT       NOT NULL DEFAULT 0,
  webhook_last_attempt DATETIME,
  webhook_failed       BOOLEAN       NOT NULL DEFAULT FALSE,
  PRIMARY KEY (id),
  CONSTRAINT fk_job_app FOREIGN KEY (app_id) REFERENCES nexus_apps(id),
  KEY idx_app_status (app_id, status),
  KEY idx_status_queued (status, queued_at),
  KEY idx_caller (caller_user_id)
);
```

### 11.4 nexus_usage_log

Log semua request masuk (sync maupun async).

```sql
CREATE TABLE nexus_usage_log (
  id                CHAR(36)      NOT NULL,
  app_id            CHAR(36)      NOT NULL,
  app_name          VARCHAR(100)  NOT NULL,
  caller_user_id    VARCHAR(100),
  caller_user_name  VARCHAR(100),
  endpoint          VARCHAR(100)  NOT NULL,
  response_mode     ENUM('sync','async') NOT NULL,
  job_id            CHAR(36),              -- FK ke nexus_jobs bila async
  model_used        VARCHAR(100),
  prompt_tokens     INT,
  completion_tokens INT,
  total_tokens      INT,
  cost_usd          DECIMAL(10, 6) NOT NULL DEFAULT 0.000000, -- Financial Audit
  latency_ms        INT,
  status_code       INT           NOT NULL,
  error_message     TEXT,
  requested_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_app_date (app_id, requested_at),
  KEY idx_endpoint_date (endpoint, requested_at),
  KEY idx_caller_date (caller_user_id, requested_at),
  KEY idx_requested_at (requested_at)
);
```

### 11.5 nexus_rate_limits

Konfigurasi rate limit per app per endpoint.

```sql
CREATE TABLE nexus_rate_limits (
  app_id              CHAR(36)     NOT NULL,
  endpoint            VARCHAR(100) NOT NULL,
  requests_per_hour   INT          NOT NULL DEFAULT 200,
  max_tokens_per_day  INT          NOT NULL DEFAULT 2000000,
  PRIMARY KEY (app_id, endpoint),
  CONSTRAINT fk_rl_app FOREIGN KEY (app_id) REFERENCES nexus_apps(id)
);
```

### 11.6 Indeks & Maintenance

Query yang paling sering digunakan dan indeks yang mendukungnya:

| Query | Indeks |
|---|---|
| Usage report per app + tanggal | `idx_app_date` |
| Usage per caller (audit trail) | `idx_caller_date` |
| Job list per app + status | `idx_app_status` |
| Worker ambil job queued terlama | `idx_status_queued` |
| API key lookup (auth) | `idx_key_prefix` + compare hash |

**Retensi data:**
- `nexus_usage_log`: retention 1 tahun, hapus via scheduled job bulanan
- `nexus_jobs`: retention 30 hari setelah `completed_at`, hapus via scheduled job harian

---

## 12. Docker Compose & Deployment

### 12.1 docker-compose.yml

```yaml
version: "3.9"

services:

  nexus-gateway:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: nexus-gateway
    command: uvicorn main:app --host 0.0.0.0 --port 8100 --workers 2 --timeout-keep-alive 120
    ports:
      - "127.0.0.1:8100:8100"    # hanya expose ke localhost, Nginx yang forward
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - REDIS_URL=redis://nexus-redis:6379/0
      - LITELLM_URL=${LITELLM_URL}
      - SECRET_KEY=${SECRET_KEY}
      - API_KEY_CACHE_TTL=300
      - LOG_LEVEL=INFO
    depends_on:
      nexus-redis:
        condition: service_healthy
    networks:
      - nexus-internal
    extra_hosts:
      - "host.docker.internal:host-gateway"    # untuk akses LiteLLM & MySQL di host
    restart: unless-stopped
    stop_grace_period: 2m
    deploy:
      resources:
        limits:
          memory: 256M
          cpus: "1.0"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8100/health/liveness"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s
    logging:
      driver: "json-file"
      options:
        max-size: "50m"
        max-file: "5"

  nexus-admin:
    build:
      context: ./admin
      dockerfile: Dockerfile
    container_name: nexus-admin
    command: streamlit run app.py --server.port 8501 --server.address 0.0.0.0
    ports:
      - "127.0.0.1:8501:8501"
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - API_URL=http://nexus-gateway:8100
    networks:
      - nexus-internal
    restart: unless-stopped

  nexus-worker:
    build:
      context: .
      dockerfile: Dockerfile
    command: python worker.py
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - REDIS_URL=redis://nexus-redis:6379/0
      - LITELLM_URL=${LITELLM_URL}
      - WORKER_CONCURRENCY=4
      - JOB_TIMEOUT_SECONDS=300
      - LOG_LEVEL=INFO
    depends_on:
      nexus-redis:
        condition: service_healthy
    networks:
      - nexus-internal
    extra_hosts:
      - "host.docker.internal:host-gateway"
    restart: unless-stopped
    stop_grace_period: 2m
    deploy:
      replicas: 2
      resources:
        limits:
          memory: 256M
          cpus: "1.0"
    logging:
      driver: "json-file"
      options:
        max-size: "50m"
        max-file: "5"

  nexus-redis:
    image: redis:7-alpine
    container_name: nexus-redis
    command: >
      redis-server
      --appendonly yes
      --appendfsync everysec
      --maxmemory 128mb
      --maxmemory-policy allkeys-lru
      --save 900 1
      --save 300 10
    volumes:
      - redis_data:/data
    networks:
      - nexus-internal
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 160M
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 3
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

networks:
  nexus-internal:
    driver: bridge

volumes:
  redis_data:
    driver: local
```

### 12.2 Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies untuk python-multipart dan pymysql
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    default-libmysqlclient-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Non-root user untuk security
RUN useradd -m -u 1000 nexus && chown -R nexus:nexus /app
USER nexus

EXPOSE 8100
```

### 12.3 requirements.txt

```
fastapi==0.111.0
uvicorn[standard]==0.29.0
sqlalchemy==2.0.30
pymysql==1.1.1
aiomysql==0.2.0
cryptography==42.0.7
redis==5.0.4
arq==0.25.0
passlib[bcrypt]==1.7.4
python-jose[cryptography]==3.3.0
python-multipart==0.0.9
httpx==0.27.0
pydantic==2.7.1
pydantic-settings==2.2.1
structlog==24.1.0
litellm==1.39.0
tenacity==8.3.0
google-cloud-firestore==2.15.0
```

### 12.4 Environment Variables (.env)

```bash
# Database
DATABASE_URL=mysql+pymysql://nexus_user:password@host.docker.internal:3306/nexus_db

# Redis — internal Docker network
REDIS_URL=redis://nexus-redis:6379/0

# LiteLLM — existing di host VM
LITELLM_URL=http://host.docker.internal:4000

# Security
SECRET_KEY=generate-random-64-char-string-here
ENCRYPTION_KEY=generate-fernet-key-here

# Cloud Infrastructure (Global)
GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/gcp-sa.json

# Worker
WORKER_CONCURRENCY=4
JOB_TIMEOUT_SECONDS=300
WEBHOOK_MAX_RETRIES=3

# Logging
LOG_LEVEL=INFO

# Opsional: alert bila worker tidak ada job dalam X menit
WORKER_IDLE_ALERT_MINUTES=30
```

### 12.5 Perintah Operasional

```bash
# Start semua service
docker compose up -d

# Lihat log gateway realtime
docker compose logs -f nexus-gateway

# Lihat log worker
docker compose logs -f nexus-worker

# Scale worker (tanpa downtime)
docker compose up -d --scale nexus-worker=4

# Restart hanya gateway (misalnya setelah update kode)
docker compose restart nexus-gateway

# Update kode dan rebuild
git pull
docker compose build nexus-gateway nexus-worker
docker compose up -d

# Stop semua
docker compose down

# Stop semua + hapus volume Redis (HATI-HATI: queue hilang)
docker compose down -v

# Cek status semua container
docker compose ps

# Cek resource usage
docker stats
```

---

## 13. Nginx Integration

### 13.1 Tambahan Server Block

Tambahkan konfigurasi berikut ke Nginx existing. Sesuaikan `server_name` dengan hostname yang digunakan oleh app client untuk mengakses Nexus.

```nginx
upstream nexus_gateway {
    server 127.0.0.1:8100;
    keepalive 32;
}

server {
    listen 80;
    server_name nexus.mpm-insurance.internal;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name nexus.mpm-insurance.internal;

    # SSL — gunakan certificate yang sudah ada di server
    # ssl_certificate     /path/to/cert.pem;
    # ssl_certificate_key /path/to/key.pem;

    # Gateway murni JSON, file besar lewat GCS
    client_max_body_size 2M;

    # Timeout generous untuk sync LLM calls
    # Sync chat/summarize bisa sampai 30 detik
    proxy_read_timeout    120s;
    proxy_connect_timeout  10s;
    proxy_send_timeout    120s;

    # Headers forwarding standar
    proxy_set_header Host              $host;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    # Penting untuk connection keepalive ke upstream
    proxy_http_version 1.1;
    proxy_set_header   Connection "";

    # Semua request → gateway
    # Admin Dashboard UI
    location /dashboard/ {
        proxy_pass http://127.0.0.1:8501/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    location / {
        proxy_pass http://nexus_gateway;
    }

    # Health check — tidak perlu auth, akses log dimatikan
    location /health/ {
        proxy_pass http://nexus_gateway;
        access_log off;
    }

    # Opsional: batasi akses admin hanya dari IP internal GCP VPC
    # location /v1/admin/ {
    #     allow 10.128.0.0/20;    # sesuaikan dengan subnet GCP VPC
    #     deny all;
    #     proxy_pass http://nexus_gateway;
    # }

    # Log format dengan request_id bila tersedia
    access_log /var/log/nginx/nexus_access.log combined;
    error_log  /var/log/nginx/nexus_error.log warn;
}
```

### 13.2 Reload Nginx

```bash
# Test konfigurasi sebelum reload
sudo nginx -t

# Reload tanpa downtime
sudo nginx -s reload
```

---

### 13.2 Keamanan Admin Dashboard (Streamlit)

Untuk mencegah akses tanpa izin ke UI Admin dan endpoint `/v1/admin/*`, kita menerapkan **HTTP Basic Authentication** di level Nginx.
Nginx akan memblokir request ke port 8501 kecuali user memasukkan Username dan Password yang dikonfigurasi melalui file `.htpasswd` di server.

```nginx
location /admin/ {
    auth_basic "Restricted Admin Area";
    auth_basic_user_file /etc/nginx/.htpasswd;
    
    proxy_pass http://127.0.0.1:8501/;
    ...
}
```

## 14. Struktur Project

```
nexus/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env                          # tidak di-commit ke git
├── .env.example                  # template, di-commit ke git
├── .gitignore
│
├── main.py                       # FastAPI app entry point
├── config.py                     # Settings via pydantic-settings dari env
├── database.py                   # SQLAlchemy engine (async), session factory
├── worker.py                     # arq worker entry point
├── webhook_dispatcher.py         # Retry logic untuk webhook callback
├── models.py                     # SQLAlchemy models (NexusApp, NexusJob, dll)
│
├── middleware/
│   ├── __init__.py
│   ├── auth.py                   # API key validation + Redis cache
│   └── rate_limiter.py           # Redis sliding window rate limiter
│
└── modules/
    ├── chat/
    │   ├── router.py             # POST /v1/ai/chat
    │   ├── service.py            # Chat & RAG logic
    │   ├── schemas.py            # Pydantic: ChatRequest, ChatResponse
    │   └── settings.json         # Konfigurasi spesifik modul chat
    │
    ├── ocr/
    │   ├── router.py             # POST /v1/ai/ocr
    │   ├── service.py            # OCR logic
    │   ├── schemas.py            # Pydantic schemas
    │   └── settings.json         # Konfigurasi spesifik modul ocr
    │
    ├── summarize/
    │   ├── router.py             # POST /v1/ai/summarize
    │   ├── service.py            # Summarize logic
    │   ├── schemas.py            # Pydantic schemas
    │   └── settings.json         # Konfigurasi spesifik modul summarize
    │
    ├── knowledge/
    │   ├── router.py             # POST /v1/ai/knowledge
    │   ├── service.py            # Firestore ingestion logic
    │   ├── schemas.py            # Pydantic schemas
    │   └── settings.json         # Konfigurasi spesifik modul knowledge
    │
    └── admin/
        ├── router.py             # /v1/admin/* endpoints
        ├── schemas.py            # Pydantic schemas
        └── settings.json         # Konfigurasi spesifik modul admin
```

---

## 15. Non-Functional Requirements

### 15.1 Performance

| Metrik | Target v1 | Target v3 |
|---|---|---|
| Gateway response — async (job_id) | < 500ms p95 | < 200ms p95 |
| Gateway response — sync chat | < 30 detik p95 | < 30 detik p95 |
| Gateway response — sync OCR single page | < 20 detik p95 | < 20 detik p95 |
| Job queue pickup latency | < 2 detik | < 1 detik |
| Webhook delivery setelah job done | < 5 detik | < 3 detik |
| Auth validation (cache hit) | < 5ms | < 5ms |
| Auth validation (cache miss) | < 50ms | < 30ms |

### 15.2 Reliability

| Metrik | Target |
|---|---|
| Availability gateway | 99.5% (downtime max ~44 jam/tahun) |
| Job durability | 99.9% — job yang masuk queue tidak hilang meski worker crash |
| Webhook delivery | 99% berhasil dalam 4 attempt (sisanya bisa polling) |
| Data loss saat restart | Nol — Redis append-only, MySQL transactional |

### 15.3 Capacity Limits

| Parameter | Limit |
|---|---|
| Max file size OCR (via URI) | Mengikuti limit Vertex AI / LiteLLM (disarankan < 50MB) |
| Max pages PDF OCR | 20 halaman (sync), unlimited (async) |
| Max text length Summarize | 100.000 karakter |
| Max messages dalam /v1/ai/chat | 50 messages |
| Max concurrent jobs per worker | 4 |
| Job result retention | 30 hari |
| Usage log retention | 1 tahun |

### 15.4 Scalability

| Trigger | Aksi |
|---|---|
| Worker queue depth > 50 job terus-menerus | Scale worker replicas: 2 → 4 |
| VM memory usage > 80% | Upgrade VM type atau pindahkan worker ke VM terpisah |
| Redis memory > 100MB | Tambah `maxmemory` atau dedicated Redis instance |
| Monthly requests > 20.000 | Evaluasi arsitektur untuk v3 |

---

## 16. Tech Stack

| Komponen | Teknologi | Versi | Alasan |
|---|---|---|---|
| Framework | FastAPI | 0.111 | Async native, auto OpenAPI docs, Pydantic v2 |
| ASGI server | uvicorn[standard] | 0.29 | Production-grade, support workers |
| Job queue library | arq | 0.25 | Redis-backed, async, simple API |
| ORM | SQLAlchemy | 2.0 | Async support, type-safe |
| MySQL driver | PyMySQL | 1.1 | Pure Python, no C extension needed |
| Redis client | redis-py | 5.0 | Official, async support |
| Password hashing | passlib[bcrypt] | 1.7 | Bcrypt untuk API key hash |
| LLM client | litellm | 1.39 | Abstraction layer, model routing |
| HTTP client | httpx | 0.27 | Async HTTP untuk webhook dispatch |
| Config management | pydantic-settings | 2.2 | Type-safe env vars |
| Logging | structlog | 24.1 | JSON structured logs |
| Retry logic | tenacity | 8.3 | Webhook retry dengan backoff |
| Container | Docker + Compose | latest | Reproducible, scale-ready |
| Reverse proxy | Nginx | existing | SSL termination, existing infra |
| Database | MySQL | existing | Konsistensi dengan apps lain |
| Message broker | Redis 7 | alpine | Job queue + rate limit counter + auth cache |
| Model provider | Vertex AI / Gemini | via LiteLLM | Existing setup di GCP |

---

## 17. Error Handling & Standar Response

### 17.1 HTTP Status Codes

| Code | Kondisi |
|---|---|
| 200 | Request berhasil (sync) |
| 202 | Request diterima dan di-queue (async) |
| 400 | Bad request — payload tidak valid, field wajib kurang |
| 401 | API key tidak valid atau tidak dikirim |
| 403 | App tidak memiliki permission ke endpoint ini |
| 404 | Resource tidak ditemukan (job_id tidak ada) |
| 409 | Conflict — misalnya cancel job yang sudah processing |
| 413 | File terlalu besar (> 10MB untuk OCR) |
| 422 | Validation error — Pydantic validation gagal |
| 429 | Rate limit tercapai |
| 500 | Internal server error |
| 502 | LiteLLM tidak dapat dihubungi |
| 504 | LLM timeout (sync mode) |

### 17.2 Format Error Response

```json
{
  "error": "string — error code (snake_case)",
  "message": "string — pesan yang human-readable",
  "request_id": "uuid",
  "details": { ... }    // opsional, untuk validation errors
}
```

**Contoh validation error (422):**
```json
{
  "error": "validation_error",
  "message": "Input tidak valid",
  "request_id": "uuid",
  "details": [
    {
      "field": "messages",
      "message": "field wajib diisi",
      "type": "missing"
    }
  ]
}
```

### 17.3 LLM Error Handling & Retry Policies

| LLM Error | Gateway Response |
|---|---|
| LiteLLM tidak dapat dihubungi | 502 Bad Gateway |
| LLM timeout (> 60s sync) | 504 Gateway Timeout |
| LLM rate limit dari Vertex | 429 + retry suggestion |
| LLM content filtered | 200 + `finish_reason: "content_filter"` |
| LLM context too long | 400 + message "Input terlalu panjang" |

#### 17.3.1 Asynchronous Retry with Backoff (Tenacity Integration)
Untuk meningkatkan reliabilitas terhadap gangguan jaringan sementara atau rate-limit (HTTP 429), Nexus mengintegrasikan library `tenacity` di level module service.

Aturan Retry:
- **Sync Requests**: Maksimal 2 retries dengan exponential backoff (penundaan minimum 2 detik, maksimum 6 detik). Hal ini menjaga client agar tidak mengalami timeout.
- **Async Requests (Background Worker)**: Maksimal 5 retries dengan exponential backoff (penundaan minimum 2 detik, maksimum 30 detik).

Penerapan pada service asinkron:
```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import litellm

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((litellm.exceptions.RateLimitError, litellm.exceptions.ServiceUnavailableError)),
    reraise=True
)
async def call_llm_with_retry(*args, **kwargs):
    return await litellm.acompletion(*args, **kwargs)
```

---

## 18. Logging & Observability

### 18.1 Structured Logging

Semua log dalam format JSON menggunakan `structlog`. Setiap log entry menyertakan:

```json
{
  "timestamp": "2026-05-05T10:30:00.123Z",
  "level": "info",
  "event": "request_completed",
  "request_id": "uuid",
  "app_id": "uuid",
  "app_name": "care",
  "caller_user_id": "usr-123",
  "endpoint": "/v1/ai/ocr",
  "response_mode": "sync",
  "status_code": 200,
  "latency_ms": 4200,
  "model_used": "gemini-1.5-pro",
  "total_tokens": 660
}
```

### 18.2 Log Events

| Event | Level | Deskripsi |
|---|---|---|
| `request_received` | info | Setiap request masuk |
| `auth_failed` | warning | API key tidak valid |
| `permission_denied` | warning | App tidak punya permission |
| `rate_limit_hit` | warning | Rate limit tercapai |
| `request_completed` | info | Request sync selesai |
| `job_queued` | info | Job async masuk queue |
| `job_started` | info | Worker mulai proses job |
| `job_completed` | info | Job selesai |
| `job_failed` | error | Job gagal |
| `webhook_sent` | info | Webhook berhasil dikirim |
| `webhook_failed` | error | Webhook gagal setelah semua retry |
| `litellm_error` | error | Error dari LiteLLM / Vertex |
| `worker_startup` | info | Worker process start |
| `worker_requeue` | warning | Job stuck di-requeue saat startup |

### 18.3 Monitoring Rekomendasi

Untuk v1 (simple, no additional infra):

```bash
# Watch error rate realtime
docker compose logs -f nexus-gateway | grep '"level":"error"'

# Count requests per jam
docker compose logs nexus-gateway | grep 'request_completed' | grep "2026-05-05T10:" | wc -l

# Check job queue depth
docker exec nexus-redis redis-cli LLEN nexus:jobs:queue

# Check Redis memory
docker exec nexus-redis redis-cli INFO memory | grep used_memory_human
```

Untuk v2 (bila traffic naik): integrasi ke GCP Cloud Monitoring atau Grafana.

---

## 19. Security Considerations

### 19.1 API Key Security

- API key hash menggunakan bcrypt dengan cost factor 12
- Plaintext key ditampilkan **satu kali** saat generate — tidak tersimpan di DB
- Key rotation tersedia via `POST /v1/admin/apps/{id}/rotate-key`
- Prefix `nexus-live-` membantu deteksi kebocoran via secret scanning (GitHub, dll)

### 19.2 Network Security

- Port 8100 (gateway) hanya bind ke `127.0.0.1` — tidak exposed langsung ke network
- Redis hanya accessible dalam Docker internal network (`nexus-internal`)
- Semua traffic eksternal melalui Nginx (SSL termination)
- `/v1/admin/*` endpoints direkomendasikan dibatasi oleh IP di level Nginx

### 19.3 File Upload Security (OCR)

- Validasi MIME type sebelum proses (tidak hanya extension)
- File size limit 10MB enforced di FastAPI layer dan Nginx (`client_max_body_size 15M`)
- File disimpan di `/tmp/nexus_uploads/{request_id}/` dengan nama yang disanitasi
- File dihapus **segera** setelah proses selesai atau terjadi error (via `try/finally`)
- Tidak ada file yang tersimpan permanen di v1

### 19.4 Webhook Security

- HMAC-SHA256 signature di setiap webhook payload
- Timestamp dalam signature untuk mencegah replay attack (tolak bila > 5 menit)
- `webhook_secret` berbeda per app, disimpan secara aman menggunakan *symmetric encryption* (`cryptography.fernet`) di DB menggunakan `ENCRYPTION_KEY` dari environment variable.

### 19.5 Input Validation

- Semua request body divalidasi oleh Pydantic schema sebelum masuk ke handler
- Max length check untuk semua string input (text, schema, dll)
- SQL injection tidak relevan — Nexus tidak mengeksekusi SQL yang di-generate

### 19.6 Gateway-Level Guardrails (Infinite Loop Prevention)

Untuk mencegah membengkaknya biaya akibat kesalahan logika aplikasi klien (seperti loop ReAct yang tidak berujung), Nexus menerapkan pembatasan di level gateway:

1. **Cumulative Token Rate Limiting**: Redis melacak total token (`prompt` + `completion`) yang digunakan per jam per `app_id`. Jika aplikasi melewati 10.000.000 token dalam satu jam, seluruh request selanjutnya akan diblokir otomatis (`HTTP 429 Rate Limit Exceeded`) hingga window bergeser.
2. **Strict max_tokens Clamping**: Nilai parameter `max_tokens` pada request chat dibatasi maksimal `4096` di FastAPI Pydantic schema. Request di atas batas tersebut akan dipangkas atau ditolak.
3. **Max Messages Constraint**: Jumlah item dalam array `messages` di `POST /v1/ai/chat` dibatasi maksimal `50` untuk menghindari eksploitasi context window yang membengkakkan tagihan.

---

## 20. Roadmap

### v1 — 2026 (Current)

- 3 modul AI: chat, OCR, summarize
- M2M auth via API key per app
- Layered user context (X-User-Id, X-User-Name)
- Sync dan async response mode
- Redis job queue + arq worker
- Webhook dengan HMAC signature + retry
- Polling endpoint
- Admin endpoints (CRUD apps, permissions, usage report)
- Usage logging lengkap
- Docker Compose deployment
- Nginx integration (server block tambahan)

### v2 — 2027

| Item | Deskripsi |
|---|---|
| RAG proper | Integrasi ChromaDB atau Vertex Matching Engine untuk knowledge base per app |
| Priority queue | Job priority: `high`, `normal`, `low` — via header `X-Job-Priority` |
| Model fallback | Auto fallback ke Gemini Flash bila Pro sedang throttle |
| Worker scale ke 4 | Sesuai proyeksi traffic 15K req/bulan |
| GCP Cloud Monitoring | Dashboard metrik: latency, error rate, queue depth, token usage |

### v3 — 2028

| Item | Deskripsi |
|---|---|
| Worker VM dedicated | Pindahkan worker containers ke GCP VM terpisah, scale independent |
| Redis Sentinel | High availability Redis untuk produksi |
| Cost dashboard | Integrasi dengan GCP Billing API, cost breakdown per app per modul |
| Auto-scaling trigger | Script otomatis scale worker berdasarkan queue depth |
| Multi-region | Evaluasi bila ada kebutuhan region selain Jakarta |

---



---

## 21. Implementation Guidelines for AI Coding Agents

Bagian ini ditujukan khusus untuk AI Agent (seperti Claude/Gemini) yang akan melakukan *scaffolding* atau *coding* platform ini. Ikuti aturan berikut dengan ketat:

### 21.1 SQLAlchemy & Database Models
1. **Base Class:** Gunakan `sqlalchemy.orm.DeclarativeBase`.
2. **Relationships:** 
   - `NexusApp` memiliki `relationship("NexusAppPermission", back_populates="app")`
   - `NexusApp` memiliki `relationship("NexusRateLimit", back_populates="app")`
   - Gunakan tipe data `JSON` milik SQLAlchemy untuk kolom `request_payload` dan `result_payload`.
3. **Async DB:** Wajib menggunakan `ext.asyncio.AsyncSession` dan `create_async_engine` (misal driver: `aiomysql` atau `asyncmy`).

### 21.2 FastAPI & Pydantic
1. **Dependency Injection:** Semua router wajib menggunakan `Depends(verify_api_key)` yang me-return *object* `NexusApp`.
2. **Pydantic v2:** Gunakan anotasi `Field` untuk validasi. Misal `app_name: str = Field(..., max_length=50)`.
3. **Modular Router:** Setiap router di `modules/{nama_modul}/router.py` harus memiliki `APIRouter(prefix="/v1/ai/{modul}", tags=["{Modul}"])` dan di-*include* ke `main.py`.
4. **Settings:** Buat class `pydantic-settings` `BaseSettings` untuk membaca `.env` global, dan `json` library biasa untuk membaca `settings.json` di setiap folder modul.

### 21.3 LiteLLM & Firestore
1. **LiteLLM:** Gunakan `litellm.acompletion(...)` secara asinkron agar tidak memblokir *thread* FastAPI. Endpoint LiteLLM Proxy di-pass ke parameter `api_base`.
2. **Firestore (RAG):** 
   - Gunakan `google-cloud-firestore` (async client jika ada, atau wrap ke threadpool).
   - Format Dokumen di Firestore: `{"content": "str", "embedding": VectorValue([float]), "metadata": dict}`. 
   - Gunakan `google.cloud.firestore_v1.vector.Vector` untuk inisialisasi kNN search.

### 21.4 Background Worker (arq)
1. **arq:** Gunakan library `arq` (Redis queue untuk Python).
2. Fungsi asinkron yang dieksekusi `arq` (misal `process_ocr_job`) harus meng-update `nexus_jobs` menjadi `processing`, menjalankan `litellm.acompletion` / Vertex AI, lalu update menjadi `done`/`failed`.
3. Jika `callback_url` ada, oper tugas HTTP POST webhook ke fungsi `arq` terpisah (`dispatch_webhook`) agar tidak memperlambat status "done".

### 21.5 File Loading & Configuration (settings.json)
1. **Caching:** AI Agent wajib membaca `settings.json` menggunakan `json.load()` yang dibungkus dengan `@functools.lru_cache()` agar file tidak dibaca berulang kali dari disk setiap kali ada request.
2. **Environment Variables:** Variabel global seperti kredensial DB dan LiteLLM URL wajib di-load menggunakan Pydantic v2 `BaseSettings`.

### 21.6 Error Handling & Logging
1. **Global Exception Handler:** Wajib mengimplementasikan `@app.exception_handler(Exception)` di `main.py` untuk memastikan seluruh *uncaught exceptions* mengembalikan HTTP 500 dalam format JSON standar Nexus (`{"error": "internal_error", "request_id": "..."}`).
2. **Logging:** Gunakan library standar `logging` Python yang dikonfigurasi menggunakan JSON Formatter. Hal ini sangat penting karena log akan dikirim ke GCP Cloud Logging yang mewajibkan struktur JSON.

### 21.7 Langkah Scaffolding (Untuk AI Agent Berikutnya)
Saat AI Agent menerima dokumen ini untuk mulai coding, lakukan sesuai urutan berikut:
1. `mkdir -p modules/chat modules/ocr modules/summarize modules/knowledge`
2. Buat file `database.py` (untuk koneksi `asyncmy`) dan `models.py` (SQLAlchemy).
3. Setup `main.py` dan includekan semua router dari `modules/*/router.py`.
4. Implementasikan `worker.py` menggunakan `arq`.


## 22. Open Questions (All Resolved)

| # | Pertanyaan | Impact | Final Decision |
|---|---|---|---|
| OQ-01 | Hak Akses MySQL user `nexus_user` | DB setup | **[RESOLVED]** Menggunakan prinsip Least Privilege. Aplikasi Nexus hanya memiliki akses `SELECT, INSERT, UPDATE, DELETE` pada `nexus_db.*`. Pembuatan struktur tabel (migration) dilakukan manual oleh DBA/Admin. |
| OQ-02 | Worker requeue limit untuk job stuck | Reliability | **[RESOLVED]** Limit ditetapkan 5 menit. Bila worker mati dan job tertahan `processing` > 5 menit, Auto-Sweeper mengembalikannya ke `queued`. |
| OQ-03 | Rotasi API Key saat terjadi kebocoran | Security | **[RESOLVED]** Menggunakan endpoint khusus `/v1/admin/apps/{id}/rotate-key`. Sistem membuat Key baru dan instan menghapus cache Redis Key lama. UI dilindungi HTTP Basic Auth di level Nginx. |
| OQ-04 | Posisi dan Akses URL LiteLLM | Config | **[RESOLVED]** LiteLLM berjalan terpisah. URL-nya disetel murni melalui Environment Variable `.env` (`LITELLM_API_BASE`). |
| OQ-05 | Hostname & Domain Nexus | Deployment | **[RESOLVED]** Nexus menggunakan Domain dengan Public IP. Keamanan dijamin lewat IP Whitelisting (allow/deny rules di Nginx/Firewall) untuk membatasi akses klien. |

---

*Dokumen ini adalah living document. Update seiring progress development dan keputusan teknis baru.*

*Versi selanjutnya: v0.4 setelah scaffolding kode selesai dan first endpoint berjalan.*
