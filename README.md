# Cyber AI Festival Backend

FastAPI 后端：用户登记、分数管理、排行榜、DeepSeek LLM 调用。数据库 PostgreSQL，后续可部署至 AWS。

## 技术栈

- **框架**: FastAPI 0.109+
- **数据库**: PostgreSQL + SQLAlchemy 2.x + Alembic
- **LLM**: DeepSeek API（OpenAI 兼容）
- **测试**: pytest + SQLite 内存数据库
- **日志**: Python logging → 终端 + `logs/app.log`（自动轮转）

## 本地开发

### 1. 环境要求

- Python 3.11+
- PostgreSQL（本地或 Docker）

### 2. 安装依赖

```bash
cd /path/to/cyber_ai_festival_be
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
brew services start postgresql@16
```

### 3. 配置环境变量

在项目根目录创建 `.env` 文件：

```env
DATABASE_URL=postgresql://user:password@localhost:5432/cyber_ai_festival
DEEPSEEK_API_KEY=your-api-key
DEEPSEEK_BASE_URL=https://api.deepseek.com
LOG_LEVEL=INFO
API_KEY=your-static-api-key
```

| 变量 | 说明 | 示例 |
|------|------|------|
| DATABASE_URL | PostgreSQL 连接字符串 | `postgresql://postgres:xxx@host:5432/postgres` |
| DEEPSEEK_API_KEY | DeepSeek API 密钥 | `sk-xxx` |
| DEEPSEEK_BASE_URL | DeepSeek API 地址 | `https://api.deepseek.com` |
| LOG_LEVEL | 日志级别 | `INFO`, `DEBUG`, `WARNING` |
| API_KEY | 静态 API 密钥 | `tMuIZgmb3m3QAZqclgnJQMLAR-zgBRVktitxzpF0LFE` |

### 4. 数据库迁移

```bash
alembic upgrade head
```

### 5. 启动服务

```bash
uvicorn app.main:app --reload --port 8848
```

- Swagger 文档: http://127.0.0.1:8848/docs
- 健康检查: http://127.0.0.1:8848/health

### 6. 运行测试

```bash
pytest tests/ -v
```

---

## API 认证

> ⚠️ **重要**: 所有 API 调用（除 `/health` 外）都需要携带 API Key。

### 请求头格式

```http
X-API-Key: tMuIZgmb3m3QAZqclgnJQMLAR-zgBRVktitxzpF0LFE
```

### 示例

```bash
# 需要认证的请求
curl -H "X-API-Key: tMuIZgmb3m3QAZqclgnJQMLAR-zgBRVktitxzpF0LFE" \
  http://127.0.0.1:8848/users/

# 健康检查（无需认证）
curl http://127.0.0.1:8848/health
```

### 认证行为

| 场景 | HTTP 状态码 | 说明 |
|------|------------|------|
| 无 X-API-Key | 422 | 缺少必需字段 |
| 错误的 API Key | 401 | 无效的 API Key |
| 正确的 API Key | 200 | 认证成功 |

### 前端集成

前端应用在发送请求时需在 HTTP 头中添加 `X-API-Key`：

```javascript
const API_KEY = 'tMuIZgmb3m3QAZqclgnJQMLAR-zgBRVktitxzpF0LFE';

fetch('http://your-backend-url/users/', {
  headers: {
    'X-API-Key': API_KEY,
    'Content-Type': 'application/json'
  }
});
```

---

## API 参考

Base URL: `http://127.0.0.1:8848` (本地) 或 `http://{ALB_DNS}` (AWS)

> ⚠️ 所有端点（除 `/health`）都需要 `X-API-Key` 请求头认证。

### 目录

| 模块 | 方法 | 路径 | 说明 |
|------|------|------|------|
| Health | GET | `/health` | 健康检查 |
| Users | POST | `/users/` | 创建用户 |
| Users | GET | `/users/{user_id}` | 获取用户 |
| Users | PUT | `/users/{user_id}` | 更新用户 |
| Users | DELETE | `/users/{user_id}` | 删除用户 |
| Users | GET | `/users/` | 用户列表 |
| Users | GET | `/users/userscores` | 所有用户成绩 |
| Scores | POST | `/scores/` | 创建分数 |
| Scores | GET | `/scores/{user_id}` | 获取分数 |
| Scores | PUT | `/scores/{user_id}` | 更新分数 |
| Rankings | GET | `/rankings/{score_type}` | 单个排行榜 |
| Rankings | GET | `/rankings/` | 全部排行榜 |
| LLM | POST | `/llm/chat` | LLM 对话 |

---

### Health

#### `GET /health`

健康检查。

**Response** `200`
```json
{ "status": "ok" }
```

---

### Users

#### `POST /users/` — 创建用户

**Request Body**
```json
{
  "firstname": "Alice",
  "lastname": "Wang",
  "email": "alice@example.com",
  "region": "MENA"            // 可选
}
```

**Response** `200`
```json
{
  "id": 1,
  "firstname": "Alice",
  "lastname": "Wang",
  "email": "alice@example.com",
  "region": "MENA",
  "created_at": "2026-02-15T22:00:00+00:00"
}
```

