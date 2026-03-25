from sqlalchemy.orm import Session

from app.models.score import Score
from app.schemas.score import ScoreCreate, ScoreUpdate


def create_score(db: Session, data: ScoreCreate) -> Score:
    # Check if score already exists for this user (1:1 relationship)
    existing_score = get_score_by_user(db, data.user_id)
    if existing_score:
        raise ValueError(f"Score already exists for user_id={data.user_id}")
    
    # Auto-calculate total_score from game scores
    game1 = data.game1_score or 0
    game2 = data.game2_score or 0
    game3 = data.game3_score or 0
    game4 = data.game4_score or 0
    game5 = data.game5_score or 0
    
    score = Score(
        user_id=data.user_id,
        game1_score=game1,
        game2_score=game2,
        game3_score=game3,
        game4_score=game4,
        game5_score=game5,
        total_score=game1 + game2 + game3 + game4 + game5,
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
    
    # Update individual game score fields
    for field, value in update_data.items():
        # Ensure None values are converted to 0 for non-nullable fields
        if value is None and field in ['game1_score', 'game2_score', 'game3_score', 'game4_score', 'game5_score']:
            setattr(score, field, 0)
        else:
            setattr(score, field, value)
    
    # Always auto-calculate total_score from game scores
    score.total_score = (
        (score.game1_score or 0) +
        (score.game2_score or 0) +
        (score.game3_score or 0) +
        (score.game4_score or 0) +
        (score.game5_score or 0)
    )
    
    db.commit()
    db.refresh(score)
    return score
