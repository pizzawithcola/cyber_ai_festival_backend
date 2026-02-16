from sqlalchemy.orm import Session

from app.models.score import Score
from app.schemas.score import ScoreCreate, ScoreUpdate


def create_score(db: Session, data: ScoreCreate) -> Score:
    score = Score(
        user_id=data.user_id,
        game1_score=data.game1_score,
        game2_score=data.game2_score,
        game3_score=data.game3_score,
        game4_score=data.game4_score,
        game5_score=data.game5_score,
        total_score=data.total_score,
    )
    db.add(score)
    db.commit()
    db.refresh(score)
    return score


def get_scores_by_user(db: Session, user_id: int, skip: int = 0, limit: int = 100) -> list[Score]:
    return db.query(Score).filter(Score.user_id == user_id).offset(skip).limit(limit).all()


def get_score(db: Session, score_id: int) -> Score | None:
    return db.query(Score).filter(Score.id == score_id).first()


def update_score(db: Session, score: Score, data: ScoreUpdate) -> Score:
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(score, field, value)
    db.commit()
    db.refresh(score)
    return score
