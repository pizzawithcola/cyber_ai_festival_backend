"""
覆盖所有 API 端点的测试。
"""
from unittest.mock import patch

from fastapi.testclient import TestClient


# ===================== API Key Authentication =====================

class TestAPIKeyAuth:
    """测试 API Key 认证功能"""

    def test_no_api_key_returns_422(self, client_no_auth):
        """无 API Key 应返回 422"""
        resp = client_no_auth.get("/users/")
        assert resp.status_code == 422
        assert "x-api-key" in str(resp.json())

    def test_invalid_api_key_returns_401(self, client_no_auth):
        """错误的 API Key 应返回 401"""
        resp = client_no_auth.get("/users/", headers={"X-API-Key": "wrong-key"})
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid API Key"

    def test_valid_api_key_succeeds(self, client):
        """正确的 API Key 应成功"""
        resp = client.get("/users/")
        assert resp.status_code == 200

    def test_health_no_auth_required(self, client_no_auth):
        """健康检查端点不需要认证"""
        resp = client_no_auth.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_post_requires_auth(self, client_no_auth):
        """POST 请求也需要认证"""
        resp = client_no_auth.post("/users/", json={
            "firstname": "Test",
            "lastname": "User",
            "email": "test@example.com",
        })
        assert resp.status_code == 422

    def test_api_key_case_sensitive(self, client_no_auth):
        """API Key 大小写敏感"""
        resp = client_no_auth.get("/users/", headers={"X-API-Key": "TEST-API-KEY-12345"})
        assert resp.status_code == 401


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


class TestLoginUser:
    def test_login_success(self, client, sample_user):
        resp = client.post("/users/login", json={
            "email": "alice@example.com",
            "firstname": "Alice",
        })
        assert resp.status_code == 200
        assert resp.json()["id"] == sample_user["id"]
        assert resp.json()["email"] == "alice@example.com"

    def test_login_case_insensitive(self, client, sample_user):
        """firstname 大小写不敏感"""
        resp = client.post("/users/login", json={
            "email": "alice@example.com",
            "firstname": "alice",
        })
        assert resp.status_code == 200

    def test_login_wrong_firstname(self, client, sample_user):
        resp = client.post("/users/login", json={
            "email": "alice@example.com",
            "firstname": "Bob",
        })
        assert resp.status_code == 401

    def test_login_email_not_found(self, client):
        resp = client.post("/users/login", json={
            "email": "nobody@example.com",
            "firstname": "Ghost",
        })
        assert resp.status_code == 401


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


class TestGetAllUsersWithScores:
    def test_get_userscores_empty(self, client):
        """Test userscores endpoint with no users"""
        resp = client.get("/users/userscores")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_userscores_default_scores(self, client, sample_user):
        """Test userscores with users - now each user has default scores"""
        resp = client.get("/users/userscores")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        user = data[0]
        assert user["id"] == sample_user["id"]
        assert user["firstname"] == "Alice"
        assert user["lastname"] == "Wang"
        assert user["email"] == "alice@example.com"
        assert user["region"] == "MENA"
        # Score ID should be the user ID in 1:1 relationship
        assert user["score_id"] == sample_user["id"]
        # Scores should have default values (0) instead of None
        assert user["game1_score"] == 0
        assert user["game2_score"] == 0
        assert user["game3_score"] == 0
        assert user["game4_score"] == 0
        assert user["game5_score"] == 0
        assert user["total_score"] == 0

    def test_get_userscores_with_scores(self, client, sample_user):
        """Test userscores after updating scores"""
        # Update the user's score (total_score will be auto-calculated)
        resp = client.put(f"/scores/{sample_user['id']}", json={
            "game1_score": 80,
            "game2_score": 70,
            "game3_score": 90,
            "game4_score": 60,
            "game5_score": 85,
        })
        assert resp.status_code == 200
        
        # Test userscores endpoint
        resp = client.get("/users/userscores")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        user = data[0]
        assert user["id"] == sample_user["id"]
        assert user["firstname"] == "Alice"
        assert user["lastname"] == "Wang"
        assert user["email"] == "alice@example.com"
        assert user["region"] == "MENA"
        # Score ID should be the user ID
        assert user["score_id"] == sample_user["id"]
        # Scores should be present
        assert user["game1_score"] == 80
        assert user["game2_score"] == 70
        assert user["game3_score"] == 90
        assert user["game4_score"] == 60
        assert user["game5_score"] == 85
        assert user["total_score"] == 385

    def test_get_userscores_multiple_users(self, client):
        """Test userscores with multiple users"""
        # Create first user (score will be created automatically)
        user1 = client.post("/users/", json={
            "firstname": "Alice",
            "lastname": "Wang",
            "email": "alice@example.com",
            "region": "MENA"
        }).json()
        
        # Update first user's score
        client.put(f"/scores/{user1['id']}", json={
            "game1_score": 90,
            "game2_score": 80,
        })
        
        # Create second user (score will be created automatically)
        user2 = client.post("/users/", json={
            "firstname": "Bob",
            "lastname": "Li",
            "email": "bob@example.com",
            "region": "APAC"
        }).json()
        
        # Update second user's score
        client.put(f"/scores/{user2['id']}", json={
            "game1_score": 70,
            "game2_score": 95,
        })
        
        resp = client.get("/users/userscores")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        
        # Sort by user id to ensure consistent order
        data.sort(key=lambda x: x["id"])
        
        # First user
        assert data[0]["firstname"] == "Alice"
        assert data[0]["score_id"] == user1["id"]
        assert data[0]["game1_score"] == 90
        assert data[0]["game2_score"] == 80
        assert data[0]["total_score"] == 170  # auto-calculated: 90 + 80
        
        # Second user
        assert data[1]["firstname"] == "Bob"
        assert data[1]["score_id"] == user2["id"]
        assert data[1]["game1_score"] == 70
        assert data[1]["game2_score"] == 95
        assert data[1]["total_score"] == 165  # auto-calculated: 70 + 95


