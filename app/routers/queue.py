"""Live queue information for the frontend.

The organiser deletes and recreates queues from the vendor dashboard, so a queue
id copied into the frontend goes stale and players end up on a dead board. The
frontend therefore asks for the current queue instead of hardcoding one; the
answer comes from the same resolution the registration path uses, so the board
link and the enrolment can never disagree.
"""

from fastapi import APIRouter, HTTPException

from app.services import queue_service

router = APIRouter()


@router.get("/")
def get_current_queue() -> dict:
    """Id, name and board URL of the newest queue.

    503 when the queue system cannot be reached or holds no queue at all: the
    caller then falls back to its configured link.
    """
    queue = queue_service.describe_current_queue()
    if not queue:
        raise HTTPException(status_code=503, detail="Queue information is unavailable")
    return queue
