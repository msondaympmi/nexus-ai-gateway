# 📝 Summarization API Contract

The **Summarize Module** compresses long paragraphs, articles, or full policy documents into readable bullet points or structured paragraphs.

## 📍 Endpoint Specification
*   **Path**: `/v1/ai/summarize`
*   **Method**: `POST`
*   **Response Modes**: Synchronous (`sync`) and Asynchronous (`async`).

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
  "text": "MPM Insurance provides comprehensive coverage for both commercial and non-commercial motor vehicles...",
  "length": "medium",
  "model": "gemini-1.5-flash"
}
```

### ⚙️ Parameter Reference
| Field | Type | Default | Constraints / Guardrails | Description |
| :--- | :--- | :--- | :--- | :--- |
| `text` | `String` | *Required* | Max `100,000` chars | The raw text to be summarized. Longer texts should be processed via `async` response mode. |
| `length` | `String` | `"medium"` | `"short"` \| `"medium"` \| `"long"` | Controls the depth/length of the summarized output. |
| `model` | `String` | `"gemini-1.5-flash"` | `gemini-1.5-flash` \| `gemini-1.5-pro` | Gemini Flash is recommended for summarizations due to excellent latency and cost efficiency. |

---

## 📤 Response Schema

### 1. Synchronous Response (`X-Response-Mode: sync`)
```json
{
  "summary": "• MPM Insurance covers commercial and personal vehicles.\• Comprehensive insurance covers accidents, third-party liability, and natural disasters.",
  "original_length": 8420,
  "summary_length": 182,
  "usage": {
    "prompt_tokens": 1420,
    "completion_tokens": 120,
    "total_tokens": 1540
  },
  "cost_usd": 0.000142
}
```

### 2. Asynchronous Response (`X-Response-Mode: async`)
```json
{
  "job_id": "7ca21d9b-1284-4821-b184-a8291082a92c",
  "status": "queued",
  "poll_url": "/v1/ai/jobs/7ca21d9b-1284-4821-b184-a8291082a92c",
  "estimated_seconds": 10
}
```
*Downstream apps must either poll the `/v1/ai/jobs/{job_id}` endpoint or handle the secure signed webhook payload dispatched upon completion.*
