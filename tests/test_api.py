"""
覆盖所有 API 端点的测试。
"""
from unittest.mock import patch


# ===================== Health =====================

class TestHealth:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


# ===================== Users =====================

class TestCreateUser:
    def test_create_user(self, client):
        resp = client.post("/users/", json={
            "firstname": "Bob",
            "lastname": "Li",
            "email": "bob@example.com",
            "region": "APAC",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["firstname"] == "Bob"
        assert data["lastname"] == "Li"
        assert data["email"] == "bob@example.com"
        assert data["region"] == "APAC"
        assert "id" in data
        assert "created_at" in data

    def test_create_user_minimal(self, client):
        """region 可选"""
        resp = client.post("/users/", json={
            "firstname": "Charlie",
            "lastname": "Doe",
            "email": "charlie@example.com",
        })
        assert resp.status_code == 200
        assert resp.json()["region"] is None

    def test_create_user_duplicate_email(self, client, sample_user):
        resp = client.post("/users/", json={
            "firstname": "Dup",
            "lastname": "User",
            "email": "alice@example.com",
        })
        assert resp.status_code == 409
        detail = resp.json()["detail"]
        assert "already exists" in detail["message"]
        assert detail["user_id"] == sample_user["id"]


class TestGetUser:
    def test_get_user(self, client, sample_user):
        resp = client.get(f"/users/{sample_user['id']}")
        assert resp.status_code == 200
        assert resp.json()["email"] == "alice@example.com"

    def test_get_user_not_found(self, client):
        resp = client.get("/users/9999")
        assert resp.status_code == 404


class TestUpdateUser:
    def test_update_user_partial(self, client, sample_user):
        """只更新 region"""
        resp = client.put(f"/users/{sample_user['id']}", json={"region": "EU"})
        assert resp.status_code == 200
        assert resp.json()["region"] == "EU"
        assert resp.json()["firstname"] == "Alice"  # 其他字段不变

    def test_update_user_email(self, client, sample_user):
        resp = client.put(f"/users/{sample_user['id']}", json={"email": "new@example.com"})
        assert resp.status_code == 200
        assert resp.json()["email"] == "new@example.com"

    def test_update_user_email_conflict(self, client, sample_user):
        """更新 email 时与其他用户冲突"""
        client.post("/users/", json={
            "firstname": "Bob",
            "lastname": "Li",
            "email": "bob@example.com",
        })
        resp = client.put(f"/users/{sample_user['id']}", json={"email": "bob@example.com"})
        assert resp.status_code == 409

    def test_update_user_not_found(self, client):
        resp = client.put("/users/9999", json={"firstname": "Ghost"})
        assert resp.status_code == 404


class TestDeleteUser:
    def test_delete_user(self, client, sample_user):
        resp = client.delete(f"/users/{sample_user['id']}")
        assert resp.status_code == 200
        assert resp.json()["message"] == "User deleted"
        # 确认已删除
        resp = client.get(f"/users/{sample_user['id']}")
        assert resp.status_code == 404

    def test_delete_user_not_found(self, client):
        resp = client.delete("/users/9999")
        assert resp.status_code == 404


class TestListUsers:
    def test_list_users_empty(self, client):
        resp = client.get("/users/")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_users(self, client, sample_user):
        resp = client.get("/users/")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_list_users_pagination(self, client):
        for i in range(5):
            client.post("/users/", json={
                "firstname": f"User{i}",
                "lastname": "Test",
                "email": f"user{i}@example.com",
            })
        resp = client.get("/users/?skip=2&limit=2")
        assert resp.status_code == 200
        assert len(resp.json()) == 2


# ===================== Scores =====================

class TestCreateScore:
    def test_create_score(self, client, sample_user):
        resp = client.post("/scores/", json={
            "user_id": sample_user["id"],
            "game1_score": 95,
            "total_score": 95,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["game1_score"] == 95
        assert data["total_score"] == 95
        assert data["user_id"] == sample_user["id"]
        assert "id" in data

    def test_create_score_defaults(self, client, sample_user):
        """未传的分数默认为 0"""
        resp = client.post("/scores/", json={
            "user_id": sample_user["id"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["game1_score"] == 0
        assert data["game2_score"] == 0
        assert data["total_score"] == 0


class TestGetScore:
    def test_get_score(self, client, sample_score):
        resp = client.get(f"/scores/{sample_score['id']}")
        assert resp.status_code == 200
        assert resp.json()["game1_score"] == 80

    def test_get_score_not_found(self, client):
        resp = client.get("/scores/9999")
        assert resp.status_code == 404


class TestUpdateScore:
    def test_update_score_partial(self, client, sample_score):
        """只更新 game1"""
        resp = client.put(f"/scores/{sample_score['id']}", json={"game1_score": 99})
        assert resp.status_code == 200
        assert resp.json()["game1_score"] == 99
        assert resp.json()["game2_score"] == 70  # 其他不变

    def test_update_score_total(self, client, sample_score):
        resp = client.put(f"/scores/{sample_score['id']}", json={
            "game1_score": 100,
            "total_score": 405,
        })
        assert resp.status_code == 200
        assert resp.json()["game1_score"] == 100
        assert resp.json()["total_score"] == 405

    def test_update_score_not_found(self, client):
        resp = client.put("/scores/9999", json={"game1_score": 50})
        assert resp.status_code == 404


class TestListScoresByUser:
    def test_list_scores_by_user(self, client, sample_user, sample_score):
        resp = client.get(f"/scores/user/{sample_user['id']}")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_list_scores_by_user_empty(self, client, sample_user):
        resp = client.get(f"/scores/user/{sample_user['id']}")
        assert resp.status_code == 200
        assert resp.json() == []


# ===================== Rankings =====================

class TestRankings:
    def _seed_data(self, client):
        """创建多个用户和分数用于排行榜测试"""
        users = []
        for i, (fn, ln, email, g1, g2, total) in enumerate([
            ("Alice", "Wang", "alice@test.com", 90, 80, 170),
            ("Bob", "Li", "bob@test.com", 70, 95, 165),
            ("Charlie", "Doe", "charlie@test.com", 85, 60, 145),
        ]):
            u = client.post("/users/", json={
                "firstname": fn, "lastname": ln, "email": email, "region": "TEST",
            }).json()
            client.post("/scores/", json={
                "user_id": u["id"],
                "game1_score": g1,
                "game2_score": g2,
                "total_score": total,
            })
            users.append(u)
        return users

    def test_ranking_game1(self, client):
        self._seed_data(client)
        resp = client.get("/rankings/game1?limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert data["score_type"] == "game1"
        assert data["total_entries"] == 3
        # Alice (90) 应该是第 1 名
        assert data["rankings"][0]["firstname"] == "Alice"
        assert data["rankings"][0]["rank"] == 1
        assert data["rankings"][0]["score"] == 90

    def test_ranking_game2(self, client):
        self._seed_data(client)
        resp = client.get("/rankings/game2?limit=10")
        assert resp.status_code == 200
        # Bob (95) 应该是第 1 名
        assert resp.json()["rankings"][0]["firstname"] == "Bob"

    def test_ranking_total(self, client):
        self._seed_data(client)
        resp = client.get("/rankings/total?limit=10")
        assert resp.status_code == 200
        # Alice (170) 应该是第 1 名
        assert resp.json()["rankings"][0]["firstname"] == "Alice"
        assert resp.json()["rankings"][0]["score"] == 170

    def test_ranking_limit(self, client):
        self._seed_data(client)
        resp = client.get("/rankings/total?limit=2")
        assert resp.status_code == 200
        assert resp.json()["total_entries"] == 2

    def test_ranking_empty(self, client):
        resp = client.get("/rankings/game1")
        assert resp.status_code == 200
        assert resp.json()["total_entries"] == 0
        assert resp.json()["rankings"] == []

    def test_ranking_invalid_type(self, client):
        resp = client.get("/rankings/invalid")
        assert resp.status_code == 422

    def test_all_rankings(self, client):
        self._seed_data(client)
        resp = client.get("/rankings/")
        assert resp.status_code == 200
        data = resp.json()
        assert "game1" in data
        assert "game2" in data
        assert "game3" in data
        assert "game4" in data
        assert "game5" in data
        assert "total" in data
        # 验证 game1 排行
        assert data["game1"]["rankings"][0]["firstname"] == "Alice"
        # 验证 total 排行
        assert data["total"]["rankings"][0]["firstname"] == "Alice"


# ===================== LLM =====================

class TestLLMChat:
    def test_chat_no_api_key(self, client):
        """API key 未配置时返回 503"""
        with patch("app.routers.llm.settings") as mock_settings:
            mock_settings.deepseek_api_key = ""
            resp = client.post("/llm/chat", json={"prompt": "Hello"})
            assert resp.status_code == 503

    def test_chat_success(self, client):
        """Mock LLM 调用"""
        with patch("app.routers.llm.chat", return_value="Hi there!") as mock_chat, \
             patch("app.routers.llm.settings") as mock_settings:
            mock_settings.deepseek_api_key = "fake-key"
            resp = client.post("/llm/chat", json={"prompt": "Hello"})
            assert resp.status_code == 200
            assert resp.json()["reply"] == "Hi there!"
            mock_chat.assert_called_once_with("Hello", model="deepseek-chat")

    def test_chat_custom_model(self, client):
        with patch("app.routers.llm.chat", return_value="response") as mock_chat, \
             patch("app.routers.llm.settings") as mock_settings:
            mock_settings.deepseek_api_key = "fake-key"
            resp = client.post("/llm/chat", json={
                "prompt": "Test",
                "model": "deepseek-reasoner",
            })
            assert resp.status_code == 200
            mock_chat.assert_called_once_with("Test", model="deepseek-reasoner")
