import logging
import random
import string

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.room import Room, RoomPlayer, Question
from app.schemas.room import (
    CreateRoomRequest,
    CreateRoomResponse,
    RoomStatusResponse,
    JoinRoomRequest,
    JoinRoomResponse,
    PlayerInfo,
    RoomListItem,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _generate_room_code(db: Session) -> str:
    """Generate a unique 4-digit room code."""
    for _ in range(30):
        code = "".join(random.choices(string.digits, k=4))
        if not db.query(Room).filter(Room.code == code).first():
            return code
    raise HTTPException(status_code=500, detail="Failed to generate room code")


# ─── Create / Join / Status ────────────────────────────────────────────────
@router.post("/", response_model=CreateRoomResponse)
def create_room(data: CreateRoomRequest, db: Session = Depends(get_db)):
    """Admin creates a new game room. Returns a 4-digit room code."""
    code = _generate_room_code(db)
    room = Room(code=code, admin_id=1, status="waiting", question_count=data.question_count)
    db.add(room)
    db.commit()
    db.refresh(room)
    logger.info("Room created: code=%s, question_count=%d", code, data.question_count)
    return CreateRoomResponse(room_code=code, admin_id=room.admin_id)


@router.get("/", response_model=list[RoomListItem])
def list_rooms(db: Session = Depends(get_db)):
    """List all rooms with player details and scores."""
    rooms = db.query(Room).order_by(Room.created_at.desc()).all()
    result = []
    for room in rooms:
        players = [
            PlayerInfo(
                id=p.id,
                user_id=p.user_id,
                player_name=p.player_name,
                total_score=p.total_score,
                streak=p.streak,
            )
            for p in sorted(room.players, key=lambda x: x.total_score, reverse=True)
        ]
        result.append(RoomListItem(
            room_code=room.code,
            status=room.status,
            player_count=len(players),
            question_count=room.question_count,
            current_question=room.current_question_index,
            created_at=room.created_at.isoformat() if room.created_at else "",
            players=players,
        ))
    return result


@router.get("/{code}/status", response_model=RoomStatusResponse)
def get_room_status(code: str, db: Session = Depends(get_db)):
    """Get room status and player list."""
    room = db.query(Room).filter(Room.code == code).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    players = [
        PlayerInfo(
            id=p.id, user_id=p.user_id, player_name=p.player_name,
            total_score=p.total_score, streak=p.streak,
        )
        for p in room.players
    ]
    return RoomStatusResponse(
        room_code=room.code, status=room.status,
        player_count=len(players), players=players,
    )


@router.post("/{code}/join", response_model=JoinRoomResponse)
def join_room(code: str, data: JoinRoomRequest, db: Session = Depends(get_db)):
    """Player joins a room by code."""
    room = db.query(Room).filter(Room.code == code).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if room.status not in ("waiting", "paused"):
        raise HTTPException(status_code=400, detail="Game already started or finished")

    existing = (
        db.query(RoomPlayer)
        .filter(RoomPlayer.room_id == room.id, RoomPlayer.user_id == data.user_id)
        .first()
    )
    if existing:
        return JoinRoomResponse(
            player_id=existing.id, room_code=code,
            player_count=len(room.players),
        )

    player = RoomPlayer(room_id=room.id, user_id=data.user_id, player_name=data.player_name)
    db.add(player)
    db.commit()
    db.refresh(player)
    logger.info("Player joined room %s: user_id=%s, name=%s", code, data.user_id, data.player_name)
    return JoinRoomResponse(
        player_id=player.id, room_code=code,
        player_count=len(room.players),
    )


# ─── Admin Control ─────────────────────────────────────────────────────────
@router.post("/{code}/pause")
def pause_room(code: str, db: Session = Depends(get_db)):
    """Pause a game room (admin only)."""
    room = db.query(Room).filter(Room.code == code).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if room.status != "playing":
        raise HTTPException(status_code=400, detail="Can only pause a playing game")
    from app.websocket.game import sessions
    session = sessions.get(code)
    if session:
        session.pause()
    room.status = "paused"
    db.commit()
    logger.info("Room %s paused", code)
    return {"status": "paused", "room_code": code}


@router.post("/{code}/resume")
def resume_room(code: str, db: Session = Depends(get_db)):
    """Resume a paused game room (admin only)."""
    room = db.query(Room).filter(Room.code == code).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if room.status != "paused":
        raise HTTPException(status_code=400, detail="Can only resume a paused game")
    from app.websocket.game import sessions
    session = sessions.get(code)
    if session:
        session.resume()
    room.status = "playing"
    db.commit()
    logger.info("Room %s resumed", code)
    return {"status": "playing", "room_code": code}


@router.post("/{code}/end")
def end_room(code: str, db: Session = Depends(get_db)):
    """Force-end a game room (admin only)."""
    room = db.query(Room).filter(Room.code == code).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if room.status == "finished":
        raise HTTPException(status_code=400, detail="Game already finished")
    from app.websocket.game import sessions
    session = sessions.get(code)
    if session:
        session.force_end()
    room.status = "finished"
    db.commit()
    logger.info("Room %s force-ended by admin", code)
    return {"status": "finished", "room_code": code}


@router.get("/questions/count")
def get_question_count(db: Session = Depends(get_db)):
    """Get total number of questions in the bank."""
    count = db.query(Question).count()
    return {"count": count}
