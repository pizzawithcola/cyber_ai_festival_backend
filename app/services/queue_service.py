"""Enrol a newly registered player into the external venue queue.

Verified contract (live-probed 2026-09-16 against the production queue, see
doc/QUEUE_INTEGRATION.md):
- POST {base}/v1/queues/{queue_id}/participants   body {name, externalId}
    201 = joined, 200 = already in the queue (idempotent, deduplicated by
    ``externalId``; ``name`` is NOT a dedupe key, so two players may share a
    nickname without shadowing each other)
- GET  {base}/v1/queues/{queue_id}                 queue state + participants
- DELETE {base}/v1/queues/{queue_id}/participants/{participant_id}   (undocumented)
- ``name`` is required, non-empty and at most 100 characters, otherwise the
  server answers 400 {"error": "name_required"} / {"error": "name_too_long"}.
- ``email`` is optional but NOT gone: a supplied value is validated (400
  {"error": "email_invalid"}) and switches the entry into a SEPARATE identity
  space -- live probing on 2026-09-18 proved that an entry created with an email
  can never be matched by an ``externalId`` lookup that omits it. We therefore
  never send one: identity stays in the ``externalId`` space and no player
  address ever leaves our system. Guarded by tests/test_queue_payload.py.
- An idempotent hit updates the stored ``name`` (the screen shows the last
  submitted name), so always send the player's current nickname.
- Connection resets happen in practice (CN egress), so transient errors retry.

Design rules:
- Never raise: registration must succeed even when the queue is down.
- Retry transient failures (network / 5xx); never retry 4xx (permanent).
- Send our own user id as ``externalId`` and let the queue deduplicate: a repeat
  submission is idempotent, so nobody is ever queued twice.
"""

import json
import logging
import time

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

MAX_NAME_LENGTH = 100        # server-enforced: 400 "name_too_long" above this
NETWORK_ATTEMPTS = 3
BACKOFF_SECONDS = 1.0


def _post_participant(name: str, user_id: int) -> tuple[int, str]:
    url = (
        f"{settings.queue_base_url.rstrip('/')}/v1/queues/"
        f"{settings.queue_queue_id}/participants"
    )
    response = httpx.post(
        url,
        # Our user id is the stable identity the queue deduplicates on, and the
        # nickname is the only label we need to display on the screen.
        json={"name": name, "externalId": str(user_id)},
        headers={"X-API-Key": settings.queue_api_key},
        timeout=settings.queue_timeout_seconds,
    )
    return response.status_code, response.text


def _attempt(name: str, user_id: int) -> bool:
    """POST one participant. True once the player is in the queue."""
    for attempt in range(1, NETWORK_ATTEMPTS + 1):
        try:
            status, text = _post_participant(name, user_id)
        except Exception as exc:  # network / TLS / timeout
            logger.warning(
                "Queue request failed for user %s: %s (attempt %s/%s)",
                user_id, exc, attempt, NETWORK_ATTEMPTS,
            )
        else:
            if 200 <= status < 300:
                entry: dict = {}
                try:
                    entry = json.loads(text)
                except ValueError:
                    pass
                logger.info(
                    "Queue: user %s (%s) -> HTTP %s (id=%s, rank=%s, ahead=%s, already=%s, total=%s)",
                    user_id, name, status, entry.get("participantId"),
                    entry.get("rank"), entry.get("peopleAhead"),
                    entry.get("alreadyInQueue"), entry.get("totalInQueue"),
                )
                return True
            if 400 <= status < 500:
                # Permanent (name_required / name_too_long / bad api key): no retry.
                logger.error(
                    "Queue rejected user %s (name=%r): HTTP %s %s",
                    user_id, name, status, text[:200],
                )
                return False
            logger.warning(
                "Queue server error for user %s: HTTP %s (attempt %s/%s)",
                user_id, status, attempt, NETWORK_ATTEMPTS,
            )

        if attempt < NETWORK_ATTEMPTS:
            time.sleep(BACKOFF_SECONDS * attempt)

    return False


def enqueue_user(user_id: int, nickname: str) -> bool:
    """Best-effort enrolment of one player. Never raises."""
    if not settings.queue_enabled:
        logger.debug("Queue integration disabled; skipping user %s", user_id)
        return False
    if not settings.queue_queue_id or not settings.queue_api_key:
        logger.warning("Queue integration enabled but queue id / api key is missing")
        return False

    # The queue rejects an empty or over-long name, so always send something
    # human-readable that fits the limit.
    name = (nickname or "").strip()[:MAX_NAME_LENGTH] or f"Player {user_id}"

    if _attempt(name, user_id):
        return True

    logger.error("Queue: could not enrol user %s", user_id)
    return False
