import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.services.llm_service import chat

logger = logging.getLogger(__name__)
router = APIRouter()


class ChatRequest(BaseModel):
    prompt: str
    model: str = "deepseek-chat"


class ChatResponse(BaseModel):
    reply: str


@router.post("/chat", response_model=ChatResponse)
def llm_chat(body: ChatRequest):
    if not settings.deepseek_api_key:
        logger.error("DeepSeek API key not configured")
        raise HTTPException(status_code=503, detail="DeepSeek API key not configured")
    logger.info("LLM chat request: model=%s, prompt_len=%d", body.model, len(body.prompt))
    reply = chat(body.prompt, model=body.model)
    logger.info("LLM chat reply: len=%d", len(reply))
    return ChatResponse(reply=reply)
