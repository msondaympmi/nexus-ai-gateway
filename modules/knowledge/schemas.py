from pydantic import BaseModel, Field
from typing import Optional

# A-2: Load module settings so schema defaults match service behavior
from config import load_module_settings
_kb_cfg = load_module_settings("knowledge")
_DEFAULT_CHUNK_SIZE = _kb_cfg.get("default_chunk_size", 1000)
_DEFAULT_CHUNK_OVERLAP = _kb_cfg.get("default_chunk_overlap", 200)


class KnowledgeRequest(BaseModel):
    document_id: str = Field(..., description="Unique ID for the document")
    content: str = Field(..., description="Raw text content to index")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Metadata key-values")


class KnowledgeResponse(BaseModel):
    status: str = "success"
    document_id: str
    chunks_indexed: int
    message: str
