# 💬 Chatbot & Multi-Tenant RAG API Contract

The **Chat Module** provides conversational AI capabilities with optional context injection, multi-tenant vector search (RAG) against GCP Firestore, and agentic tool (function) calling.

## 📍 Endpoint Specification
*   **Path**: `/v1/ai/chat`
*   **Method**: `POST`
*   **Response Modes**: Synchronous (`sync` only. Streaming/SSE is not supported in `async` response mode).

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
  "messages": [
    { "role": "system", "content": "You are a helpful insurance assistant." },
    { "role": "user", "content": "How do I claim my car insurance?" }
  ],
  "model": "gemini-1.5-pro",
  "temperature": 0.7,
  "max_tokens": 2048,
  "use_rag": false,
  "tools": null,
  "tool_choice": "auto"
}
```

### ⚙️ Parameter Reference
| Field | Type | Default | Constraints / Guardrails | Description |
| :--- | :--- | :--- | :--- | :--- |
| `messages` | `Array` | *Required* | Max `50` items | Conversation history with `role` (`user`, `assistant`, `system`) and `content`. |
| `model` | `String` | `"gemini-1.5-pro"` | `gemini-1.5-pro` \| `gemini-1.5-flash` | Use `gemini-1.5-flash` for high-speed, lower-cost tasks. |
| `temperature` | `Float` | `0.7` | `0.0` to `2.0` | Controls randomness of completion. |
| `max_tokens` | `Integer` | `2048` | Max `4096` | Output token limits. |
| `use_rag` | `Boolean` | `false` | - | If `true`, triggers Firestore semantic vector search filtered strictly by your `app_id`. |
| `tools` | `Array` | `null` | - | Whitelist JSON schemas for standard OpenAI-style function calling. |
| `tool_choice` | `String` | `"auto"` | `"auto"` \| `"none"` | Function calling association control. |

---

## 📤 Response Schema (Synchronous)

```json
{
  "id": "chatcmpl-a93f8281",
  "object": "chat.completion",
  "created": 1746441000,
  "model": "gemini-1.5-pro",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "To submit a car insurance claim at MPM Insurance, you need to prepare...",
        "tool_calls": null
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 128,
    "completion_tokens": 256,
    "total_tokens": 384
  },
  "cost_usd": 0.001440
}
```

### 💸 Cost Rates (Gemini)
Calculated automatically in real-time and tracked inside your application's cost sheets:
*   **Gemini 1.5 Pro**: Input: `$1.25` / 1M tokens | Output: `$5.00` / 1M tokens
*   **Gemini 1.5 Flash**: Input: `$0.075` / 1M tokens | Output: `$0.30` / 1M tokens

---

## 🔒 Security Guardrails
1.  **Strict Message Clamping**: Requests with more than 50 messages will return `422 Unprocessable Entity` to prevent billing exploits.
2.  **Cumulative Rate Limiting**: If your application exceeds **10,000,000** total tokens within a single hour, further requests are blocked automatically with `HTTP 429 Rate Limit Exceeded`.
