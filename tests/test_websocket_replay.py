"""
WebSocket reconnect state-replay unit tests.

Verifies GameSession._replay_snapshot builds the right follow-up messages for a
(re)connecting admin/player in each live phase, so a refreshed client resumes the
exact game state instead of desyncing.
"""
import json

import pytest

from app.websocket.game import GameSession


class FakeWS:
    """Minimal WebSocket stand-in that collects sent messages."""

    def __init__(self):
        self.sent: list[dict] = []

    async def send_text(self, raw: str):
        self.sent.append(json.loads(raw))


class FakePC:
    """Duck-typed PlayerConnection for session.players."""

    def __init__(self, ws, room_player_id: int):
        self.ws = ws
        self.room_player_id = room_player_id
        self.user_id = room_player_id
        self.player_name = f"player-{room_player_id}"


def _question_payload(**overrides):
    payload = {
        "type": "question",
        "question_id": 1,
        "number": 3,
        "total": 12,
        "text": "Which test?",
        "options": [],
        "time_limit": 20,
        "score": 500,
        "multiplier": 1,
    }
    payload.update(overrides)
    return payload


class TestReplaySnapshot:
    def test_no_snapshot_is_noop(self):
        s = GameSession("1234")
        s.snapshot = None
        ws = FakeWS()
        import asyncio
        asyncio.run(s._replay_snapshot(ws, "admin"))
        assert ws.sent == []

    def test_countdown(self):
        s = GameSession("1234")
        s.snapshot = {"phase": "countdown", "countdown_value": 2}
        aws, pws = FakeWS(), FakeWS()
        import asyncio
        asyncio.run(s._replay_snapshot(aws, "admin"))
        asyncio.run(s._replay_snapshot(pws, "player"))
        assert aws.sent == [{"type": "countdown", "value": 2}]
        assert pws.sent == [{"type": "countdown", "value": 2}]

    def test_question_sends_question_plus_tick(self):
        s = GameSession("1234")
        s.snapshot = {
            "phase": "question",
            "question": _question_payload(),
            "remaining": 12,
            "answered_count": 2,
            "is_paused": False,
            "total_players": 3,
        }
        aws, pws = FakeWS(), FakeWS()
        import asyncio
        asyncio.run(s._replay_snapshot(aws, "admin"))
        asyncio.run(s._replay_snapshot(pws, "player"))
        for ws in (aws, pws):
            types = [m["type"] for m in ws.sent]
            assert types == ["question", "tick"], types
            assert ws.sent[1]["remaining"] == 12
            assert ws.sent[1]["answered_count"] == 2

    def test_paused_question_includes_paused_message(self):
        s = GameSession("1234")
        s.snapshot = {
            "phase": "question",
            "question": _question_payload(),
            "remaining": 7,
            "answered_count": 1,
            "is_paused": True,
            "total_players": 2,
        }
        pws = FakeWS()
        import asyncio
        asyncio.run(s._replay_snapshot(pws, "player"))
        types = [m["type"] for m in pws.sent]
        assert types == ["question", "tick", "paused"], types

    def test_result_player_personalized(self):
        s = GameSession("1234")
        pws = FakeWS()
        pc = FakePC(pws, room_player_id=42)
        s.players = [pc]
        s.snapshot = {
            "phase": "result",
            "question": _question_payload(multiplier=2),
            "correct_option": "B",
            "distribution": {"A": 1, "B": 2, "C": 0, "D": 0},
            "result_answers": {"42": {"option": "B", "correct": True, "score": 1500}},
        }
        import asyncio
        asyncio.run(s._replay_snapshot(pws, "player"))
        assert pws.sent[0]["type"] == "question"
        res = pws.sent[1]
        assert res["type"] == "question_result"
        assert res["your_option"] == "B"
        assert res["is_correct"] is True
        assert res["score_earned"] == 1500
        assert res["distribution"]["B"] == 2

    def test_result_admin_gets_answers_map(self):
        s = GameSession("1234")
        aws = FakeWS()
        s.snapshot = {
            "phase": "result",
            "question": _question_payload(),
            "correct_option": "B",
            "distribution": {"A": 0, "B": 1, "C": 0, "D": 0},
            "result_answers": {"42": {"option": "B", "correct": True, "score": 1000}},
        }
        import asyncio
        asyncio.run(s._replay_snapshot(aws, "admin"))
        assert aws.sent[0]["type"] == "question"
        res = aws.sent[1]
        assert res["type"] == "question_result"
        assert "answers" in res
        assert res["answers"]["42"]["correct"] is True

    def test_leaderboard_and_finished(self):
        s = GameSession("1234")
        pws = FakeWS()
        import asyncio
        s.snapshot = {
            "phase": "leaderboard",
            "leaderboard": [{"rank": 1, "player_id": 1, "player_name": "A", "total_score": 2000, "streak": 0}],
            "question_number": 9,
            "total_questions": 12,
        }
        asyncio.run(s._replay_snapshot(pws, "player"))
        assert pws.sent[0]["type"] == "leaderboard"
        assert pws.sent[0]["total_questions"] == 12

        pws2 = FakeWS()
        s.snapshot = {"phase": "finished", "leaderboard": []}
        asyncio.run(s._replay_snapshot(pws2, "player"))
        assert pws2.sent[0]["type"] == "game_over"
