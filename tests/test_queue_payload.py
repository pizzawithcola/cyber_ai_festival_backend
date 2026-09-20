"""Contract tests for the payload we POST to the external venue queue.

Why this file exists
--------------------
The queue API still accepts an ``email`` field, and it is not merely cosmetic:
live probing on 2026-09-18 showed that an entry created *with* an email forms a
separate identity space. A later POST carrying the same ``externalId`` but no
email does NOT match it, so the same person ends up queued twice and can never
be merged again.

We therefore deliberately send only ``{name, externalId}``. These tests are the
guard rail: if anyone ever adds an email (or any other field) to the request,
they fail loudly.

Run with:
    python -m pytest tests/test_queue_payload.py -v
"""

from unittest.mock import patch

import pytest

from app.services import queue_service


class FakeResponse:
    """Minimal stand-in for httpx.Response."""

    def __init__(self, status_code: int = 201, text: str = '{"participantId": "p1"}'):
        self.status_code = status_code
        self.text = text


@pytest.fixture(autouse=True)
def queue_settings(monkeypatch):
    """Enable the integration with fake credentials and no retry delays."""
    monkeypatch.setattr(queue_service.settings, "queue_enabled", True)
    monkeypatch.setattr(queue_service.settings, "queue_base_url", "https://queue.example/api")
    monkeypatch.setattr(queue_service.settings, "queue_queue_id", "test-queue")
    monkeypatch.setattr(queue_service.settings, "queue_api_key", "test-key")
    monkeypatch.setattr(queue_service.settings, "queue_timeout_seconds", 5.0)
    monkeypatch.setattr(queue_service.time, "sleep", lambda _seconds: None)


def _capture(nickname: str, user_id: int, response: FakeResponse | None = None):
    """Run one enrolment and return the mocked httpx.post used for it."""
    with patch.object(queue_service.httpx, "post", return_value=response or FakeResponse()) as post:
        result = queue_service.enqueue_user(user_id, nickname)
    return post, result


def test_payload_contains_only_name_and_external_id():
    """The whole point of this file: nothing but name + externalId is sent."""
    post, result = _capture("AliceQ_003", 4242)

    assert result is True
    assert post.call_count == 1

    body = post.call_args.kwargs["json"]
    assert set(body.keys()) == {"name", "externalId"}, (
        f"queue payload must be exactly name + externalId, got {sorted(body)}"
    )
    assert "email" not in body
    assert body["name"] == "AliceQ_003"
    assert body["externalId"] == "4242"


def test_no_email_even_for_email_shaped_nicknames():
    """The old implementation turned nicknames into fake addresses; never again."""
    for nickname in ("admin@admin.com", "John Smith Jr", "玩家_001", "  spaced  "):
        post, _ = _capture(nickname, 7)
        body = post.call_args.kwargs["json"]
        assert set(body.keys()) == {"name", "externalId"}, nickname
        assert "@" not in str(body) or nickname == "admin@admin.com"


def test_request_target_and_auth_header():
    post, _ = _capture("AliceQ_003", 4242)

    url = post.call_args.args[0]
    assert url == "https://queue.example/api/v1/queues/test-queue/participants"
    assert post.call_args.kwargs["headers"]["X-API-Key"] == "test-key"


def test_name_is_truncated_to_the_server_limit():
    """The server answers 400 name_too_long above 100 characters."""
    post, _ = _capture("N" * 300, 99)
    assert len(post.call_args.kwargs["json"]["name"]) == queue_service.MAX_NAME_LENGTH == 100


def test_empty_nickname_falls_back_to_a_placeholder():
    """The server answers 400 name_required for an empty name."""
    for nickname in ("", "   ", None):
        post, _ = _capture(nickname, 555)
        assert post.call_args.kwargs["json"]["name"] == "Player 555"


def test_client_error_is_not_retried():
    """4xx is permanent for this payload, so one attempt is enough."""
    post, result = _capture("AliceQ_003", 4242, FakeResponse(400, '{"error":"name_required"}'))

    assert result is False
    assert post.call_count == 1


def test_server_error_is_retried_then_reported():
    post, result = _capture("AliceQ_003", 4242, FakeResponse(503, "unavailable"))

    assert result is False
    assert post.call_count == queue_service.NETWORK_ATTEMPTS


def test_network_failure_never_raises():
    """Registration must succeed even when the queue is unreachable."""
    with patch.object(queue_service.httpx, "post", side_effect=OSError("boom")):
        assert queue_service.enqueue_user(4242, "AliceQ_003") is False


def test_disabled_integration_sends_nothing():
    queue_service.settings.queue_enabled = False
    try:
        post, result = _capture("AliceQ_003", 4242)
        assert result is False
        assert post.call_count == 0
    finally:
        queue_service.settings.queue_enabled = True
