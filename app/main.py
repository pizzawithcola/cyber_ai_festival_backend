import logging
import os
import time
import traceback
import uuid
from logging.handlers import RotatingFileHandler

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import engine, Base
from app.routers import users, scores, rankings, llm

# --------------- Logging ---------------
LOG_LEVEL = getattr(logging, (settings.log_level or "INFO").upper(), logging.INFO)
LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"

# 确保 logs 目录存在
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# 根 logger 配置
root_logger = logging.getLogger()
root_logger.setLevel(LOG_LEVEL)
formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATEFMT)

# 终端输出
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
root_logger.addHandler(console_handler)

# 文件输出（自动轮转：单文件最大 5MB，保留最近 3 个备份）
file_handler = RotatingFileHandler(
    os.path.join(LOG_DIR, "app.log"),
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8",
)
file_handler.setFormatter(formatter)
root_logger.addHandler(file_handler)

logger = logging.getLogger("app")

# Create tables (容错：如果数据库不可达，应用仍可启动，健康检查不受影响)
try:
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables ready")
except Exception:
    logger.warning("Database not reachable at startup (will retry on first request): %s", traceback.format_exc())

app = FastAPI(
    title="Cyber AI Festival API",
    description="用户登记、分数上传与 LLM 调用",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router, prefix="/users", tags=["users"])
app.include_router(scores.router, prefix="/scores", tags=["scores"])
app.include_router(rankings.router, prefix="/rankings", tags=["rankings"])
app.include_router(llm.router, prefix="/llm", tags=["llm"])


# --------------- 请求日志中间件 ---------------
@app.middleware("http")
async def log_requests(request: Request, call_next):
    error_id = uuid.uuid4().hex[:8]
    start = time.time()
    try:
        response: Response = await call_next(request)
    except Exception as exc:
        duration_ms = (time.time() - start) * 1000
        logger.error(
            "[%s] %s %s → 500 (%.0fms)\n%s",
            error_id, request.method, request.url.path, duration_ms,
            traceback.format_exc(),
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal Server Error", "error_id": error_id},
            headers={"Access-Control-Allow-Origin": "*"},
        )
    duration_ms = (time.time() - start) * 1000
    if response.status_code >= 500:
        logger.error(
            "[%s] %s %s → %s (%.0fms)",
            error_id, request.method, request.url.path, response.status_code, duration_ms,
        )
    elif response.status_code >= 400:
        logger.warning(
            "[%s] %s %s → %s (%.0fms)",
            error_id, request.method, request.url.path, response.status_code, duration_ms,
        )
    else:
        logger.info(
            "%s %s → %s (%.0fms)",
            request.method, request.url.path, response.status_code, duration_ms,
        )
    return response


@app.get("/health")
def health():
    return {"status": "ok"}


logger.info("Cyber AI Festival API started (log_level=%s)", settings.log_level)
