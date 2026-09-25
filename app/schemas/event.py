from datetime import datetime

from pydantic import BaseModel


class EventCreate(BaseModel):
    name: str
    description: str | None = None
    start_at: datetime
    end_at: datetime


class EventResponse(BaseModel):
    id: int
    name: str
    description: str | None = None
    start_at: datetime
    end_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class CountryStat(BaseModel):
    region: str
    count: int


class DayStat(BaseModel):
    date: str
    count: int


class TopPlayer(BaseModel):
    nickname: str
    firstname: str
    lastname: str
    region: str
    total_score: float


class GameStat(BaseModel):
    players: int
    avg: float
    max: float


class ShowdownStat(BaseModel):
    rooms: int
    players: int
    answers: int


class EventReport(BaseModel):
    event: EventResponse
    total_participants: int
    country_count: int
    countries: list[CountryStat]
    registrations_per_day: list[DayStat]
    active_players: int
    top_players: list[TopPlayer]
    games: dict[str, GameStat]
    showdown: ShowdownStat
