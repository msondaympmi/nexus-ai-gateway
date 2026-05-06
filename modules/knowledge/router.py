from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import NexusApp
from middleware.rate_limiter import check_rate_limits
from middleware.auth import require_permission
from modules.knowledge.schemas import KnowledgeRequest, KnowledgeResponse
from modules.knowledge.service import execute_knowledge_ingestion

router = APIRouter(prefix="/v1/ai/knowledge", tags=["Knowledge"])


@router.post(
    "",
    response_model=KnowledgeResponse,
    dependencies=[Depends(require_permission("knowledge"))]
)
async def knowledge_endpoint(
    request: KnowledgeRequest,
    req_obj: Request,
    app: NexusApp = Depends(check_rate_limits)
):
    """
    POST /v1/ai/knowledge
    Ingests source documents into GCP Firestore under strict app_id tenant isolation.
    """
    return await execute_knowledge_ingestion(
        request=request,
        app=app
    )
