"""Event CRUD + time-window report aggregation.

Membership of an event is decided by timestamps (registration time, score
changes, game-play time), never by a stored foreign key. This keeps the feature
additive and safe: no existing table is altered.
"""

from datetime import datetime, timezone

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.event import Event
from app.models.room import PlayerAnswer, Room, RoomPlayer
from app.models.score import Score
from app.models.user import User

GAME_FIELDS = ["game1_score", "game2_score", "game3_score", "game4_score", "game5_score"]


def _utc_naive(dt: datetime) -> datetime:
    """Normalise to naive UTC so comparisons match server_default=func.now()."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.replace(tzinfo=None)


def create_event(db: Session, data) -> Event:
    event = Event(
        name=data.name,
        description=data.description,
        start_at=_utc_naive(data.start_at),
        end_at=_utc_naive(data.end_at),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def get_events(db: Session) -> list[Event]:
    return db.query(Event).order_by(Event.start_at.desc()).all()


def get_event(db: Session, event_id: int) -> Event | None:
    return db.query(Event).filter(Event.id == event_id).first()


def get_current_event(db: Session) -> Event | None:
    """The single event currently marked active (at most one)."""
    return db.query(Event).filter(Event.is_current.is_(True)).first()


def set_current_event(db: Session, event_id: int) -> Event | None:
    """Mark one event as current, clearing the flag on every other event."""
    event = db.get(Event, event_id)
    if event is None:
        return None
    db.query(Event).filter(Event.id != event_id).update({Event.is_current: False})
    event.is_current = True
    db.commit()
    db.refresh(event)
    return event


def user_in_event_filter(event: Event | None):
    """Return a SQLAlchemy expression for 'user belongs to this event'.

    Returns None when there is no current event, so callers can skip filtering
    and keep the pre-event behaviour (show everything) for backward compatibility.
    """
    if event is None:
        return None
    return (User.created_at >= event.start_at) & (User.created_at <= event.end_at)


def delete_event(db: Session, event: Event) -> None:
    db.delete(event)
    db.commit()


def build_report(db: Session, event: Event) -> dict:
    start, end = event.start_at, event.end_at
    in_window = (User.created_at >= start) & (User.created_at <= end)

    total = db.query(func.count(User.id)).filter(in_window).scalar() or 0

    countries = [
        {"region": region or "Unknown", "count": int(count)}
        for region, count in db.query(User.region, func.count(User.id))
        .filter(in_window)
        .group_by(User.region)
        .order_by(func.count(User.id).desc())
        .all()
    ]

    per_day = [
        {"date": str(day), "count": int(count)}
        for day, count in db.query(func.date(User.created_at), func.count(User.id))
        .filter(in_window)
        .group_by(func.date(User.created_at))
        .order_by(func.date(User.created_at))
        .all()
    ]

    active = (
        db.query(func.count(Score.user_id))
        .join(User, User.id == Score.user_id)
        .filter(in_window)
        .filter(or_(*[getattr(Score, field) > 0 for field in GAME_FIELDS]))
        .scalar()
        or 0
    )

    top_players = [
        {
            "nickname": nickname or "",
            "firstname": firstname,
            "lastname": lastname,
            "region": region or "",
            "total_score": float(total_score or 0),
        }
        for nickname, firstname, lastname, region, total_score in (
            db.query(
                User.nickname, User.firstname, User.lastname, User.region,
                Score.total_score,
            )
            .join(Score, Score.user_id == User.id)
            .filter(in_window)
            .order_by(Score.total_score.desc())
            .limit(10)
            .all()
        )
    ]

    games = {}
    for i, field in enumerate(GAME_FIELDS, start=1):
        players, avg, best = (
            db.query(
                func.count(Score.user_id),
                func.avg(getattr(Score, field)),
                func.max(getattr(Score, field)),
            )
            .join(User, User.id == Score.user_id)
            .filter(in_window)
            .filter(getattr(Score, field) > 0)
            .one()
        )
        games[f"game{i}"] = {
            "players": int(players or 0),
            "avg": round(float(avg or 0), 1),
            "max": float(best or 0),
        }

    showdown = {
        "rooms": int(
            db.query(func.count(Room.id))
            .filter(Room.created_at >= start, Room.created_at <= end)
            .scalar()
            or 0
        ),
        "players": int(
            db.query(func.count(func.distinct(RoomPlayer.user_id)))
            .filter(RoomPlayer.joined_at >= start, RoomPlayer.joined_at <= end)
            .scalar()
            or 0
        ),
        "answers": int(
            db.query(func.count(PlayerAnswer.id))
            .filter(PlayerAnswer.created_at >= start, PlayerAnswer.created_at <= end)
            .scalar()
            or 0
        ),
    }

    return {
        "event": event,
        "total_participants": int(total),
        "country_count": len(countries),
        "countries": countries,
        "registrations_per_day": per_day,
        "active_players": int(active),
        "top_players": top_players,
        "games": games,
        "showdown": showdown,
    }
