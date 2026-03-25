"""
AWS 后端集成测试 - 测试部署在 AWS 上的真实服务

使用方法:
    export AWS_API_URL=http://cyber-ai-festival-alb-xxx.ap-south-1.elb.amazonaws.com
    export AWS_API_KEY=tMuIZgmb3m3QAZqclgnJQMLAR-zgBRVktitxzpF0LFE
    python -m pytest tests/test_aws_integration.py -v

或者直接运行:
    python tests/test_aws_integration.py
"""
import os
import sys
import uuid

import requests

# 从环境变量或默认值获取配置
AWS_API_URL = os.getenv("AWS_API_URL", "http://cyber-ai-festival-alb-2006617150.ap-south-1.elb.amazonaws.com")
AWS_API_KEY = os.getenv("AWS_API_KEY", "tMuIZgmb3m3QAZqclgnJQMLAR-zgBRVktitxzpF0LFE")

# 确保 URL 不以 / 结尾
AWS_API_URL = AWS_API_URL.rstrip("/")


def get_headers():
    """获取带认证的请求头"""
    return {
        "X-API-Key": AWS_API_KEY,
        "Content-Type": "application/json",
    }


def test_health_check():
    """测试健康检查端点（无需认证）"""
    resp = requests.get(f"{AWS_API_URL}/health", timeout=10)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    print(f"✅ Health check: {resp.json()}")


def test_no_api_key_returns_422():
    """测试无 API Key 返回 422"""
    resp = requests.get(f"{AWS_API_URL}/users/", timeout=10)
    assert resp.status_code == 422
    print(f"✅ No API Key returns 422")


def test_invalid_api_key_returns_401():
    """测试错误 API Key 返回 401"""
    headers = {"X-API-Key": "wrong-key"}
    resp = requests.get(f"{AWS_API_URL}/users/", headers=headers, timeout=10)
    assert resp.status_code == 401
    print(f"✅ Invalid API Key returns 401")


# 全局列表，记录需要清理的测试用户ID
test_user_ids = []


def cleanup_test_users():
    """清理所有测试创建的用户"""
    print(f"\n🧹 Cleaning up {len(test_user_ids)} test users...")
    for user_id in list(test_user_ids):  # 使用 list 副本避免修改迭代中的列表
        try:
            resp = requests.delete(
                f"{AWS_API_URL}/users/{user_id}",
                headers=get_headers(),
                timeout=10
            )
            if resp.status_code == 200:
                print(f"  🗑️  Deleted user {user_id}")
                test_user_ids.remove(user_id)
            elif resp.status_code == 404:
                print(f"  ℹ️  User {user_id} already deleted")
                test_user_ids.remove(user_id)
            else:
                print(f"  ⚠️  Failed to delete user {user_id}: {resp.status_code}")
        except Exception as e:
            print(f"  ⚠️  Error deleting user {user_id}: {e}")


