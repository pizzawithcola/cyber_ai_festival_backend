from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base


class Event(Base):
    """An event is a pure time-window definition (venue / festival period).

    It deliberately has NO foreign key to any business table: membership is
    derived at query time by comparing timestamps, so creating, editing or
    deleting an event never mutates user / score / room data.
    """

    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    start_at = Column(DateTime(timezone=True), nullable=False)
    end_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
