# 📚 Knowledge Ingestion (Firestore RAG) API Contract

The **Knowledge Ingestion Module** parses PDF or text documents into overlapping chunks, generates 768-dimensional embeddings, and indexes them securely inside GCP Firestore.

---

## 📍 Endpoint Specification
*   **Path**: `/v1/ai/knowledge`
*   **Method**: `POST`
*   **Response Modes**: Synchronous (`sync` only).

---

## 📥 Request Schema

### Headers
```http
Authorization: Bearer <your-api-key>
Content-Type: application/json
X-User-Id: usr-123                  # Optional: For audit trail
X-User-Name: budi.santoso           # Optional: For audit trail
```

### JSON Body
```json
{
  "file_url": "gs://mpm-bucket/kb/car_insurance_procedures.txt",
  "doc_name": "Prosedur Klaim Mobil",
  "doc_id": "doc-car-01",
  "chunk_size": 1000,
  "chunk_overlap": 200
}
```

### ⚙️ Parameter Reference
| Field | Type | Default | Constraints / Guardrails | Description |
| :--- | :--- | :--- | :--- | :--- |
| `file_url` | `String` | *Required* | Absolute URL | URL or Google Cloud Storage URI (`gs://`) pointing to the source text file. |
| `doc_name` | `String` | *Required* | Max `100` chars | Friendly identifier name for the document. |
| `doc_id` | `String` | `None` | Optional | Custom unique identifier. If not provided, a random UUID will be generated. |
| `chunk_size` | `Integer` | `1000` | `100` to `5000` | Number of characters per text chunk. |
| `chunk_overlap` | `Integer` | `200` | `0` to `1000` | Overlap character length between neighboring chunks. |

---

## 📤 Response Schema

```json
{
  "status": "success",
  "doc_id": "doc-car-01",
  "chunks_count": 14,
  "message": "Dokumen berhasil diparsing menjadi 14 chunks dan diindeks ke database"
}
```

---

## 🔒 Strict Application Isolation (Tenant Security)
When a document is indexed via this endpoint, every chunk is automatically tagged with your application's unique `app_id`. 

When calling `/v1/ai/chat` with `use_rag=true`, **only documents belonging to your own `app_id` are searched and retrieved**. There is zero possibility of cross-tenant data leaks.
