from datetime import datetime
from pydantic import BaseModel


class ScoreCreate(BaseModel):
    user_id: int
    game1_score: float = 0
    game2_score: float = 0
    game3_score: float = 0
    game4_score: float = 0
    game5_score: float = 0
    # total_score is auto-calculated from game scores, not user-provided


class ScoreUpdate(BaseModel):
    game1_score: float | None = None
    game2_score: float | None = None
    game3_score: float | None = None
    game4_score: float | None = None
    game5_score: float | None = None
    # total_score is auto-calculated, not updatable


class ScoreResponse(BaseModel):
    user_id: int
    game1_score: float
    game2_score: float
    game3_score: float
    game4_score: float
    game5_score: float
    total_score: float  # Auto-calculated from game scores
    created_at: datetime

    model_config = {"from_attributes": True}
