from datetime import datetime
from pydantic import BaseModel


class ScoreCreate(BaseModel):
    user_id: int
    game1_score: float = 0
    game2_score: float = 0
    game3_score: float = 0
    game4_score: float = 0
    game5_score: float = 0
    total_score: float = 0


class ScoreUpdate(BaseModel):
    game1_score: float | None = None
    game2_score: float | None = None
    game3_score: float | None = None
    game4_score: float | None = None
    game5_score: float | None = None
    total_score: float | None = None


class ScoreResponse(BaseModel):
    user_id: int
    game1_score: float
    game2_score: float
    game3_score: float
    game4_score: float
    game5_score: float
    total_score: float
    created_at: datetime

    model_config = {"from_attributes": True}
