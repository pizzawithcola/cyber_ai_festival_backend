"""Nickname rule (JL1) + queue display-name regression tests."""

import pytest

from app.crud.user import initials_of
from app.services import queue_service


@pytest.fixture(autouse=True)
def _disable_queue(monkeypatch):
    monkeypatch.setattr(queue_service.settings, "queue_enabled", False)


def test_initials_of():
    assert initials_of("Jamie", "Liu") == "JL"
    assert initials_of("jamie", "liu") == "JL"
    assert initials_of("Jamie", None) == "JA"
    assert initials_of("", "") == "PL"
    assert initials_of("张", "三") == "PL"  # non-Latin falls back to a placeholder


def test_nickname_is_memorable_and_collision_safe(client):
    r1 = client.post("/users/", json={"firstname": "Jamie", "lastname": "Liu", "region": "China"})
    r2 = client.post("/users/", json={"firstname": "Jing", "lastname": "Li", "region": "China"})
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["nickname"] == "JL1"
    assert r2.json()["nickname"] == "JL2"


def test_registration_enqueues_real_name(client, monkeypatch):
    from app.routers import users as users_module

    calls = []
    monkeypatch.setattr(users_module, "enqueue_user", lambda uid, name: calls.append((uid, name)))

    r = client.post("/users/", json={"firstname": "Jamie", "lastname": "Liu", "region": "China"})
    assert r.status_code == 200
    assert calls == [(r.json()["id"], "Jamie Liu")]
