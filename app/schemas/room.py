from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ─── Question ──────────────────────────────────────────────────────────────────
class OptionItem(BaseModel):
    id: str  # A/B/C/D
    label: str
    color: str  # theme color name: red/cyan/yellow/lime
    icon: str   # ▲ ◆ ● ■


class QuestionResponse(BaseModel):
    id: int
    text: str
    options: list[OptionItem]
    time_limit: int
    number: int
    total: int

    class Config:
        from_attributes = True


# ─── Room ──────────────────────────────────────────────────────────────────────
class CreateRoomRequest(BaseModel):
    question_count: int = Field(default=10, ge=1, le=30)
    # Per-category question balance, e.g. {"phishing": 2, "ai": 2}. Empty/None = random from all.
    balance: dict[str, int] | None = None


class CreateRoomResponse(BaseModel):
    room_code: str
    admin_id: int


class PlayerInfo(BaseModel):
    id: int
    user_id: int
    player_name: str
    total_score: int
    streak: int

    class Config:
        from_attributes = True


class RoomStatusResponse(BaseModel):
    room_code: str
    status: str
    player_count: int
    players: list[PlayerInfo]


class JoinRoomRequest(BaseModel):
    user_id: int
    player_name: str


class JoinRoomResponse(BaseModel):
    player_id: int
    room_code: str
    player_count: int

    class Config:
        from_attributes = True


# ─── WebSocket Messages ────────────────────────────────────────────────────────
class WsIncoming(BaseModel):
    type: str  # start_game / submit_answer / ping


class WsStartGame(BaseModel):
    type: str = "start_game"
    question_count: int = 10


class WsSubmitAnswer(BaseModel):
    type: str = "submit_answer"
    question_id: int
    option: str  # A/B/C/D


# ─── Game Result ───────────────────────────────────────────────────────────────
class LeaderboardEntry(BaseModel):
    rank: int
    player_id: int
    player_name: str
    total_score: int
    streak: int


class RoomListItem(BaseModel):
    room_code: str
    status: str
    player_count: int
    question_count: int
    current_question: int
    created_at: str
    players: list[PlayerInfo] = []
