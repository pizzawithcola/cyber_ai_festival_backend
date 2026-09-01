"""
Question bank CRUD endpoints for Ultimate Showdown.

All endpoints are protected by the shared X-API-Key auth (registered in main.py).
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.room import Question
from app.schemas.question import QuestionCreate, QuestionUpdate, QuestionResponse

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_question(db: Session, question_id: int) -> Question:
    question = db.query(Question).filter(Question.id == question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    return question


@router.get("/", response_model=list[QuestionResponse])
def list_questions(
    skip: int = 0,
    limit: int = 500,
    db: Session = Depends(get_db),
):
    """List all questions in the bank (ordered by id)."""
    questions = (
        db.query(Question)
        .order_by(Question.id)
        .offset(skip)
        .limit(limit)
        .all()
    )
    logger.info("Questions listed: count=%d", len(questions))
    return questions


@router.get("/{question_id}", response_model=QuestionResponse)
def get_question(question_id: int, db: Session = Depends(get_db)):
    """Get a single question by id."""
    return _get_question(db, question_id)


@router.post("/", response_model=QuestionResponse)
def create_question(data: QuestionCreate, db: Session = Depends(get_db)):
    """Create a new question."""
    question = Question(
        text=data.text,
        option_a=data.option_a,
        option_b=data.option_b,
        option_c=data.option_c,
        option_d=data.option_d,
        correct_option=data.correct_option.upper(),
        time_limit=data.time_limit,
        category=data.category or "general",
        score=data.score,
    )
    db.add(question)
    db.commit()
    db.refresh(question)
    logger.info("Question created: id=%s, category=%s", question.id, question.category)
    return question


@router.put("/{question_id}", response_model=QuestionResponse)
def update_question(question_id: int, data: QuestionUpdate, db: Session = Depends(get_db)):
    """Update an existing question (partial update supported)."""
    question = _get_question(db, question_id)
    update_data = data.model_dump(exclude_unset=True)
    if "correct_option" in update_data and update_data["correct_option"]:
        update_data["correct_option"] = update_data["correct_option"].upper()
    for field, value in update_data.items():
        setattr(question, field, value)
    db.commit()
    db.refresh(question)
    logger.info("Question updated: id=%s", question_id)
    return question


@router.delete("/{question_id}")
def delete_question(question_id: int, db: Session = Depends(get_db)):
    """Delete a question by id."""
    question = _get_question(db, question_id)
    db.delete(question)
    db.commit()
    logger.info("Question deleted: id=%s", question_id)
    return {"message": "Question deleted", "question_id": question_id}
