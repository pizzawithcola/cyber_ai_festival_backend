from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, index=True)
    text = Column(Text, nullable=False)
    option_a = Column(String(255), nullable=False)
    option_b = Column(String(255), nullable=False)
    option_c = Column(String(255), nullable=False)
    option_d = Column(String(255), nullable=False)
    correct_option = Column(String(1), nullable=False)  # A/B/C/D
    time_limit = Column(Integer, nullable=False, default=20)
    category = Column(String(64), nullable=True, default="general")


class Room(Base):
    __tablename__ = "rooms"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(4), unique=True, index=True, nullable=False)
    admin_id = Column(Integer, nullable=False)
    status = Column(String(16), nullable=False, default="waiting")  # waiting / playing / finished
    question_count = Column(Integer, nullable=False, default=10)
    current_question_index = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    players = relationship("RoomPlayer", back_populates="room", cascade="all, delete-orphan")


class RoomPlayer(Base):
    __tablename__ = "room_players"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False)
    user_id = Column(Integer, nullable=False)
    player_name = Column(String(128), nullable=False)
    total_score = Column(Integer, nullable=False, default=0)
    streak = Column(Integer, nullable=False, default=0)
    joined_at = Column(DateTime(timezone=True), server_default=func.now())

    room = relationship("Room", back_populates="players")
    answers = relationship("PlayerAnswer", back_populates="player", cascade="all, delete-orphan")


class PlayerAnswer(Base):
    __tablename__ = "player_answers"

    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("room_players.id"), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    chosen_option = Column(String(1), nullable=False)
    is_correct = Column(Boolean, nullable=False)
    answer_time_ms = Column(Integer, nullable=False)
    score_earned = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    player = relationship("RoomPlayer", back_populates="answers")
