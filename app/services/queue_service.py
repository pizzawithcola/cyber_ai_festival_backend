"""Enrol a newly registered player into the external venue queue.

Verified contract (live-tested against the service, see doc/QUEUE_INTEGRATION.md):
- POST {base}/v1/queues/{queue_id}/participants   body {email, name, externalId}
    201 = joined, 200 = already in the queue (idempotent, deduplicated by email)
- GET  {base}/v1/queues                            list queues
- DELETE {base}/v1/queues/{queue_id}/participants/{participant_id}
- The email is validated strictly: a nickname containing a space or an "@"
  is rejected with HTTP 400 {"error": "email_invalid"}.
- Connection resets happen in practice (CN egress), so transient errors retry.

Design rules:
- Never raise: registration must succeed even when the queue is down.
- Retry transient failures (network / 5xx); never retry 4xx.
- If the nickname-derived address is rejected, fall back to the user id form,
  which is always valid and always unique, so nobody silently misses the queue.
"""

import json
import logging
import re
import time

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# A nickname that already looks like an address is used as-is (one admin account
# is literally called "admin@admin.com"); anything else gets a suffix.
EMAIL_LIKE = re.compile(r"@[^@\s]+\.[A-Za-z]{2,}$")
EMAIL_SUFFIX = "@gmail.com"
FALLBACK_DOMAIN = "cyber-ai-festival.local"

MAX_NAME_LENGTH = 100        # queue field limit
NETWORK_ATTEMPTS = 3
BACKOFF_SECONDS = 1.0


def queue_email(nickname: str, user_id: int) -> str:
    """Dedupe key for the queue: the nickname, given an address shape."""
    name = (nickname or "").strip()
    if not name:
        return fallback_email(user_id)
    if EMAIL_LIKE.search(name):
        return name
    return f"{name}{EMAIL_SUFFIX}"


def fallback_email(user_id: int) -> str:
    """Always valid and always unique — used when the nickname form is rejected."""
    return f"user{user_id}@{FALLBACK_DOMAIN}"


def _post_participant(email: str, name: str, user_id: int) -> tuple[int, str]:
    url = (
        f"{settings.queue_base_url.rstrip('/')}/v1/queues/"
        f"{settings.queue_queue_id}/participants"
    )
    response = httpx.post(
        url,
        json={"email": email, "name": name, "externalId": str(user_id)},
        headers={"X-API-Key": settings.queue_api_key},
        timeout=settings.queue_timeout_seconds,
    )
    return response.status_code, response.text


def _attempt(email: str, name: str, user_id: int) -> str:
    """POST one participant. Returns 'ok' | 'permanent' | 'transient'."""
    for attempt in range(1, NETWORK_ATTEMPTS + 1):
        try:
            status, text = _post_participant(email, name, user_id)
        except Exception as exc:  # network / TLS / timeout
            logger.warning(
                "Queue request failed for user %s (email=%s): %s (attempt %s/%s)",
                user_id, email, exc, attempt, NETWORK_ATTEMPTS,
            )
        else:
            if 200 <= status < 300:
                entry: dict = {}
                try:
                    entry = json.loads(text)
                except ValueError:
                    pass
                logger.info(
                    "Queue: user %s joined as %s -> HTTP %s (id=%s, rank=%s, already=%s, total=%s)",
                    user_id, email, status, entry.get("participantId"),
                    entry.get("rank"), entry.get("alreadyInQueue"),
                    entry.get("totalInQueue"),
                )
                return "ok"
            if 400 <= status < 500:
                # Permanent for this address (e.g. email_invalid): no retry.
                logger.error(
                    "Queue rejected user %s (email=%s): HTTP %s %s",
                    user_id, email, status, text[:200],
                )
                return "permanent"
            logger.warning(
                "Queue server error for user %s (email=%s): HTTP %s (attempt %s/%s)",
                user_id, email, status, attempt, NETWORK_ATTEMPTS,
            )

        if attempt < NETWORK_ATTEMPTS:
            time.sleep(BACKOFF_SECONDS * attempt)

    return "transient"


def enqueue_user(user_id: int, nickname: str) -> bool:
    """Best-effort enrolment of one player. Never raises."""
    if not settings.queue_enabled:
        logger.debug("Queue integration disabled; skipping user %s", user_id)
        return False
    if not settings.queue_queue_id or not settings.queue_api_key:
        logger.warning("Queue integration enabled but queue id / api key is missing")
        return False

    name = (nickname or "").strip()[:MAX_NAME_LENGTH] or f"Player {user_id}"
    primary = queue_email(nickname, user_id)

    outcome = _attempt(primary, name, user_id)
    if outcome == "ok":
        return True

    if outcome == "permanent":
        fallback = fallback_email(user_id)
        if primary != fallback:
            logger.warning("Queue: retrying user %s with %s", user_id, fallback)
            if _attempt(fallback, name, user_id) == "ok":
                return True

    logger.error("Queue: could not enrol user %s", user_id)
    return False
