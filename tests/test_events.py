"""Tests for the event configuration + time-window report feature."""

from datetime import datetime, timedelta, timezone

import pytest

from app.services import queue_service


@pytest.fixture(autouse=True)
def _disable_queue(monkeypatch):
    """Registration spawns a background queue task; keep it off in tests."""
    monkeypatch.setattr(queue_service.settings, "queue_enabled", False)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def test_event_lifecycle(client):
    now = datetime.now(timezone.utc)
    payload = {
        "name": "Festival 2026",
        "description": "Dubai venue",
        "start_at": _iso(now - timedelta(hours=1)),
        "end_at": _iso(now + timedelta(hours=1)),
    }

    created = client.post("/events/", json=payload)
    assert created.status_code == 200
    ev = created.json()
    assert ev["name"] == "Festival 2026"

    listed = client.get("/events/")
    assert listed.status_code == 200
    assert any(e["id"] == ev["id"] for e in listed.json())

    deleted = client.delete(f"/events/{ev['id']}")
    assert deleted.status_code == 200

    missing = client.get(f"/events/{ev['id']}/report")
    assert missing.status_code == 404


def test_event_report_counts_participants(client):
    reg = client.post(
        "/users/",
        json={"firstname": "Event", "lastname": "Tester", "region": "United Arab Emirates"},
    )
    assert reg.status_code == 200

    now = datetime.now(timezone.utc)
    ev = client.post(
        "/events/",
        json={
            "name": "E",
            "description": None,
            "start_at": _iso(now - timedelta(hours=2)),
            "end_at": _iso(now + timedelta(hours=2)),
        },
    ).json()

    rep = client.get(f"/events/{ev['id']}/report").json()
    assert rep["total_participants"] >= 1
    assert rep["country_count"] >= 1
    assert any(c["region"] == "United Arab Emirates" for c in rep["countries"])
    assert rep["event"]["name"] == "E"
    # games / showdown / top_players are always present (possibly zero-filled)
    assert set(rep["games"].keys()) == {"game1", "game2", "game3", "game4", "game5"}
    assert set(rep["showdown"].keys()) == {"rooms", "players", "answers"}
