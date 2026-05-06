# 🔄 Jobs & Async Queue Management API Contract

The **Jobs Module** handles tracking, polling, and results retrieval for long-running asynchronous AI processes (like large OCR files or text summarization).

---

## 📍 Endpoint Specification
*   **Path**: `/v1/ai/jobs/{job_id}`
*   **Method**: `GET`
*   **Response Modes**: Synchronous.

---

## 📥 Request Schema

### Headers
```http
Authorization: Bearer <your-api-key>
```

---

## 📤 Response Schema

### 1. Status: `queued`
The job is accepted and resides in the Redis `arq` queue waiting for a background worker.
```json
{
  "job_id": "8fa21c8b-7182-4112-a1b2-10821b028ab2",
  "status": "queued",
  "endpoint": "/v1/ai/ocr",
  "queued_at": "2026-05-07T03:00:00Z",
  "position_in_queue": 1,
  "estimated_wait_seconds": 15
}
```

### 2. Status: `processing`
A background worker is actively running the job and contacting the AI providers.
```json
{
  "job_id": "8fa21c8b-7182-4112-a1b2-10821b028ab2",
  "status": "processing",
  "endpoint": "/v1/ai/ocr",
  "queued_at": "2026-05-07T03:00:00Z",
  "started_at": "2026-05-07T03:00:15Z"
}
```

### 3. Status: `done`
The processing has successfully completed and results are returned inside the `result` field.
```json
{
  "job_id": "8fa21c8b-7182-4112-a1b2-10821b028ab2",
  "status": "done",
  "endpoint": "/v1/ai/ocr",
  "queued_at": "2026-05-07T03:00:00Z",
  "started_at": "2026-05-07T03:00:15Z",
  "completed_at": "2026-05-07T03:00:22Z",
  "latency_ms": 7000,
  "result": {
    "extracted_text": "MPM INSURANCE POLIS ASURANSI KENDARAAN...\nNo Polis: POL-99212...",
    "metadata": {
      "file_url": "gs://mpm-bucket/documents/policy_invoice.pdf",
      "pages": 1,
      "confidence": 0.99
    },
    "usage": {
      "prompt_tokens": 1240,
      "completion_tokens": 320,
      "total_tokens": 1560
    },
    "cost_usd": 0.000189
  }
}
```

### 4. Status: `failed`
The job failed due to an upstream error, bad payload, or processing timeout.
```json
{
  "job_id": "8fa21c8b-7182-4112-a1b2-10821b028ab2",
  "status": "failed",
  "endpoint": "/v1/ai/ocr",
  "queued_at": "2026-05-07T03:00:00Z",
  "started_at": "2026-05-07T03:00:15Z",
  "completed_at": "2026-05-07T03:00:30Z",
  "error_message": "Vertex AI Service Unavailable: please try again later"
}
```

---

## 🔒 Strict App-Isolation
Downstream applications can **only** query jobs that were created by their own `app_id`. Trying to retrieve a job belonging to a different application will instantly trigger `HTTP 403 Forbidden`.
