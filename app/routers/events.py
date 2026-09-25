"""Event configuration + reporting endpoints.

Read-only reports derive membership from timestamps; nothing here mutates
user / score / room data.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.crud import event as crud
from app.database import get_db
from app.schemas.event import EventCreate, EventReport, EventResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/", response_model=EventResponse)
def create_event(data: EventCreate, db: Session = Depends(get_db)):
    event = crud.create_event(db, data)
    logger.info("Event created: id=%s name=%s", event.id, event.name)
    return event


@router.get("/", response_model=list[EventResponse])
def list_events(db: Session = Depends(get_db)):
    return crud.get_events(db)


@router.get("/{event_id}/report", response_model=EventReport)
def get_event_report(event_id: int, db: Session = Depends(get_db)):
    event = crud.get_event(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return crud.build_report(db, event)


@router.delete("/{event_id}")
def delete_event(event_id: int, db: Session = Depends(get_db)):
    event = crud.get_event(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    crud.delete_event(db, event)
    logger.info("Event deleted: id=%s", event_id)
    return {"message": "Event deleted", "event_id": event_id}
