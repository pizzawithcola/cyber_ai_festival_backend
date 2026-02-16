import logging
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.score import Score
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()


# --------------- 可排名的分数类型 ---------------
class ScoreType(str, Enum):
    game1 = "game1"
    game2 = "game2"
    game3 = "game3"
    game4 = "game4"
    game5 = "game5"
    total = "total"


# 映射到数据库列
SCORE_COLUMN_MAP = {
    ScoreType.game1: Score.game1_score,
    ScoreType.game2: Score.game2_score,
    ScoreType.game3: Score.game3_score,
    ScoreType.game4: Score.game4_score,
    ScoreType.game5: Score.game5_score,
    ScoreType.total: Score.total_score,
}


# --------------- 响应 Schema ---------------
class RankingEntry(BaseModel):
    rank: int
    user_id: int
    firstname: str
    lastname: str
    email: str
    region: str | None
    score: float

    model_config = {"from_attributes": True}


class RankingResponse(BaseModel):
    score_type: str
    total_entries: int
    rankings: list[RankingEntry]


# --------------- API ---------------
@router.get("/{score_type}", response_model=RankingResponse)
def get_ranking(
    score_type: ScoreType,
    limit: int = Query(default=50, ge=1, le=500, description="返回前 N 名"),
    db: Session = Depends(get_db),
):
    """获取指定分数类型的排行榜"""
    column = SCORE_COLUMN_MAP[score_type]

    rows = (
        db.query(Score, User)
        .join(User, Score.user_id == User.id)
        .filter(column.isnot(None))
        .order_by(desc(column))
        .limit(limit)
        .all()
    )

    rankings = [
        RankingEntry(
            rank=idx + 1,
            user_id=user.id,
            firstname=user.firstname,
            lastname=user.lastname,
            email=user.email,
            region=user.region,
            score=getattr(score, f"{score_type.value}_score" if score_type != ScoreType.total else "total_score") or 0,
        )
        for idx, (score, user) in enumerate(rows)
    ]

    logger.info("Ranking requested: type=%s, entries=%d", score_type.value, len(rankings))
    return RankingResponse(
        score_type=score_type.value,
        total_entries=len(rankings),
        rankings=rankings,
    )


@router.get("/", response_model=dict[str, RankingResponse])
def get_all_rankings(
    limit: int = Query(default=50, ge=1, le=500, description="每个排行榜返回前 N 名"),
    db: Session = Depends(get_db),
):
    """一次获取所有排行榜（game1~game5 + total）"""
    result = {}
    for score_type in ScoreType:
        column = SCORE_COLUMN_MAP[score_type]
        rows = (
            db.query(Score, User)
            .join(User, Score.user_id == User.id)
            .filter(column.isnot(None))
            .order_by(desc(column))
            .limit(limit)
            .all()
        )
        col_name = f"{score_type.value}_score" if score_type != ScoreType.total else "total_score"
        rankings = [
            RankingEntry(
                rank=idx + 1,
                user_id=user.id,
                firstname=user.firstname,
                lastname=user.lastname,
                email=user.email,
                region=user.region,
                score=getattr(score, col_name) or 0,
            )
            for idx, (score, user) in enumerate(rows)
        ]
        result[score_type.value] = RankingResponse(
            score_type=score_type.value,
            total_entries=len(rankings),
            rankings=rankings,
        )

    logger.info("All rankings requested, limit=%d", limit)
    return result
