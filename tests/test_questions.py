"""
Question bank CRUD endpoint tests (Ultimate Showdown).
"""
import pytest

from app.models.room import Room, RoomPlayer, PlayerAnswer
from tests.conftest import TestSessionLocal
import pytest


def make_question_payload(**overrides):
    payload = {
        "text": "What does RAG stand for?",
        "option_a": "Random Access Graph",
        "option_b": "Retrieval-Augmented Generation",
        "option_c": "Recursive Agent Gateway",
        "option_d": "Realtime Analytics Group",
        "correct_option": "b",  # intentionally lowercase to test normalization
        "time_limit": 25,
        "category": "AI Techniques",
        "score": 1500,
    }
    payload.update(overrides)
    return payload


class TestQuestionAuth:
    def test_list_requires_api_key(self, client_no_auth):
        resp = client_no_auth.get("/questions/")
        assert resp.status_code == 422

    def test_invalid_api_key(self, client_no_auth):
        resp = client_no_auth.get("/questions/", headers={"X-API-Key": "wrong-key"})
        assert resp.status_code == 401


class TestQuestionList:
    def test_list_empty(self, client):
        resp = client.get("/questions/")
        assert resp.status_code == 200
        assert resp.json() == []


class TestQuestionCreate:
    def test_create_question(self, client):
        resp = client.post("/questions/", json=make_question_payload())
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] > 0
        assert data["text"] == "What does RAG stand for?"
        assert data["option_b"] == "Retrieval-Augmented Generation"
        assert data["correct_option"] == "B"  # uppercased
        assert data["score"] == 1500
        assert data["time_limit"] == 25
        assert data["category"] == "AI Techniques"

    def test_create_question_defaults(self, client):
        """score/time_limit/category 缺省时用默认值"""
        payload = make_question_payload()
        for key in ("score", "time_limit", "category", "correct_option"):
            payload.pop(key, None)
        payload["correct_option"] = "A"
        resp = client.post("/questions/", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["score"] == 1000
        assert data["time_limit"] == 20
        assert data["category"] == "general"

    def test_create_question_invalid_correct_option(self, client):
        """correct_option 只允许 A/B/C/D"""
        resp = client.post("/questions/", json=make_question_payload(correct_option="E"))
        assert resp.status_code == 422

    def test_create_question_negative_score(self, client):
        resp = client.post("/questions/", json=make_question_payload(score=-5))
        assert resp.status_code == 422


class TestQuestionGet:
    def test_get_question(self, client):
        created = client.post("/questions/", json=make_question_payload()).json()
        resp = client.get(f"/questions/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]

    def test_get_question_404(self, client):
        resp = client.get("/questions/99999")
        assert resp.status_code == 404


class TestQuestionUpdate:
    def test_update_question(self, client):
        created = client.post("/questions/", json=make_question_payload()).json()
        resp = client.put(
            f"/questions/{created['id']}",
            json={"text": "Updated RAG question?", "score": 2000},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["text"] == "Updated RAG question?"
        assert data["score"] == 2000
        assert data["option_b"] == "Retrieval-Augmented Generation"  # 未改动字段保留

    def test_update_question_normalizes_correct_option(self, client):
        created = client.post("/questions/", json=make_question_payload()).json()
        resp = client.put(
            f"/questions/{created['id']}",
            json={"correct_option": "c"},
        )
        assert resp.status_code == 200
        assert resp.json()["correct_option"] == "C"

    def test_update_question_404(self, client):
        resp = client.put("/questions/99999", json={"text": "nope"})
        assert resp.status_code == 404


class TestQuestionDelete:
    def test_delete_question(self, client):
        created = client.post("/questions/", json=make_question_payload()).json()
        resp = client.delete(f"/questions/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["question_id"] == created["id"]
        # 删除后再查应 404
        assert client.get(f"/questions/{created['id']}").status_code == 404

    def test_delete_question_404(self, client):
        resp = client.delete("/questions/99999")
        assert resp.status_code == 404


class TestQuestionDeleteWithAnswers:
    """删除被 player_answers 引用的题目（外键场景）"""

    def test_delete_question_with_answer_history(self, client):
        # 1. 通过 API 创建题目
        q = client.post("/questions/", json=make_question_payload()).json()
        qid = q["id"]

        # 2. 直接写库：Room → RoomPlayer → PlayerAnswer（引用该题）
        db = TestSessionLocal()
        try:
            room = Room(code="9999", admin_id=1, status="waiting")
            db.add(room)
            db.commit()
            db.refresh(room)
            rp = RoomPlayer(room_id=room.id, user_id=1, player_name="Test")
            db.add(rp)
            db.commit()
            db.refresh(rp)
            pa = PlayerAnswer(
                player_id=rp.id, question_id=qid,
                chosen_option="A", is_correct=True,
                answer_time_ms=100, score_earned=100,
            )
            db.add(pa)
            db.commit()
        finally:
            db.close()

        # 3. 删除该题 —— 应级联清理 answer 并成功，而非 500
        resp = client.delete(f"/questions/{qid}")
        assert resp.status_code == 200
        assert resp.json()["question_id"] == qid
        assert client.get(f"/questions/{qid}").status_code == 404
