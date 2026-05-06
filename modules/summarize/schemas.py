from pydantic import BaseModel, Field
from typing import Optional

# C-3: Load module settings so validators use the same limits as the service
from config import load_module_settings
_sum_cfg = load_module_settings("summarize")
_MAX_CHAR_LENGTH = _sum_cfg.get("max_character_length", 100000)
_DEFAULT_MODEL = _sum_cfg.get("default_model", "gemini-1.5-flash")
_DEFAULT_LENGTH = _sum_cfg.get("default_length", "medium")


class SummarizeRequest(BaseModel):
    text: str = Field(..., max_length=_MAX_CHAR_LENGTH, description="Text content to be summarized")
    language: Optional[str] = Field("id", description="Target language of the summary (e.g. 'id', 'en')")
    style: Optional[str] = Field("paragraph", pattern="^(bullet|paragraph|executive)$", description="Style of the summary")
    max_length: Optional[int] = Field(None, description="Approximate maximum length (in words) for the summary")
    focus: Optional[str] = Field(None, description="Specific topic to focus the summary on")
    model: Optional[str] = _DEFAULT_MODEL


class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class SummarizeResponse(BaseModel):
    summary: str
    language: str
    style: str
    compression_ratio: float
    usage: Usage
    cost_usd: float = 0.000000
