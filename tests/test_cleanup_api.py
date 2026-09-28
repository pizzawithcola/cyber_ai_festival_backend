"""
Cleanup API tests: wiping the stage clean before a live event.

Covers:
  * DELETE /rooms/{code}  - room + its players + their answers
  * POST   /rooms/purge   - every room at once
  * DELETE /users/{id}    - no ghost player left behind inside rooms
  * POST   /users/purge   - players only, admin accounts are kept
"""
from app.models.room import Room, RoomPlayer, PlayerAnswer, Question
from app.models.user import User


def _create_user(client, firstname="Test", lastname="Player"):
    resp = client.post(
        "/users/",
        json={"firstname": firstname, "lastname": lastname, "region": "AE"},
    )
    assert resp.status_code == 200
    return resp.json()


def _create_room(client, question_count=7):
    resp = client.post("/rooms/", json={"question_count": question_count})
    assert resp.status_code == 200
    return resp.json()["room_code"]


class TestDeleteRoom:
    def test_delete_room_removes_players_and_answers(self, client, db_session):
        code = _create_room(client)
        alice = _create_user(client, "Alice", "One")
        bob = _create_user(client, "Bob", "Two")
        for user in (alice, bob):
            resp = client.post(
                f"/rooms/{code}/join",
                json={"user_id": user["id"], "player_name": "ignored"},
            )
            assert resp.status_code == 200

        # Give one player an answer so the second-level cascade is covered too.
        room = db_session.query(Room).filter(Room.code == code).first()
        room_id = room.id
        player = db_session.query(RoomPlayer).filter(RoomPlayer.room_id == room_id).first()
        question = Question(
            text="q", option_a="a", option_b="b", option_c="c", option_d="d",
            correct_option="A", time_limit=20, category="general", score=1000,
        )
        db_session.add(question)
        db_session.commit()
        db_session.add(PlayerAnswer(
            player_id=player.id, question_id=question.id, chosen_option="A",
            is_correct=True, answer_time_ms=1200, score_earned=1000,
        ))
        db_session.commit()

        resp = client.delete(f"/rooms/{code}")
        assert resp.status_code == 200
        assert resp.json()["players_removed"] == 2

        assert db_session.query(Room).filter(Room.code == code).first() is None
        assert db_session.query(RoomPlayer).filter(RoomPlayer.room_id == room_id).count() == 0
        assert db_session.query(PlayerAnswer).count() == 0
        assert all(r["room_code"] != code for r in client.get("/rooms/").json())

    def test_delete_unknown_room_is_404(self, client):
        assert client.delete("/rooms/9999").status_code == 404

    def test_room_list_is_empty_after_delete(self, client):
        code = _create_room(client)
        assert client.delete(f"/rooms/{code}").status_code == 200
        assert all(r["room_code"] != code for r in client.get("/rooms/").json())


class TestDeleteAllRooms:
    def test_purge_rooms(self, client, db_session):
        codes = [_create_room(client) for _ in range(3)]
        user = _create_user(client)
        client.post(f"/rooms/{codes[0]}/join", json={"user_id": user["id"], "player_name": "p"})

        resp = client.post("/rooms/purge")
        assert resp.status_code == 200
        body = resp.json()
        assert body["rooms_removed"] == 3
        assert sorted(body["room_codes"]) == sorted(codes)
        assert client.get("/rooms/").json() == []
        assert db_session.query(RoomPlayer).count() == 0

    def test_purge_rooms_is_idempotent(self, client):
        assert client.post("/rooms/purge").json()["rooms_removed"] == 0


class TestDeleteUsers:
    def test_delete_user_leaves_no_ghost_player_in_room(self, client, db_session):
        code = _create_room(client)
        user = _create_user(client, "Ghost", "Gone")
        client.post(f"/rooms/{code}/join", json={"user_id": user["id"], "player_name": "p"})

        assert client.delete(f"/users/{user['id']}").status_code == 200

        # The room survives, but the player row must not.
        assert db_session.query(RoomPlayer).filter(RoomPlayer.user_id == user["id"]).count() == 0
        room = next(r for r in client.get("/rooms/").json() if r["room_code"] == code)
        assert room["player_count"] == 0

    def test_purge_users_keeps_admins(self, client, db_session):
        _create_user(client, "P1", "X")
        _create_user(client, "P2", "Y")
        db_session.add(User(firstname="Admin", lastname="Root", nickname="ADM1", role="admin"))
        db_session.commit()

        resp = client.post("/users/purge")
        assert resp.status_code == 200
        assert resp.json()["users_removed"] == 2
        assert resp.json()["admins_kept"] == 1

        remaining = client.get("/users/").json()
        assert len(remaining) == 1
        assert remaining[0]["nickname"] == "ADM1"

    def test_purge_users_can_include_admins(self, client, db_session):
        _create_user(client, "P1", "X")
        db_session.add(User(firstname="Admin", lastname="Root", nickname="ADM2", role="admin"))
        db_session.commit()

        resp = client.post("/users/purge?include_admins=true")
        assert resp.status_code == 200
        assert resp.json()["users_removed"] == 2
        assert client.get("/users/").json() == []
