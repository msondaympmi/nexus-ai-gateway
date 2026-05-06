from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

# Load module settings so validators use the same limits as the service
from config import load_module_settings
_chat_cfg = load_module_settings("chat")
_MAX_MESSAGES = _chat_cfg.get("max_messages_limit", 50)
_MAX_TOKENS = _chat_cfg.get("clamped_max_tokens", 4096)
_DEFAULT_TEMPERATURE = _chat_cfg.get("default_temperature", 0.7)
_DEFAULT_MODEL = _chat_cfg.get("default_model", "gemini-1.5-pro")


class Message(BaseModel):
    role: str = Field(..., description="Role of the message sender ('user', 'assistant', 'system', 'tool')")
    content: str = Field(..., description="Text content of the message")
    name: Optional[str] = Field(None, description="Optional name for function calling association")
    tool_calls: Optional[List[Dict[str, Any]]] = None


class ChatRequest(BaseModel):
    # Clamped to settings.json max_messages_limit (default 50)
    messages: List[Message] = Field(..., max_length=_MAX_MESSAGES)
    # §8.4: Simple RAG context injection — text injected as extra system message
    document_context: Optional[str] = Field(None, description="Teks dokumen yang di-inject sebagai context tambahan (RAG sederhana)")
    # §8.4: Override system prompt — prepended before document_context
    system_prompt: Optional[str] = Field(None, description="Override system prompt")
    model: Optional[str] = _DEFAULT_MODEL
    temperature: Optional[float] = Field(_DEFAULT_TEMPERATURE, ge=0.0, le=2.0)
    # Clamped to settings.json clamped_max_tokens (default 4096)
    max_tokens: Optional[int] = Field(2048, le=_MAX_TOKENS)
    use_rag: Optional[bool] = False
    stream: Optional[bool] = False
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[str] = "auto"


class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatChoiceMessage(BaseModel):
    role: str = "assistant"
    content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None


class ChatChoice(BaseModel):
    index: int = 0
    message: ChatChoiceMessage
    finish_reason: str = "stop"  # 'stop', 'length', 'tool_calls'


class ChatResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatChoice]
    usage: Usage
    cost_usd: float = 0.000000
