from datetime import datetime
from pydantic import BaseModel


class ScoreCreate(BaseModel):
    user_id: int
    game1_score: float | None = 0
    game2_score: float | None = 0
    game3_score: float | None = 0
    game4_score: float | None = 0
    game5_score: float | None = 0
    total_score: float | None = 0


class ScoreUpdate(BaseModel):
    game1_score: float | None = None
    game2_score: float | None = None
    game3_score: float | None = None
    game4_score: float | None = None
    game5_score: float | None = None
    total_score: float | None = None


class ScoreResponse(BaseModel):
    id: int
    user_id: int
    game1_score: float | None
    game2_score: float | None
    game3_score: float | None
    game4_score: float | None
    game5_score: float | None
    total_score: float | None
    created_at: datetime

    model_config = {"from_attributes": True}
