"""
测试配置：使用 SQLite 内存数据库，不依赖 PostgreSQL。
在导入 app 之前先覆盖 DATABASE_URL 环境变量。
"""
import os

# ⚠️ 必须在导入 app 之前设置，否则 main.py 会尝试连接 PostgreSQL
os.environ["DATABASE_URL"] = "sqlite://"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app

# SQLite 内存数据库用于测试
engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

# SQLite 默认不启用外键约束，需要手动开启
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_database():
    """每个测试前重建所有表，测试后清理。"""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def sample_user(client):
    """创建一个示例用户并返回响应数据。"""
    resp = client.post("/users/", json={
        "firstname": "Alice",
        "lastname": "Wang",
        "email": "alice@example.com",
        "region": "MENA",
    })
    assert resp.status_code == 200
    return resp.json()


@pytest.fixture()
def sample_score(client, sample_user):
    """创建一个示例分数并返回响应数据。"""
    resp = client.post("/scores/", json={
        "user_id": sample_user["id"],
        "game1_score": 80,
        "game2_score": 70,
        "game3_score": 90,
        "game4_score": 60,
        "game5_score": 85,
        "total_score": 385,
    })
    assert resp.status_code == 200
    return resp.json()
