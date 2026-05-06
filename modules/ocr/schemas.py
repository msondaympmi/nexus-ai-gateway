from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

# C-3: Load module settings so validators use the same limits as the service
from config import load_module_settings
_ocr_cfg = load_module_settings("ocr")
_DEFAULT_MODEL = _ocr_cfg.get("default_model", "gemini-1.5-flash")


class OcrRequest(BaseModel):
    file_uri: str = Field(..., description="Absolute URL to the image or PDF file stored in cloud storage")
    output_format: Optional[str] = Field("text", description="'text', 'json', or 'markdown'")
    extraction_schema: Optional[Dict[str, Any]] = Field(None, description="JSON schema if output_format is json")
    language_hint: Optional[str] = Field("id,en", description="Hint for OCR engine")
    page_range: Optional[str] = Field("all", description="Pages to extract (e.g. '1-3', 'all')")
    model: Optional[str] = _DEFAULT_MODEL


class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class OcrResponse(BaseModel):
    filename: str
    output_format: str
    page_count: int
    result: str
    confidence_note: str
    usage: Usage
    cost_usd: float = 0.000000
