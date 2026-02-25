from sqlalchemy.orm import Session

from app.models.score import Score
from app.schemas.score import ScoreCreate, ScoreUpdate


def create_score(db: Session, data: ScoreCreate) -> Score:
    # Check if score already exists for this user (1:1 relationship)
    existing_score = get_score_by_user(db, data.user_id)
    if existing_score:
        raise ValueError(f"Score already exists for user_id={data.user_id}")
    
    score = Score(
        user_id=data.user_id,
        game1_score=data.game1_score or 0,
        game2_score=data.game2_score or 0,
        game3_score=data.game3_score or 0,
        game4_score=data.game4_score or 0,
        game5_score=data.game5_score or 0,
        total_score=data.total_score or 0,
    )
    db.add(score)
    db.commit()
    db.refresh(score)
    return score


def get_scores_by_user(db: Session, user_id: int, skip: int = 0, limit: int = 100) -> list[Score]:
    return db.query(Score).filter(Score.user_id == user_id).offset(skip).limit(limit).all()


def get_score_by_user(db: Session, user_id: int) -> Score | None:
    return db.query(Score).filter(Score.user_id == user_id).first()


def get_score(db: Session, score_id: int) -> Score | None:
    # In 1:1 relationship, score_id is the same as user_id
    return db.query(Score).filter(Score.user_id == score_id).first()


def update_score(db: Session, score: Score, data: ScoreUpdate) -> Score:
    update_data = data.model_dump(exclude_unset=True)
    
    # Check if total_score is explicitly being updated
    total_score_explicitly_updated = 'total_score' in update_data
    
    # Update individual fields first
    for field, value in update_data.items():
        # Ensure None values are converted to 0 for non-nullable fields
        if value is None and field in ['game1_score', 'game2_score', 'game3_score', 'game4_score', 'game5_score', 'total_score']:
            setattr(score, field, 0)
        else:
            setattr(score, field, value)
    
    # Auto-calculate total_score if:
    # 1. Any game scores were updated, AND
    # 2. total_score was NOT explicitly updated in this request
    game_fields_updated = any(field in update_data for field in ['game1_score', 'game2_score', 'game3_score', 'game4_score', 'game5_score'])
    if game_fields_updated and not total_score_explicitly_updated:
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
