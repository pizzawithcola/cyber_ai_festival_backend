import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.crud import user as crud
from app.database import get_db
from app.models.user import User
from app.models.score import Score
from app.schemas.user import UserLogin, UserCreate, UserUpdate, UserResponse, UserScoreResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/login", response_model=UserResponse)
def login(data: UserLogin, db: Session = Depends(get_db)):
    user = crud.get_user_by_email(db, data.email)
    if not user:
        logger.warning("Login failed: email not found (%s)", data.email)
        raise HTTPException(status_code=401, detail="Invalid email or firstname")
    if user.firstname.lower() != data.firstname.lower():
        logger.warning("Login failed: firstname mismatch for email=%s", data.email)
        raise HTTPException(status_code=401, detail="Invalid email or firstname")
    logger.info("Login success: id=%s, email=%s", user.id, user.email)
    return user


@router.post("/", response_model=UserResponse)
def create_user(data: UserCreate, db: Session = Depends(get_db)):
    existing = crud.get_user_by_email(db, data.email)
    if existing:
        logger.warning("User already exists: email=%s, id=%s", data.email, existing.id)
        raise HTTPException(
            status_code=409,
            detail={"message": "User with this email already exists", "user_id": existing.id},
        )
    logger.info("Creating user: %s %s (%s)", data.firstname, data.lastname, data.email)
    user = crud.create_user(db, data)
    logger.info("User created: id=%s", user.id)
    return user


@router.get("/userscores", response_model=list[UserScoreResponse])
def get_all_users_with_scores(db: Session = Depends(get_db)):
    """
    Get all users with their scores.
    Returns user information along with scores for all 5 games and total score.
    In 1:1 relationship, each user has exactly one score record.
    """
    # Join User and Score tables to get users with their scores
    query = db.query(
        User.id,
        User.firstname,
        User.lastname,
        User.email,
        User.region,
        Score.user_id.label('score_id'),
        Score.game1_score,
        Score.game2_score,
        Score.game3_score,
        Score.game4_score,
        Score.game5_score,
        Score.total_score
    ).outerjoin(Score, User.id == Score.user_id)
    
    results = query.all()
    
    # Convert to response format
    user_scores = []
    for row in results:
        user_scores.append(UserScoreResponse(
            id=row.id,
            firstname=row.firstname,
            lastname=row.lastname,
            email=row.email,
            region=row.region,
            score_id=row.score_id,
            game1_score=row.game1_score if row.game1_score is not None else 0,
            game2_score=row.game2_score if row.game2_score is not None else 0,
            game3_score=row.game3_score if row.game3_score is not None else 0,
            game4_score=row.game4_score if row.game4_score is not None else 0,
            game5_score=row.game5_score if row.game5_score is not None else 0,
            total_score=row.total_score if row.total_score is not None else 0
        ))
    
    return user_scores


@router.get("/{user_id}", response_model=UserResponse)
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = crud.get_user(db, user_id)
    if not user:
        logger.warning("User not found: id=%s", user_id)
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.put("/{user_id}", response_model=UserResponse)
def update_user(user_id: int, data: UserUpdate, db: Session = Depends(get_db)):
    user = crud.get_user(db, user_id)
    if not user:
        logger.warning("User not found for update: id=%s", user_id)
        raise HTTPException(status_code=404, detail="User not found")
    if data.email and data.email != user.email:
        existing = crud.get_user_by_email(db, data.email)
        if existing:
            logger.warning("Email already taken: %s (by user id=%s)", data.email, existing.id)
            raise HTTPException(
                status_code=409,
                detail={"message": "Email already taken", "user_id": existing.id},
            )
    logger.info("Updating user: id=%s", user_id)
    user = crud.update_user(db, user, data)
    logger.info("User updated: id=%s", user.id)
    return user


@router.delete("/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db)):
    user = crud.get_user(db, user_id)
    if not user:
        logger.warning("User not found for delete: id=%s", user_id)
        raise HTTPException(status_code=404, detail="User not found")
    crud.delete_user(db, user)
    logger.info("User deleted: id=%s", user_id)
    return {"message": "User deleted", "user_id": user_id}


@router.get("/", response_model=list[UserResponse])
def list_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_users(db, skip=skip, limit=limit)
