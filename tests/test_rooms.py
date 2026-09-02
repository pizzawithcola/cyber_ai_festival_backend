"""
Room balance (per-category question distribution) tests.
"""
import pytest

from app.models.room import Room


class TestCreateRoomBalance:
    def test_create_room_without_balance(self, client):
        resp = client.post("/rooms/", json={"question_count": 10})
        assert resp.status_code == 200
        assert len(resp.json()["room_code"]) == 4

    def test_create_room_with_balance(self, client):
        resp = client.post("/rooms/", json={
            "question_count": 10,
            "balance": {"phishing": 2, "ai": 2, "bonus": 1},
        })
        assert resp.status_code == 200
        code = resp.json()["room_code"]
        rooms = client.get("/rooms/").json()
        room = next(r for r in rooms if r["room_code"] == code)
        # question_count is the sum of the balance
        assert room["question_count"] == 5

    def test_create_room_with_new_category_balance(self, client):
        """New curated categories (hallucination/data/agent/phishing) are accepted."""
        resp = client.post("/rooms/", json={
            "question_count": 10,
            "balance": {"hallucination": 1, "data": 1, "agent": 1, "phishing": 2},
        })
        assert resp.status_code == 200
        code = resp.json()["room_code"]
        rooms = client.get("/rooms/").json()
        room = next(r for r in rooms if r["room_code"] == code)
        assert room["question_count"] == 5

    def test_create_room_balance_filters_unknown_categories(self, client):
        resp = client.post("/rooms/", json={
            "question_count": 10,
            "balance": {"phishing": 2, "unknown_cat": 5, "": 3, "bonus": 0},
        })
        assert resp.status_code == 200
        code = resp.json()["room_code"]
        rooms = client.get("/rooms/").json()
        room = next(r for r in rooms if r["room_code"] == code)
        # only "phishing": 2 survives (unknown + zero-count dropped)
        assert room["question_count"] == 2

    def test_create_room_with_empty_balance_falls_back_to_question_count(self, client):
        resp = client.post("/rooms/", json={
            "question_count": 8,
            "balance": {},
        })
        assert resp.status_code == 200
        code = resp.json()["room_code"]
        rooms = client.get("/rooms/").json()
        room = next(r for r in rooms if r["room_code"] == code)
        assert room["question_count"] == 8


class TestRejoinWhilePlaying:
    """A player who already joined may re-join (refresh / reconnect) while the game
    is running; brand-new players are still blocked once it has started."""

    def test_existing_player_can_rejoin_while_playing(self, client, db_session):
        resp = client.post("/rooms/", json={"question_count": 10})
        assert resp.status_code == 200
        code = resp.json()["room_code"]

        first = client.post(f"/rooms/{code}/join", json={"user_id": 7, "player_name": "Alice"})
        assert first.status_code == 200

        # Mark the room as playing (simulates admin having started the game)
        room = db_session.query(Room).filter(Room.code == code).first()
        assert room is not None
        room.status = "playing"
        db_session.commit()

        # Already-joined player refreshing → allowed (200)
        rejoin = client.post(f"/rooms/{code}/join", json={"user_id": 7, "player_name": "Alice"})
        assert rejoin.status_code == 200

    def test_new_player_blocked_while_playing(self, client, db_session):
        resp = client.post("/rooms/", json={"question_count": 10})
        assert resp.status_code == 200
        code = resp.json()["room_code"]

        client.post(f"/rooms/{code}/join", json={"user_id": 7, "player_name": "Alice"})

        room = db_session.query(Room).filter(Room.code == code).first()
        room.status = "playing"
        db_session.commit()

        # Brand-new player while playing → rejected (400)
        blocked = client.post(f"/rooms/{code}/join", json={"user_id": 99, "player_name": "Bob"})
        assert blocked.status_code == 400

    def test_rejoin_blocked_after_finished(self, client, db_session):
        resp = client.post("/rooms/", json={"question_count": 10})
        assert resp.status_code == 200
        code = resp.json()["room_code"]
        client.post(f"/rooms/{code}/join", json={"user_id": 7, "player_name": "Alice"})

        room = db_session.query(Room).filter(Room.code == code).first()
        room.status = "finished"
        db_session.commit()

        rejoin = client.post(f"/rooms/{code}/join", json={"user_id": 7, "player_name": "Alice"})
        assert rejoin.status_code == 400
