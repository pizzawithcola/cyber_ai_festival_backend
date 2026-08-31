from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate


def generate_nickname(db: Session, firstname: str, lastname: str | None) -> str:
    """
    生成唯一昵称：名字全拼 + 姓氏首字母大写，后缀 _NNN 按同名累加。
    例："Jamie Liu" → "JamieL_001"；下一个同名（Jamie/姓氏L开头）→ "JamieL_002"。
    """
    first = (firstname or "").strip()
    last = (lastname or "").strip()
    base = first + (last[0].upper() if last else "")
    if not base:
        base = "Player"

    # 已有同名基数：既可能存的是 base（旧数据），也可能是 base_xxx
    prefix = f"{base}_"
    existing = db.query(User).filter(
        (User.nickname == base) | User.nickname.like(f"{prefix}%")
    ).count()
    return f"{base}_{existing + 1:03d}"


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
        email=data.email,
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


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email).first()


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