**Error** `409` — email 已存在
```json
{
  "detail": {
    "message": "User with this email already exists",
    "user_id": 1
  }
}
```

---

#### `GET /users/{user_id}` — 获取用户

**Response** `200` — 同上 UserResponse

**Error** `404`
```json
{ "detail": "User not found" }
```

---

#### `PUT /users/{user_id}` — 更新用户

只需传要修改的字段，未传的保持不变。

**Request Body**（全部字段可选）
```json
{
  "firstname": "Bob",
  "lastname": "Li",
  "email": "bob@example.com",
  "region": "APAC"
}
```

**Response** `200` — 同 UserResponse

**Error** `404` — 用户不存在  
**Error** `409` — email 被其他用户占用

---

#### `DELETE /users/{user_id}` — 删除用户

删除用户及其关联的所有分数（CASCADE）。

**Response** `200`
```json
{ "message": "User deleted", "user_id": 1 }
```

**Error** `404` — 用户不存在

---

#### `GET /users/?skip=0&limit=100` — 用户列表

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| skip | int | 0 | 跳过前 N 条 |
| limit | int | 100 | 返回最多 N 条 |

**Response** `200` — `UserResponse[]`

---

#### `GET /users/userscores` — 所有用户成绩

获取所有用户及其成绩信息，包括成绩ID（即用户ID）、五个游戏的分数和总分。

**Response** `200`
```json
[
  {
    "id": 1,
    "firstname": "Alice",
    "lastname": "Wang",
    "email": "alice@example.com",
    "region": "MENA",
    "score_id": 1,
    "game1_score": 0.0,
    "game2_score": 0.0,
    "game3_score": 0.0,
    "game4_score": 0.0,
    "game5_score": 0.0,
    "total_score": 0.0
  },
  {
    "id": 2,
    "firstname": "Bob",
    "lastname": "Li",
    "email": "bob@example.com",
    "region": "APAC",
    "score_id": 2,
    "game1_score": 95.0,
    "game2_score": 85.0,
    "game3_score": 75.0,
    "game4_score": 90.0,
    "game5_score": 80.0,
    "total_score": 425.0
  }
]
```

**说明**:
- 每个用户创建时自动创建一条分数记录，初始值均为0.0
- `score_id` 字段即为用户ID（1:1关系）
- 所有分数字段均为必填，返回值为浮点数格式

---

### Scores

#### `POST /scores/` — 创建分数

**注意**: 每个用户只能有一条分数记录。用户创建时会自动创建默认分数记录，此接口用于创建新用户的分数（如果尚未存在）。

**Request Body**
```json
{
  "user_id": 1,
  "game1_score": 80,       // 可选，默认 0
  "game2_score": 70,       // 可选，默认 0
  "game3_score": 90,       // 可选，默认 0
  "game4_score": 60,       // 可选，默认 0
  "game5_score": 85        // 可选，默认 0
  // total_score 将自动计算为 game1-game5 的总和
}
```

**Response** `200`
```json
{
  "user_id": 1,
  "game1_score": 80.0,
  "game2_score": 70.0,
  "game3_score": 90.0,
  "game4_score": 60.0,
  "game5_score": 85.0,
  "total_score": 385.0,    // 自动计算
  "created_at": "2026-02-15T22:00:00+00:00"
}
```

**Error** `409` — 分数记录已存在
```json
{ "detail": "Score already exists for user_id=1" }
```

---

#### `GET /scores/{user_id}` — 获取分数

通过用户ID获取分数记录。

**Response** `200` — 同上 ScoreResponse

**Error** `404`
```json
{ "detail": "Score not found" }
```

---

#### `PUT /scores/{user_id}` — 更新分数

只需传要修改的字段，未传的保持不变。`total_score` 将自动计算为五个游戏分数的总和，不可手动设置。

**Request Body**（全部字段可选）
```json
{
  "game1_score": 95,
  "game2_score": 85
  // total_score 会自动计算为 95 + 85 + 0 + 0 + 0 = 180
}
```

**Response** `200` — 同 ScoreResponse

**Error** `404` — 分数不存在

---

### Rankings

#### `GET /rankings/{score_type}?limit=50` — 单个排行榜

`score_type` 可选值：`game1` `game2` `game3` `game4` `game5` `total`

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| limit | int | 50 | 返回前 N 名（1~500） |

**Response** `200`
```json
{
  "score_type": "game1",
  "total_entries": 3,
  "rankings": [
    {
      "rank": 1,
      "user_id": 5,
      "firstname": "Alice",
      "lastname": "Wang",
      "email": "alice@example.com",
      "region": "MENA",
      "score": 98.5
    },
    {
      "rank": 2,
      "user_id": 2,
      "firstname": "Bob",
      "lastname": "Li",
      "email": "bob@example.com",
      "region": "APAC",
      "score": 85.0
    }
  ]
}
```

**Error** `422` — 无效的 score_type

---

#### `GET /rankings/?limit=50` — 全部排行榜

