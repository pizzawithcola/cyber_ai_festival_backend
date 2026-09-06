from sqlalchemy.orm import Session

from app.models.score import Score
from app.schemas.score import ScoreCreate, ScoreUpdate

# Per-game score range (all games normalize to 0-100 on the leaderboard).
GAME_FIELDS = ["game1_score", "game2_score", "game3_score", "game4_score", "game5_score"]
SCORE_MIN = 0
SCORE_MAX = 100


def _clamp(value) -> float:
    """Server-side range guard: reject NaN and clamp every game score to 0-100."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        v = 0.0
    if v != v:  # NaN
        return 0.0
    return max(SCORE_MIN, min(SCORE_MAX, v))


def create_score(db: Session, data: ScoreCreate) -> Score:
    # Check if score already exists for this user (1:1 relationship)
    existing_score = get_score_by_user(db, data.user_id)
    if existing_score:
        raise ValueError(f"Score already exists for user_id={data.user_id}")

    # Auto-calculate total_score from clamped game scores
    games = {f: _clamp(getattr(data, f)) for f in GAME_FIELDS}

    score = Score(
        user_id=data.user_id,
        **games,
        total_score=sum(games.values()),
    )
    db.add(score)
    db.commit()
    db.refresh(score)
    return score


def get_score(db: Session, score_id: int) -> Score | None:
    # In 1:1 relationship, score_id is the same as user_id
    return db.query(Score).filter(Score.user_id == score_id).first()


def get_score_by_user(db: Session, user_id: int) -> Score | None:
    """Alias for get_score - kept for backwards compatibility"""
    return get_score(db, user_id)


def update_score(db: Session, score: Score, data: ScoreUpdate) -> Score:
    update_data = data.model_dump(exclude_unset=True)

    # Update individual game score fields (clamped server-side)
    for field, value in update_data.items():
        if field in GAME_FIELDS:
            setattr(score, field, _clamp(value))
        else:
            setattr(score, field, value)

    # Always auto-calculate total_score from game scores
    score.total_score = sum(
        _clamp(getattr(score, f) if getattr(score, f) is not None else 0) for f in GAME_FIELDS
    )

    db.commit()
    db.refresh(score)
    return score
