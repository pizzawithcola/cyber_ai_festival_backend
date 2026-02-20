import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.crud import user as crud
from app.database import get_db
from app.schemas.user import UserLogin, UserCreate, UserUpdate, UserResponse

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