一次返回所有 6 个排行榜（game1~game5 + total）。

**Response** `200`
```json
{
  "game1": { "score_type": "game1", "total_entries": 3, "rankings": [...] },
  "game2": { "score_type": "game2", "total_entries": 3, "rankings": [...] },
  "game3": { "score_type": "game3", "total_entries": 3, "rankings": [...] },
  "game4": { "score_type": "game4", "total_entries": 3, "rankings": [...] },
  "game5": { "score_type": "game5", "total_entries": 3, "rankings": [...] },
  "total": { "score_type": "total", "total_entries": 3, "rankings": [...] }
}
```

---

### LLM

#### `POST /llm/chat` — LLM 对话

**Request Body**
```json
{
  "prompt": "你好，请介绍一下 AI",
  "model": "deepseek-chat"          // 可选，默认 deepseek-chat
}
```

**Response** `200`
```json
{ "reply": "你好！AI 是人工智能的缩写..." }
```

**Error** `503` — API key 未配置
```json
{ "detail": "DeepSeek API key not configured" }
```

---

## 数据模型

### User

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | int | PK, 自增 | 用户 ID |
| firstname | string(128) | 必填 | 名 |
| lastname | string(128) | 必填 | 姓 |
| email | string(256) | 必填, 唯一 | 邮箱 |
| region | string(128) | 可选 | 地区 |
| created_at | datetime | 自动生成 | 创建时间 |

### Score

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| user_id | int | PK, FK → users.id, CASCADE | 用户 ID (主键) |
| game1_score | float | 必填, 默认 0 | 游戏 1 分数 |
| game2_score | float | 必填, 默认 0 | 游戏 2 分数 |
| game3_score | float | 必填, 默认 0 | 游戏 3 分数 |
| game4_score | float | 必填, 默认 0 | 游戏 4 分数 |
| game5_score | float | 必填, 默认 0 | 游戏 5 分数 |
| total_score | float | 必填, 默认 0 | 总分（自动计算为 game1-game5 之和） |
| created_at | datetime | 自动生成 | 创建时间 |

**说明**: Score表与User表为1:1关系，每个用户创建时自动创建一条分数记录，初始值均为0。`total_score` 字段由系统自动计算为 game1-game5 的总和，不可手动设置。

---

## 错误码说明

| 状态码 | 含义 | 常见场景 |
|--------|------|----------|
| 200 | 成功 | 所有正常操作 |
| 401 | 未授权 | API Key 无效或缺失 |
| 404 | 未找到 | 用户/分数 ID 不存在 |
| 409 | 冲突 | email 重复 |
| 422 | 参数错误 | 请求体格式错误、无效枚举值、缺少 API Key |
| 500 | 服务器错误 | 未捕获异常（响应包含 error_id） |
| 503 | 服务不可用 | DeepSeek API key 未配置 |

500 错误响应格式：
```json
{ "detail": "Internal Server Error", "error_id": "e7d4a0f2" }
```
可用 `error_id` 在 `logs/app.log` 中搜索完整堆栈信息。

---

## 项目结构

```
app/
  main.py            # FastAPI 应用入口、日志配置、请求中间件
  config.py          # 配置（pydantic-settings）
  database.py        # 数据库引擎与 Session
  models/            # SQLAlchemy 模型（User, Score）
  schemas/           # Pydantic 请求/响应模型
  crud/              # 数据库操作
  routers/           # 路由（users, scores, rankings, llm）
  services/          # 业务服务（llm_service）
alembic/             # 数据库迁移
tests/               # 测试（pytest, 43 个用例）
logs/                # 日志文件（自动轮转，git ignored）
requirements.txt
---

## AWS 部署

### 架构概览

- **计算**: AWS ECS Fargate (无服务器容器)
- **负载均衡**: Application Load Balancer (ALB)
- **数据库**: AWS RDS PostgreSQL (db.t3.micro)
- **安全**: API Key 认证 + HTTPS (待配置)
- **密钥管理**: AWS Secrets Manager

### AWS 资源

| 资源 | 名称 |
|------|------|
| Region | ap-south-1 (孟买) |
| ECS Cluster | cyber-ai-festival-cluster |
| ALB DNS | cyber-ai-festival-alb-xxx.ap-south-1.elb.amazonaws.com |
| ECR Repository | 866730904414.dkr.ecr.ap-south-1.amazonaws.com/cyber-ai-festival-backend |

详细架构文档: [docs/architecture.md](docs/architecture.md)

### 安全配置

- **API Key**: 存储在 AWS Secrets Manager (`cyber-ai-festival/api-key`)
- **数据库密码**: 存储在 AWS Secrets Manager (`cyber-ai-festival/db-password`)
- **DeepSeek API Key**: 存储在 AWS Secrets Manager (`cyber-ai-festival/deepseek-api-key`)

### 后续步骤

1. **获取域名** - 当前后端使用 HTTP，待配置 HTTPS
2. **配置 HTTPS** - 在 ALB 添加 HTTPS 监听器
3. **配置 WAF** - 添加 Web 应用防火墙防护
