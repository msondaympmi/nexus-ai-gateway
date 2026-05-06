from fastapi import APIRouter, Depends, Request, Header
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from database import get_db
from models import NexusApp
from middleware.rate_limiter import check_rate_limits
from middleware.auth import require_permission
from modules.chat.schemas import ChatRequest, ChatResponse
from modules.chat.service import execute_chat_completion

router = APIRouter(prefix="/v1/ai/chat", tags=["Chat"])


# Fix #12: inject check_rate_limits only ONCE as the named app dep
# require_permission wraps verify_api_key internally, but check_rate_limits also
# calls verify_api_key via its own Depends chain — FastAPI deduplicates same-signature deps.
@router.post("", dependencies=[Depends(require_permission("chat"))])
async def chat_endpoint(
    request: ChatRequest,
    req_obj: Request,
    app: NexusApp = Depends(check_rate_limits),
    db: AsyncSession = Depends(get_db),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    x_user_name: Optional[str] = Header(None, alias="X-User-Name")
):
    """
    POST /v1/ai/chat
    Executes synchronous chat completions with optional RAG pre-retrieval and function calling.
    Supports Server-Sent Events streaming when stream=true in the request body.
    Validates API key prefix authentication and rate limits.
    """
    return await execute_chat_completion(
        request=request,
        app=app,
        db=db,
        user_id=x_user_id,
        user_name=x_user_name
    )
