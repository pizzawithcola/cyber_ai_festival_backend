"""
Room balance (per-category question distribution) tests.
"""
import pytest


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
