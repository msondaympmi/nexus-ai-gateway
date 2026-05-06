from fastapi import APIRouter, Depends, Request, Header, Response
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from database import get_db
from models import NexusApp
from middleware.rate_limiter import check_rate_limits
from middleware.auth import require_permission
from modules.ocr.schemas import OcrRequest, OcrResponse
from modules.ocr.service import execute_ocr
from modules.jobs.service import enqueue_async_job

router = APIRouter(prefix="/v1/ai/ocr", tags=["OCR"])


@router.post(
    "",
    dependencies=[Depends(require_permission("ocr"))]
)
async def ocr_endpoint(
    request: OcrRequest,
    req_obj: Request,
    response: Response,
    app: NexusApp = Depends(check_rate_limits),
    db: AsyncSession = Depends(get_db),
    x_response_mode: Optional[str] = Header("sync", alias="X-Response-Mode"),
    x_callback_url: Optional[str] = Header(None, alias="X-Callback-Url"),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    x_user_name: Optional[str] = Header(None, alias="X-User-Name")
):
    """
    POST /v1/ai/ocr
    Extracts text from images or PDF files synchronously or asynchronously in the background.
    """
    # 1. Handle Asynchronous Response Mode (Section 6.3 & Section 8.5)
    if x_response_mode.lower() == "async":
        response.status_code = 202
        return await enqueue_async_job(
            app_id=app.id,
            endpoint="/v1/ai/ocr",
            request_payload=request.model_dump(),
            webhook_url=x_callback_url,
            db=db
        )

    # 2. Handle Synchronous Response Mode (Default)
    return await execute_ocr(
        request=request,
        app=app,
        db=db,
        user_id=x_user_id,
        user_name=x_user_name
    )
