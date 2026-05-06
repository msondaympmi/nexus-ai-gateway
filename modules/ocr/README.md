# 👁️ OCR (Optical Character Recognition) API Contract

The **OCR Module** extracts text from uploaded images or PDF files using multimodal Gemini Vision.

## 📍 Endpoint Specification
*   **Path**: `/v1/ai/ocr`
*   **Method**: `POST`
*   **Response Modes**: Synchronous (`sync`) and Asynchronous (`async`). Async is highly recommended for PDF files with more than 2 pages.

---

## 📥 Request Schema

### Headers
```http
Authorization: Bearer <your-api-key>
Content-Type: application/json
X-Response-Mode: sync               # Options: sync | async (Default: sync)
X-Callback-Url: https://mycallback  # Optional: Overrides default app webhook URL (Async mode only)
X-User-Id: usr-123                  # Optional: For audit trail
X-User-Name: budi.santoso           # Optional: For audit trail
```

### JSON Body
```json
{
  "file_url": "gs://mpm-bucket/documents/policy_invoice.pdf",
  "model": "gemini-1.5-flash"
}
```

### ⚙️ Parameter Reference
| Field | Type | Default | Constraints / Guardrails | Description |
| :--- | :--- | :--- | :--- | :--- |
| `file_url` | `String` | *Required* | Absolute URL | Publicly readable URL or Google Cloud Storage URI (`gs://`) of the file. |
| `model` | `String` | `"gemini-1.5-flash"` | `gemini-1.5-flash` \| `gemini-1.5-pro` | `gemini-1.5-flash` is heavily recommended for simple parsing to lower latency and costs. |

---

## 📤 Response Schema

### 1. Synchronous Response (`X-Response-Mode: sync`)
Returned directly in the HTTP response body once processing completes (usually 4–15 seconds).

```json
{
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
```

### 2. Asynchronous Response (`X-Response-Mode: async`)
Returned immediately (`< 500ms`) with a job tracking payload.

```json
{
  "job_id": "8fa21c8b-7182-4112-a1b2-10821b028ab2",
  "status": "queued",
  "poll_url": "/v1/ai/jobs/8fa21c8b-7182-4112-a1b2-10821b028ab2",
  "estimated_seconds": 15
}
```
*Downstream apps must either poll the `/v1/ai/jobs/{job_id}` endpoint or handle the secure signed webhook payload dispatched upon completion.*
