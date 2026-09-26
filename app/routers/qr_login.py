"""QR login: pair a game station's QR code with a player's phone.

Flow:
- A game station (the shared login page in QR mode) creates a long-lived station
  session and shows its code as a QR code.
- The player's phone (the /me panel) scans the code with its camera and submits
  the player's nickname.
- The station polls for the pairing, receives the player's identity and logs
  them in.

State is deliberately in-memory: the festival is a one-day event, stations run
on a single ECS task, and codes are reusable within the day, so a database table
would add moving parts without benefit. Station codes expire after STATION_TTL.
"""

import logging
import secrets
import string
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()

# Long-lived, reusable station codes (one per game station per day).
STATION_TTL = 24 * 3600
_stations: dict[str, float] = {}
# FIFO queue of paired players per station code (consumed by the station's poll).
_pending: dict[str, deque] = defaultdict(deque)

# No 0/O/1/I so a human never misreads a code.
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _prune_stale() -> None:
    now = time.time()
    for code in [c for c, ts in _stations.items() if now - ts > STATION_TTL]:
        _stations.pop(code, None)
        _pending.pop(code, None)


def _new_code() -> str:
    for _ in range(30):
        code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(6))
        if code not in _stations:
            return code
    raise HTTPException(status_code=500, detail="Failed to generate station code")


class SessionResponse(BaseModel):
    station_code: str


class PairRequest(BaseModel):
    station_code: str
    nickname: str


class PairResponse(BaseModel):
    ok: bool


class StatusResponse(BaseModel):
    ok: bool
    user: dict | None = None


@router.post("/session", response_model=SessionResponse)
def create_session() -> SessionResponse:
    """A station asks for a fresh, unique code to render as its QR code."""
    _prune_stale()
    code = _new_code()
    _stations[code] = time.time()
    logger.info("QR session created: code=%s", code)
    return SessionResponse(station_code=code)


@router.post("/pair", response_model=PairResponse)
def pair(data: PairRequest, db: Session = Depends(get_db)) -> PairResponse:
    """The phone submits {station_code, nickname} after scanning the QR code."""
    _prune_stale()
    code = (data.station_code or "").strip().upper()
    if code not in _stations:
        raise HTTPException(status_code=404, detail="Station not found")

    nickname = (data.nickname or "").strip()
    if not nickname:
        raise HTTPException(status_code=400, detail="Nickname is required")

    user = db.query(User).filter(User.nickname.ilike(nickname)).first()
    if not user:
        raise HTTPException(status_code=404, detail="Invalid nickname")

    snapshot = {
        "user_id": user.id,
        "nickname": user.nickname,
        "firstname": user.firstname,
        "lastname": user.lastname,
        "region": user.region,
    }
    _pending[code].append(snapshot)
    logger.info("QR pair: station=%s user_id=%s nickname=%s", code, user.id, user.nickname)
    return PairResponse(ok=True)


@router.get("/status/{station_code}", response_model=StatusResponse)
def status(station_code: str) -> StatusResponse:
    """The station polls this; each poll consumes the oldest waiting pairing."""
    _prune_stale()
    code = (station_code or "").strip().upper()
    if code not in _stations:
        raise HTTPException(status_code=404, detail="Station not found")

    queue = _pending.get(code)
    if queue:
        return StatusResponse(ok=True, user=queue.popleft())
    return StatusResponse(ok=False)