def test_create_user():
    """测试创建用户"""
    unique_email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    resp = requests.post(
        f"{AWS_API_URL}/users/",
        headers=get_headers(),
        json={
            "firstname": "Test",
            "lastname": "User",
            "email": unique_email,
            "region": "APAC",
        },
        timeout=10,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["firstname"] == "Test"
    assert data["email"] == unique_email
    test_user_ids.append(data['id'])  # 记录用于清理
    print(f"✅ Create user: id={data['id']}, email={data['email']}")


def test_list_users():
    """测试获取用户列表"""
    resp = requests.get(f"{AWS_API_URL}/users/", headers=get_headers(), timeout=10)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    print(f"✅ List users: {len(data)} users found")


def test_user_score_workflow():
    """测试用户和分数的完整流程：创建用户 -> 获取用户 -> 更新分数 -> 获取分数"""
    # 1. 创建用户
    unique_email = f"workflow_{uuid.uuid4().hex[:8]}@example.com"
    create_resp = requests.post(
        f"{AWS_API_URL}/users/",
        headers=get_headers(),
        json={
            "firstname": "Workflow",
            "lastname": "Test",
            "email": unique_email,
            "region": "TEST",
        },
        timeout=10,
    )
    assert create_resp.status_code == 200
    user_id = create_resp.json()["id"]
    test_user_ids.append(user_id)  # 记录用于清理
    print(f"✅ Created user: id={user_id}")

    # 2. 获取用户
    get_resp = requests.get(f"{AWS_API_URL}/users/{user_id}", headers=get_headers(), timeout=10)
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == user_id
    print(f"✅ Get user: id={user_id}")

    # 3. 更新分数
    update_resp = requests.put(
        f"{AWS_API_URL}/scores/{user_id}",
        headers=get_headers(),
        json={
            "game1_score": 80,
            "game2_score": 70,
            "game3_score": 90,
            "game4_score": 60,
            "game5_score": 85,
        },
        timeout=10,
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["total_score"] == 385
    print(f"✅ Update score: total=385")

    # 4. 获取分数
    score_resp = requests.get(f"{AWS_API_URL}/scores/{user_id}", headers=get_headers(), timeout=10)
    assert score_resp.status_code == 200
    assert score_resp.json()["user_id"] == user_id
    print(f"✅ Get score: user_id={user_id}")


def test_rankings():
    """测试排行榜"""
    resp = requests.get(f"{AWS_API_URL}/rankings/", headers=get_headers(), timeout=10)
    assert resp.status_code == 200
    data = resp.json()
    assert "game1" in data
    assert "total" in data
    print(f"✅ Rankings: {len(data)} score types returned")


def test_userscores():
    """测试 userscores 端点"""
    resp = requests.get(f"{AWS_API_URL}/users/userscores", headers=get_headers(), timeout=10)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    print(f"✅ Userscores: {len(data)} entries returned")


def test_login():
    """测试登录功能"""
    # 先创建一个用户
    unique_email = f"login_{uuid.uuid4().hex[:8]}@example.com"
    create_resp = requests.post(
        f"{AWS_API_URL}/users/",
        headers=get_headers(),
        json={
            "firstname": "Login",
            "lastname": "Test",
            "email": unique_email,
        },
        timeout=10,
    )
    assert create_resp.status_code == 200
    user_id = create_resp.json()["id"]
    test_user_ids.append(user_id)  # 记录用于清理

    # 测试登录
    resp = requests.post(
        f"{AWS_API_URL}/users/login",
        headers=get_headers(),
        json={
            "email": unique_email,
            "firstname": "Login",
        },
        timeout=10,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == user_id
    print(f"✅ Login: user_id={data['id']}")


def test_update_and_delete_user():
    """测试更新和删除用户"""
    # 1. 创建用户
    unique_email = f"update_{uuid.uuid4().hex[:8]}@example.com"
    create_resp = requests.post(
        f"{AWS_API_URL}/users/",
        headers=get_headers(),
        json={
            "firstname": "Update",
            "lastname": "Test",
            "email": unique_email,
            "region": "APAC",
        },
        timeout=10,
    )
    assert create_resp.status_code == 200
    user_id = create_resp.json()["id"]
    test_user_ids.append(user_id)  # 记录用于清理
    print(f"✅ Created user for update test: id={user_id}")

    # 2. 更新用户
    update_resp = requests.put(
        f"{AWS_API_URL}/users/{user_id}",
        headers=get_headers(),
        json={
            "firstname": "Updated",
            "region": "EU",
        },
        timeout=10,
    )
    assert update_resp.status_code == 200
    data = update_resp.json()
    assert data["firstname"] == "Updated"
    assert data["region"] == "EU"
    assert data["lastname"] == "Test"  # 未更新的字段保持不变
    print(f"✅ Updated user: firstname={data['firstname']}, region={data['region']}")

    # 3. 删除用户
    delete_resp = requests.delete(f"{AWS_API_URL}/users/{user_id}", headers=get_headers(), timeout=10)
    assert delete_resp.status_code == 200
    assert delete_resp.json()["message"] == "User deleted"
    print(f"✅ Deleted user: id={user_id}")

    # 从清理列表中移除（已经被删除了）
    if user_id in test_user_ids:
        test_user_ids.remove(user_id)

    # 4. 确认用户已删除
    get_resp = requests.get(f"{AWS_API_URL}/users/{user_id}", headers=get_headers(), timeout=10)
    assert get_resp.status_code == 404
    print(f"✅ Confirmed user deleted: 404 returned")


def test_single_rankings():
    """测试单个排行榜"""
    # 先创建用户并更新分数
    unique_email = f"rank_{uuid.uuid4().hex[:8]}@example.com"
    create_resp = requests.post(
        f"{AWS_API_URL}/users/",
        headers=get_headers(),
        json={
            "firstname": "Rank",
            "lastname": "Test",
            "email": unique_email,
        },
        timeout=10,
    )
    assert create_resp.status_code == 200
    user_id = create_resp.json()["id"]
    test_user_ids.append(user_id)  # 记录用于清理

    # 更新分数
    requests.put(
        f"{AWS_API_URL}/scores/{user_id}",
        headers=get_headers(),
        json={
            "game1_score": 95,
            "game2_score": 85,
            "game3_score": 75,
            "game4_score": 90,
            "game5_score": 80,
        },
        timeout=10,
    )

    # 测试各个排行榜
    for score_type in ["game1", "game2", "game3", "game4", "game5", "total"]:
        resp = requests.get(f"{AWS_API_URL}/rankings/{score_type}?limit=10", headers=get_headers(), timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        assert data["score_type"] == score_type
        assert isinstance(data["rankings"], list)
        print(f"✅ Ranking {score_type}: {data['total_entries']} entries")


def test_error_cases():
    """测试错误场景"""
    # 1. 404: 获取不存在的用户
    resp = requests.get(f"{AWS_API_URL}/users/99999", headers=get_headers(), timeout=10)
    assert resp.status_code == 404
    print("✅ Error case: User not found (404)")

    # 2. 404: 获取不存在的分数
    resp = requests.get(f"{AWS_API_URL}/scores/99999", headers=get_headers(), timeout=10)
    assert resp.status_code == 404
    print("✅ Error case: Score not found (404)")

    # 3. 409: 重复 email
    unique_email = f"dup_{uuid.uuid4().hex[:8]}@example.com"
    # 第一次创建成功
    resp1 = requests.post(
        f"{AWS_API_URL}/users/",
        headers=get_headers(),
        json={
            "firstname": "Dup",
            "lastname": "Test",
            "email": unique_email,
        },
        timeout=10,
    )
    assert resp1.status_code == 200
    test_user_ids.append(resp1.json()['id'])  # 记录第一个用户用于清理

    # 第二次创建失败（409）
    resp2 = requests.post(
        f"{AWS_API_URL}/users/",
        headers=get_headers(),
        json={
            "firstname": "Dup2",
            "lastname": "Test2",
            "email": unique_email,
        },
        timeout=10,
    )
    assert resp2.status_code == 409
    print("✅ Error case: Duplicate email (409)")

    # 4. 422: 无效的排行榜类型
    resp = requests.get(f"{AWS_API_URL}/rankings/invalid_type", headers=get_headers(), timeout=10)
    assert resp.status_code == 422
    print("✅ Error case: Invalid ranking type (422)")

    # 5. 401: 登录失败（错误的 firstname）
    unique_email2 = f"login_fail_{uuid.uuid4().hex[:8]}@example.com"
    create_resp = requests.post(
        f"{AWS_API_URL}/users/",
        headers=get_headers(),
        json={
            "firstname": "Correct",
            "lastname": "Name",
            "email": unique_email2,
        },
        timeout=10,
    )
    if create_resp.status_code == 200:
        test_user_ids.append(create_resp.json()['id'])  # 记录用于清理
    resp = requests.post(
        f"{AWS_API_URL}/users/login",
        headers=get_headers(),
        json={
            "email": unique_email2,
            "firstname": "Wrong",
        },
        timeout=10,
    )
    assert resp.status_code == 401
    print("✅ Error case: Login wrong firstname (401)")


def test_total_score_auto_calculation():
    """测试总分自动计算的各种场景"""
    unique_email = f"calc_{uuid.uuid4().hex[:8]}@example.com"
    create_resp = requests.post(
        f"{AWS_API_URL}/users/",
        headers=get_headers(),
        json={
            "firstname": "Calc",
            "lastname": "Test",
            "email": unique_email,
        },
        timeout=10,
    )
    assert create_resp.status_code == 200
    user_id = create_resp.json()["id"]
    test_user_ids.append(user_id)  # 记录用于清理

    # 场景1: 初始分数为0
    score_resp = requests.get(f"{AWS_API_URL}/scores/{user_id}", headers=get_headers(), timeout=10)
    assert score_resp.json()["total_score"] == 0
    print("✅ Auto-calc: Initial total = 0")

    # 场景2: 更新单个分数
    requests.put(
        f"{AWS_API_URL}/scores/{user_id}",
        headers=get_headers(),
        json={"game1_score": 50},
        timeout=10,
    )
    score_resp = requests.get(f"{AWS_API_URL}/scores/{user_id}", headers=get_headers(), timeout=10)
    assert score_resp.json()["total_score"] == 50
    print("✅ Auto-calc: After game1=50, total = 50")

    # 场景3: 更新多个分数
    requests.put(
        f"{AWS_API_URL}/scores/{user_id}",
        headers=get_headers(),
        json={
            "game1_score": 10,
            "game2_score": 20,
            "game3_score": 30,
            "game4_score": 40,
            "game5_score": 50,
        },
        timeout=10,
    )
    score_resp = requests.get(f"{AWS_API_URL}/scores/{user_id}", headers=get_headers(), timeout=10)
    assert score_resp.json()["total_score"] == 150  # 10+20+30+40+50
    print("✅ Auto-calc: After all games, total = 150")

    # 场景4: 部分更新（未传的分数保持不变）
    requests.put(
        f"{AWS_API_URL}/scores/{user_id}",
        headers=get_headers(),
        json={"game1_score": 100},
        timeout=10,
    )
    score_resp = requests.get(f"{AWS_API_URL}/scores/{user_id}", headers=get_headers(), timeout=10)
    # game1=100, game2=20, game3=30, game4=40, game5=50
    assert score_resp.json()["total_score"] == 240
    print("✅ Auto-calc: Partial update, total = 240")


def run_all_tests():
    """运行所有测试"""
    print(f"\n🧪 Testing AWS Backend: {AWS_API_URL}\n")

    tests_passed = 0
    tests_failed = 0

    # 基础测试
    try:
        test_health_check()
        tests_passed += 1
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        tests_failed += 1

    # API Key 认证测试
    try:
        test_no_api_key_returns_422()
        tests_passed += 1
    except Exception as e:
        print(f"❌ No API Key test failed: {e}")
        tests_failed += 1

    try:
        test_invalid_api_key_returns_401()
        tests_passed += 1
    except Exception as e:
        print(f"❌ Invalid API Key test failed: {e}")
        tests_failed += 1

    # 用户相关测试
    try:
        test_list_users()
        tests_passed += 1
    except Exception as e:
        print(f"❌ List users failed: {e}")
        tests_failed += 1

    try:
        test_create_user()
        tests_passed += 1
    except Exception as e:
        print(f"❌ Create user failed: {e}")
        tests_failed += 1

    try:
        test_user_score_workflow()
        tests_passed += 1
    except Exception as e:
        print(f"❌ User score workflow failed: {e}")
        tests_failed += 1

    try:
        test_update_and_delete_user()
        tests_passed += 1
    except Exception as e:
        print(f"❌ Update and delete user failed: {e}")
        tests_failed += 1

    # 排行榜测试
    try:
        test_rankings()
        tests_passed += 1
    except Exception as e:
        print(f"❌ Rankings failed: {e}")
        tests_failed += 1

    try:
        test_single_rankings()
        tests_passed += 1
    except Exception as e:
        print(f"❌ Single rankings failed: {e}")
        tests_failed += 1

    try:
        test_userscores()
        tests_passed += 1
    except Exception as e:
        print(f"❌ Userscores failed: {e}")
        tests_failed += 1

    # 登录测试
    try:
        test_login()
        tests_passed += 1
    except Exception as e:
        print(f"❌ Login failed: {e}")
        tests_failed += 1

    # 错误场景测试
    try:
        test_error_cases()
        tests_passed += 1
    except Exception as e:
        print(f"❌ Error cases failed: {e}")
        tests_failed += 1

    # 自动计算测试
    try:
        test_total_score_auto_calculation()
        tests_passed += 1
    except Exception as e:
        print(f"❌ Total score auto calculation failed: {e}")
        tests_failed += 1

    # 打印结果
    print(f"\n{'='*50}")
    print(f"✅ Passed: {tests_passed}")
    print(f"❌ Failed: {tests_failed}")
    print(f"{'='*50}\n")

    # 清理测试数据
    cleanup_test_users()

    return tests_failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)