from sqlalchemy import Column, Integer, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Score(Base):
    __tablename__ = "scores"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True)
    game1_score = Column(Float, nullable=False, default=0)
    game2_score = Column(Float, nullable=False, default=0)
    game3_score = Column(Float, nullable=False, default=0)
    game4_score = Column(Float, nullable=False, default=0)
    game5_score = Column(Float, nullable=False, default=0)
    total_score = Column(Float, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="score")
