import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.crud import score as crud
from app.database import get_db
from app.schemas.score import ScoreCreate, ScoreUpdate, ScoreResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/", response_model=ScoreResponse)
def create_score(data: ScoreCreate, db: Session = Depends(get_db)):
    logger.info("Creating score for user_id=%s", data.user_id)
    try:
        score = crud.create_score(db, data)
        logger.info("Score created: user_id=%s, total=%.1f", score.user_id, score.total_score)
        return score
    except ValueError as e:
        logger.warning("Score creation failed: %s", str(e))
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/{user_id}", response_model=ScoreResponse)
def get_score(user_id: int, db: Session = Depends(get_db)):
    score = crud.get_score(db, user_id)
    if not score:
        logger.warning("Score not found: user_id=%s", user_id)
        raise HTTPException(status_code=404, detail="Score not found")
    return score


@router.put("/{user_id}", response_model=ScoreResponse)
def update_score(user_id: int, data: ScoreUpdate, db: Session = Depends(get_db)):
    score = crud.get_score(db, user_id)
    if not score:
        logger.warning("Score not found for update: user_id=%s", user_id)
        raise HTTPException(status_code=404, detail="Score not found")
    logger.info("Updating score: user_id=%s", user_id)
    score = crud.update_score(db, score, data)
    logger.info("Score updated: user_id=%s, total=%.1f", score.user_id, score.total_score or 0)
    return score
