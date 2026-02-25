from datetime import datetime
from pydantic import BaseModel


class UserLogin(BaseModel):
    email: str
    firstname: str


class UserCreate(BaseModel):
    firstname: str
    lastname: str
    email: str
    region: str | None = None


class UserUpdate(BaseModel):
    firstname: str | None = None
    lastname: str | None = None
    email: str | None = None
    region: str | None = None


class UserResponse(BaseModel):
    id: int
    firstname: str
    lastname: str
    email: str
    region: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class UserScoreResponse(BaseModel):
    id: int
    firstname: str
    lastname: str
    email: str
    region: str | None
    score_id: int | None
    game1_score: float | None
    game2_score: float | None
    game3_score: float | None
    game4_score: float | None
    game5_score: float | None
    total_score: float | None

    model_config = {"from_attributes": True}
