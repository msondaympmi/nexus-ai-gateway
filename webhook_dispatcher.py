import time
import hmac
import hashlib
import json
import logging
from typing import Dict, Any, Optional
from cryptography.fernet import Fernet
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config import settings

logger = logging.getLogger("nexus.webhook")

# Fix #5: Wrap Fernet init — a bad key at import time would crash the whole app
try:
    fernet = Fernet(settings.ENCRYPTION_KEY.encode())
except Exception as _fernet_init_err:
    logger.error(
        f"ENCRYPTION_KEY is invalid — Fernet cipher not initialized: {_fernet_init_err}. "
        "Webhook signing will fall back to raw ENCRYPTION_KEY bytes."
    )
    fernet = None



def decrypt_webhook_secret(encrypted_secret: str) -> bytes:
    """Decrypts the application-specific webhook secret from DB using the global ENCRYPTION_KEY."""
    if fernet is None:
        logger.warning("Fernet not initialized; returning raw ENCRYPTION_KEY bytes as fallback.")
        return settings.ENCRYPTION_KEY.encode()
    try:
        return fernet.decrypt(encrypted_secret.encode())
    except Exception as e:
        logger.error(f"Failed to decrypt webhook secret: {e}")
        # Fallback to global key if encryption fails or secret was plaintext
        return settings.ENCRYPTION_KEY.encode()



def sign_payload(payload_bytes: bytes, secret: bytes, timestamp: int) -> str:
    """
    Generates a secure HMAC-SHA256 signature combining payload and timestamp.
    m = hmac.new(secret, payload + b'.' + str(timestamp).encode(), sha256)
    """
    message = payload_bytes + b"." + str(timestamp).encode()
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


# Webhook retry params sourced from config.py (overridable via .env)
@retry(
    reraise=True,
    stop=stop_after_attempt(settings.WEBHOOK_MAX_RETRY_ATTEMPTS),
    wait=wait_exponential(
        multiplier=settings.WEBHOOK_RETRY_MULTIPLIER,
        min=settings.WEBHOOK_RETRY_WAIT_MIN_SEC,
        max=settings.WEBHOOK_RETRY_WAIT_MAX_SEC
    ),
    retry=retry_if_exception_type((httpx.HTTPError, httpx.NetworkError)),
    before_sleep=lambda retry_state: logger.info(
        f"Webhook dispatch attempt {retry_state.attempt_number} failed. Retrying..."
    )
)
async def perform_webhook_post(url: str, payload_str: str, headers: Dict[str, str]) -> httpx.Response:
    """Wrapper function to perform the actual HTTP POST with retry handling."""
    async with httpx.AsyncClient(timeout=settings.WEBHOOK_TIMEOUT_SEC) as client:
        response = await client.post(url, content=payload_str, headers=headers)
        response.raise_for_status()
        return response



async def dispatch_webhook(
    url: str,
    app_id: str,
    app_name: str,
    encrypted_secret: Optional[str],
    event_type: str,
    job_id: str,
    endpoint: str,
    caller_user_id: Optional[str],
    latency_ms: Optional[int],
    result_payload: Dict[str, Any]
) -> bool:
    """
    Asynchronously signs and dispatches a webhook callback to the registered client URL.
    Returns True if successfully sent, False otherwise.
    """
    # 1. Prepare webhook payload (Section 19.4 / 10.2)
    timestamp = int(time.time())
    payload = {
        "event": event_type,
        "job_id": job_id,
        "app_id": app_id,
        "app_name": app_name,
        "endpoint": endpoint,
        "caller_user_id": caller_user_id,
        "latency_ms": latency_ms,
        "timestamp": timestamp,
        "result": result_payload
    }
    
    payload_str = json.dumps(payload)
    payload_bytes = payload_str.encode("utf-8")

    # 2. Decrypt secret and sign payload (HMAC-SHA256)
    secret_bytes = decrypt_webhook_secret(encrypted_secret) if encrypted_secret else settings.ENCRYPTION_KEY.encode()
    signature = sign_payload(payload_bytes, secret_bytes, timestamp)

    headers = {
        "Content-Type": "application/json",
        "X-Nexus-Signature": f"sha256={signature}",
        "X-Nexus-Timestamp": str(timestamp)
    }

    logger.info(f"Dispatching webhook event '{event_type}' to {url} for Job {job_id}")

    try:
        response = await perform_webhook_post(url, payload_str, headers)
        logger.info(f"Webhook delivered successfully to {url}. Status: {response.status_code}")
        return True
    except Exception as e:
        logger.error(f"Webhook delivery failed permanently for Job {job_id} after maximum retries: {e}")
        return False
