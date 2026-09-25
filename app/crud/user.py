import re

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate


def initials_of(firstname: str, lastname: str | None) -> str:
    """Two-letter initials from the real name, e.g. "Jamie Liu" -> "JL".

    Falls back to the first two letters of whichever name part is present, and
    to "PL" when neither is usable.
    """
    first = re.sub(r"[^A-Za-z]", "", (firstname or "").strip())
    last = re.sub(r"[^A-Za-z]", "", (lastname or "").strip())
    if first and last:
        return (first[0] + last[0]).upper()
    if first:
        return first[:2].upper()
    if last:
        return last[:2].upper()
    return "PL"


def generate_nickname(db: Session, firstname: str, lastname: str | None) -> str:
    """Short, memorable nickname: initials + the smallest free number.

    Examples: "Jamie Liu" -> "JL1", "JL2", ...; a single name "Jamie" -> "JA1".
    The number is scoped per initials, so many players may share the same letters.
    """
    base = initials_of(firstname, lastname)
    used: set[int] = set()
    for (nick,) in db.query(User.nickname).filter(User.nickname.ilike(f"{base}%")).all():
        if not nick:
            continue
        suffix = nick[len(base):]
        if suffix.isdigit():
            used.add(int(suffix))
    number = 1
    while number in used:
        number += 1
    return f"{base}{number}"


def ensure_nickname(db: Session, user: User) -> User:
    """老用户登录时 nickname 为空则补生成（带唯一冲突重试）"""
    if user.nickname:
        return user
    for _ in range(10):
        candidate = generate_nickname(db, user.firstname, user.lastname)
        try:
            user.nickname = candidate
            db.commit()
            db.refresh(user)
            return user
        except Exception:
            db.rollback()
    # 极端并发兜底：带 user id 后缀
    user.nickname = f"{generate_nickname(db, user.firstname, user.lastname)}_{user.id}"
    db.commit()
    db.refresh(user)
    return user


def create_user(db: Session, data: UserCreate) -> User:
    nickname = generate_nickname(db, data.firstname, data.lastname)
    user = User(
        firstname=data.firstname,
        lastname=data.lastname,
        nickname=nickname,
        region=data.region,
    )
    db.add(user)
    db.flush()  # Get the user ID before committing
    
    # Create default score record for the user
    from app.models.score import Score
    score = Score(
        user_id=user.id,
        game1_score=0,
        game2_score=0,
        game3_score=0,
        game4_score=0,
        game5_score=0,
        total_score=0
    )
    db.add(score)
    
    db.commit()
    db.refresh(user)
    return user


def get_user(db: Session, user_id: int) -> User | None:
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_nickname(db: Session, nickname: str) -> User | None:
    """按昵称查找：trim + 大小写不敏感"""
    n = nickname.strip().lower()
    return db.query(User).filter(func.lower(User.nickname) == n).first()


def update_user(db: Session, user: User, data: UserUpdate) -> User:
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user


def delete_user(db: Session, user: User) -> None:
    db.delete(user)
    db.commit()


def get_users(db: Session, skip: int = 0, limit: int = 100) -> list[User]:
    return db.query(User).offset(skip).limit(limit).all()
