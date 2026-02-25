from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    firstname = Column(String(128), nullable=False)
    lastname = Column(String(128), nullable=False)
    email = Column(String(256), unique=True, index=True, nullable=False)
    region = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    score = relationship("Score", back_populates="user", uselist=False, cascade="all, delete-orphan")
