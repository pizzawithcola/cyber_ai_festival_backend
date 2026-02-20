import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.services.llm_service import chat

logger = logging.getLogger(__name__)
router = APIRouter()


class Mission(BaseModel):
    title: str
    description: str
    targetLink: str
    difficulty: str
    hint: str


class TargetInformation(BaseModel):
    name: str
    email: str
    department: str
    position: str
    hobbies: list[str] = []
    personality: str
    mission: Mission


class ChatRequest(BaseModel):
    prompt: str
    model: str = "deepseek-chat"
    target_information: TargetInformation


class ChatResponse(BaseModel):
    reply: str


@router.post("/chat", response_model=ChatResponse)
def llm_chat(body: ChatRequest):
    if not settings.deepseek_api_key:
        logger.error("DeepSeek API key not configured")
        raise HTTPException(status_code=503, detail="DeepSeek API key not configured")

    logger.info(
        "LLM chat request: model=%s, target=%s, difficulty=%s",
        body.model, body.target_information.name, body.target_information.mission.difficulty,
    )
    reply = chat(
        body.prompt,
        model=body.model,
        target_info=body.target_information.model_dump(),
    )
    logger.info("LLM chat reply: len=%d", len(reply))
    return ChatResponse(reply=reply)
