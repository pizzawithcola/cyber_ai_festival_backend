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


class FakeQueueList:
    """Stand-in for GET /v1/queues."""

    def __init__(self, queues: list[dict]):
        self._queues = queues

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return {"queues": self._queues}


# The organiser deletes and recreates queues, so the newest entry must win.
QUEUES = [
    {"queueId": "older-queue", "name": "Old One", "createdAt": 100,
     "queueBoardUrl": "https://queue.example/#queue/older-queue"},
    {"queueId": "newest-queue", "name": "Arcade", "createdAt": 999,
     "queueBoardUrl": "https://queue.example/#queue/newest-queue"},
]


@pytest.fixture(autouse=True)
def queue_settings(monkeypatch):
    """Enable the integration with fake credentials and no retry delays."""
    monkeypatch.setattr(queue_service.settings, "queue_enabled", True)
    monkeypatch.setattr(queue_service.settings, "queue_base_url", "https://queue.example/api")
    monkeypatch.setattr(queue_service.settings, "queue_queue_id", "test-queue")
    monkeypatch.setattr(queue_service.settings, "queue_api_key", "test-key")
    monkeypatch.setattr(queue_service.settings, "queue_timeout_seconds", 5.0)
    monkeypatch.setattr(queue_service.time, "sleep", lambda _seconds: None)


def _capture(nickname: str, user_id: int, response: FakeResponse | None = None,
             queues: list[dict] | None = None):
    """Run one enrolment with both HTTP calls mocked out."""
    listing = FakeQueueList(QUEUES if queues is None else queues)
    with patch.object(queue_service.httpx, "post", return_value=response or FakeResponse()) as post, \
            patch.object(queue_service.httpx, "get", return_value=listing):
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
    assert url == "https://queue.example/api/v1/queues/newest-queue/participants"
    assert post.call_args.kwargs["headers"]["X-API-Key"] == "test-key"


def test_newest_queue_wins_over_older_ones():
    """A stale queue id must never be posted to while a newer queue exists.

    Regression: on 2026-09-21 the organiser recreated the queue, our configured
    id kept pointing at the deleted one and every registration answered 404
    queue_not_found, so players silently never reached the screen.
    """
    post, result = _capture("AliceQ_003", 4242)

    assert result is True
    assert "/v1/queues/newest-queue/participants" in post.call_args.args[0]
    assert "older-queue" not in post.call_args.args[0]


def test_falls_back_to_the_configured_queue_when_listing_fails():
    """If the listing call fails we still try the id from the configuration."""
    with patch.object(queue_service.httpx, "get", side_effect=OSError("boom")), \
            patch.object(queue_service.httpx, "post", return_value=FakeResponse()) as post:
        assert queue_service.enqueue_user(4242, "AliceQ_003") is True

    assert "/v1/queues/test-queue/participants" in post.call_args.args[0]


def test_listing_failure_still_never_raises():
    with patch.object(queue_service.httpx, "get", side_effect=OSError("boom")), \
            patch.object(queue_service.httpx, "post", side_effect=OSError("boom")):
        assert queue_service.enqueue_user(4242, "AliceQ_003") is False


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


def test_describe_current_queue_reports_the_newest_board_url():
    """The frontend needs a board link that survives the queue being recreated."""
    with patch.object(queue_service.httpx, "get", return_value=FakeQueueList(QUEUES)):
        info = queue_service.describe_current_queue()

    assert info == {
        "queueId": "newest-queue",
        "name": "Arcade",
        "queueBoardUrl": "https://queue.example/#queue/newest-queue",
    }


def test_describe_current_queue_is_none_without_a_barrable_queue():
    """No queue, a dead API or a queue without an id must all say "unknown"."""
    for queues_or_error in ([], [{"name": "Nameless", "createdAt": 1}]):
        with patch.object(queue_service.httpx, "get", return_value=FakeQueueList(queues_or_error)):
            assert queue_service.describe_current_queue() is None

    with patch.object(queue_service.httpx, "get", side_effect=OSError("boom")):
        assert queue_service.describe_current_queue() is None


def test_queue_endpoint_hands_the_frontend_the_live_board_url(client):
    """GET /queue/ is what keeps the frontend off a dead board."""
    with patch.object(queue_service.httpx, "get", return_value=FakeQueueList(QUEUES)):
        response = client.get("/queue/")

    assert response.status_code == 200
    assert response.json()["queueId"] == "newest-queue"
    assert response.json()["queueBoardUrl"] == "https://queue.example/#queue/newest-queue"


def test_queue_endpoint_answers_503_when_the_queue_system_is_down(client):
    """503, never a guess: the frontend then keeps its own configured fallback."""
    with patch.object(queue_service.httpx, "get", side_effect=OSError("boom")):
        assert client.get("/queue/").status_code == 503


def test_board_link_and_enrolment_never_disagree(client):
    """Nobody may be queued in a queue they cannot watch on the big screen."""
    listing = FakeQueueList(QUEUES)
    with patch.object(queue_service.httpx, "get", return_value=listing), \
            patch.object(queue_service.httpx, "post", return_value=FakeResponse()) as post:
        board = client.get("/queue/").json()
        assert queue_service.enqueue_user(99, "ZoeQ_009") is True

    assert board["queueId"] == "newest-queue"
    assert post.call_args.args[0].endswith("/queues/newest-queue/participants")