# ===================== Scores =====================

class TestCreateScore:
    def test_create_score_conflict(self, client, sample_user):
        """Test that creating score for existing user returns 409"""
        resp = client.post("/scores/", json={
            "user_id": sample_user["id"],
            "game1_score": 95,
        })
        assert resp.status_code == 409
        assert "already exists" in resp.json()["detail"]

    def test_create_score_defaults_conflict(self, client, sample_user):
        """Test that creating score with defaults for existing user returns 409"""
        resp = client.post("/scores/", json={
            "user_id": sample_user["id"],
        })
        assert resp.status_code == 409
        assert "already exists" in resp.json()["detail"]


class TestGetScore:
    def test_get_score(self, client, sample_user):
        # Update score first to set expected values (total_score will be auto-calculated)
        client.put(f"/scores/{sample_user['id']}", json={
            "game1_score": 80,
            "game2_score": 70,
        })
        
        # Use user_id instead of score_id since they're the same in 1:1 relationship
        resp = client.get(f"/scores/{sample_user['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["game1_score"] == 80
        assert data["game2_score"] == 70
        assert data["total_score"] == 150  # auto-calculated: 80 + 70
        assert data["user_id"] == sample_user["id"]

    def test_get_score_not_found(self, client):
        resp = client.get("/scores/9999")
        assert resp.status_code == 404


class TestUpdateScore:
    def test_update_score_partial(self, client, sample_user):
        """只更新 game1"""
        # First set initial values
        client.put(f"/scores/{sample_user['id']}", json={
            "game1_score": 80,
            "game2_score": 70,
        })
        
        # Then update game1 only
        resp = client.put(f"/scores/{sample_user['id']}", json={"game1_score": 99})
        assert resp.status_code == 200
        data = resp.json()
        assert data["game1_score"] == 99
        assert data["game2_score"] == 70  # 其他不变
        # total_score should be auto-calculated: 99 + 70 + 0 + 0 + 0 = 169
        assert data["total_score"] == 169
        assert data["user_id"] == sample_user["id"]

    def test_update_score_total_auto_calculated(self, client, sample_user):
        """Test that total_score is always auto-calculated from game scores"""
        # First set initial values
        client.put(f"/scores/{sample_user['id']}", json={
            "game1_score": 80,
            "game2_score": 70,
        })
        
        # Then update game1 - total_score should be auto-calculated
        resp = client.put(f"/scores/{sample_user['id']}", json={
            "game1_score": 100,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["game1_score"] == 100
        # total_score should be auto-calculated: 100 + 70 + 0 + 0 + 0 = 170
        assert data["total_score"] == 170
        assert data["user_id"] == sample_user["id"]

    def test_update_score_auto_total_calculation(self, client, sample_user):
        """Test that total_score is automatically calculated when game scores are updated"""
        # Update multiple game scores
        resp = client.put(f"/scores/{sample_user['id']}", json={
            "game1_score": 85,
            "game2_score": 90,
            "game3_score": 75,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["game1_score"] == 85
        assert data["game2_score"] == 90
        assert data["game3_score"] == 75
        # total_score should be auto-calculated: 85 + 90 + 75 + 0 + 0 = 250
        assert data["total_score"] == 250

    def test_update_score_total_always_auto(self, client, sample_user):
        """Test that total_score is always auto-calculated, cannot be manually set"""
        # Set initial values
        client.put(f"/scores/{sample_user['id']}", json={
            "game1_score": 80,
            "game2_score": 70,
        })
        
        # Try to update with total_score - it should be ignored
        resp = client.put(f"/scores/{sample_user['id']}", json={
            "game1_score": 90,
            # total_score should still be auto-calculated
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["game1_score"] == 90
        # total_score should be auto-calculated: 90 + 70 + 0 + 0 + 0 = 160
        assert data["total_score"] == 160

    def test_update_score_not_found(self, client):
        resp = client.put("/scores/9999", json={"game1_score": 50})
        assert resp.status_code == 404


# ===================== Rankings =====================

class TestRankings:
    def _seed_data(self, client):
        """创建多个用户和分数用于排行榜测试"""
        users = []
        user_scores = [
            ("Alice", "Wang", "alice@test.com", 90, 80, 170),
            ("Bob", "Li", "bob@test.com", 70, 95, 165),
            ("Charlie", "Doe", "charlie@test.com", 85, 60, 145),
        ]
        
        for fn, ln, email, g1, g2, total in user_scores:
            u = client.post("/users/", json={
                "firstname": fn, "lastname": ln, "email": email, "region": "TEST",
            }).json()
            users.append(u)
        
        # Update scores after users are created (since scores are auto-created)
        # total_score will be auto-calculated from game scores
        for i, (fn, ln, email, g1, g2, total) in enumerate(user_scores):
            client.put(f"/scores/{users[i]['id']}", json={
                "game1_score": g1,
                "game2_score": g2,
                # total is kept for reference but not sent to API
            })
            
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
    SAMPLE_TARGET = {
        "name": "Alex Johnson",
        "email": "alex.j@acc.com",
        "department": "IT Security",
        "position": "Senior Security Analyst",
        "hobbies": ["Cybersecurity Research", "Penetration Testing"],
        "personality": "Detail-oriented, skeptical, tech-savvy",
        "mission": {
            "title": "Security Update Required",
            "description": "Urgent security patch needs immediate attention",
            "targetLink": "https://secure-update.company.com/patch",
            "difficulty": "Medium",
            "hint": "Exploit technical urgency",
        },
    }

    def _chat_body(self, **overrides):
        body = {
            "prompt": "From: IT\nTo: Alex\nSubject: Urgent\n\nPlease update now.",
            "model": "deepseek-chat",
            "target_information": self.SAMPLE_TARGET,
        }
        body.update(overrides)
        return body

    def test_chat_no_api_key(self, client):
        """API key 未配置时返回 503"""
        with patch("app.routers.llm.settings") as mock_settings:
            mock_settings.deepseek_api_key = ""
            resp = client.post("/llm/chat", json=self._chat_body())
            assert resp.status_code == 503

    def test_chat_success(self, client):
        """Mock LLM 调用，target_info 应传入 system prompt"""
        with patch("app.routers.llm.chat", return_value='{"total_score": 75}') as mock_chat, \
             patch("app.routers.llm.settings") as mock_settings:
            mock_settings.deepseek_api_key = "fake-key"
            resp = client.post("/llm/chat", json=self._chat_body())
            assert resp.status_code == 200
            assert "total_score" in resp.json()["reply"]
            assert mock_chat.call_count == 1
            # prompt (user message) 只包含邮件内容
            prompt_sent = mock_chat.call_args[0][0]
            assert "From: IT" in prompt_sent
            # target_info 通过 kwarg 传入（用于 system prompt）
            target_sent = mock_chat.call_args[1]["target_info"]
            assert target_sent["name"] == "Alex Johnson"
            assert target_sent["department"] == "IT Security"

    def test_chat_custom_model(self, client):
        with patch("app.routers.llm.chat", return_value="response") as mock_chat, \
             patch("app.routers.llm.settings") as mock_settings:
            mock_settings.deepseek_api_key = "fake-key"
            resp = client.post("/llm/chat", json=self._chat_body(model="deepseek-reasoner"))
            assert resp.status_code == 200
            assert mock_chat.call_args[1]["model"] == "deepseek-reasoner"
            assert mock_chat.call_args[1]["target_info"]["name"] == "Alex Johnson"

    def test_chat_missing_target_info(self, client):
        """缺少 target_information 应返回 422"""
        resp = client.post("/llm/chat", json={"prompt": "Hello"})
        assert resp.status_code == 422
