import logging
import os
import time
import traceback
import uuid
from logging.handlers import RotatingFileHandler

from fastapi import FastAPI, Request, Response, HTTPException, Header, Depends, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import settings
from app.database import engine, Base, SessionLocal
from app.routers import users, scores, rankings, llm
from app.routers import rooms as rooms_router
from app.websocket.game import websocket_endpoint

# Ensure all models are imported so Base.metadata knows about them
import app.models.user  # noqa: F401
import app.models.score  # noqa: F401
import app.models.room  # noqa: F401

# --------------- API Key Authentication ---------------
async def verify_api_key(request: Request, x_api_key: str = Header(..., description="API Key for authentication")):
    """Verify API Key from request header"""
    # Skip authentication for health check endpoint
    if request.url.path == "/health":
        return True
    
    if not settings.api_key:
        logger.warning("API_KEY not configured on server!")
        raise HTTPException(status_code=500, detail="Server configuration error")
    
    if x_api_key != settings.api_key:
        logger.warning(f"Invalid API Key attempt: {x_api_key[:8]}...")
        raise HTTPException(status_code=401, detail="Invalid API Key")
    
    return True

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

    # ─── Auto-migration: Add role column if not exists ─────────────────────────
    with engine.connect() as conn:
        r = conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='users' AND column_name='role'"
        ))
        if not r.fetchone():
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN role VARCHAR(32) NOT NULL DEFAULT 'player'"
            ))
            conn.commit()
            logger.info("Migration: Added 'role' column to users table")
        else:
            logger.info("Migration: 'role' column already exists")

        # ─── Create admin account if not exists ────────────────────────────────
        r = conn.execute(text("SELECT id FROM users WHERE email = 'admin@admin.com'"))
        if not r.fetchone():
            conn.execute(text(
                "INSERT INTO users (firstname, lastname, email, region, role) "
                "VALUES ('admin', 'account', 'admin@admin.com', 'United Kingdom', 'admin')"
            ))
            conn.commit()
            # Get the new admin user id to create score record
            r = conn.execute(text("SELECT id FROM users WHERE email = 'admin@admin.com'"))
            admin_id = r.fetchone()[0]
            conn.execute(text(
                "INSERT INTO scores (user_id, game1_score, game2_score, game3_score, game4_score, game5_score, total_score) "
                "VALUES (:uid, 0, 0, 0, 0, 0, 0)"
            ), {"uid": admin_id})
            conn.commit()
            logger.info("Migration: Created admin account (id=%s)", admin_id)
        else:
            logger.info("Migration: Admin account already exists")

        # ─── Auto-seed question bank if empty ───────────────────────────────
        r = conn.execute(text("SELECT COUNT(*) FROM questions"))
        qcount = r.fetchone()[0]
        if qcount == 0:
            questions_data = [
                ("What does GAN stand for in AI?", "General Adaptive Network", "Generative Adversarial Network", "Graphical Analysis Node", "Gradient Adjusted Neuron", "B", 20, "AI Basics"),
                ("Which type of AI attack tricks a model by feeding it slightly altered input data?", "Phishing attack", "Adversarial attack", "Brute force attack", "Man-in-the-middle attack", "B", 20, "AI Security"),
                ("What is a deepfake?", "A very realistic AI-generated fake image or video", "A type of blockchain transaction", "A deep-learning training technique", "A type of firewall", "A", 20, "DeepFake"),
                ("What is the primary risk of AI hallucination?", "AI models become too fast", "AI generates false but convincing information", "AI deletes its training data", "AI refuses to answer questions", "B", 20, "AI Risks"),
                ("Which company developed ChatGPT?", "Google", "Meta", "OpenAI", "Microsoft", "C", 15, "AI Industry"),
                ("What does the term 'training data' refer to in machine learning?", "Data used to test the model's accuracy", "Data used to teach the model patterns and relationships", "Data the model has never seen before", "Data that is manually curated by humans only", "B", 20, "AI Basics"),
                ("Which of these is a real cybersecurity concern with AI models?", "Model inversion attacks that reveal training data", "AI models developing consciousness", "AI models needing food and water", "AI models refusing to process numbers", "A", 20, "AI Security"),
                ("What is 'prompt injection' in the context of LLMs?", "A method to speed up AI responses", "A technique where malicious input overrides the model's system instructions", "A way to install software on the model", "A type of hardware attack", "B", 25, "AI Security"),
                ("Which of these is NOT a common type of phishing attack?", "Spear phishing", "Whaling", "Neural phishing", "Clone phishing", "C", 20, "Phishing"),
                ("What is the purpose of a CAPTCHA?", "To encrypt user passwords", "To distinguish humans from bots", "To compress web page data", "To track user location", "B", 15, "Web Security"),
                ("What is zero-trust security architecture?", "Trust no one, verify nothing", "Never trust, always verify every access request", "Only trust internal network traffic", "Disable all security measures", "B", 25, "Cyber Security"),
                ("What does NLP stand for in AI?", "Neural Learning Protocol", "Natural Language Processing", "Network Layer Protection", "Non-Linear Programming", "B", 15, "AI Basics"),
                ("What is the biggest risk of using public AI models with sensitive data?", "The model might run out of memory", "Data could be used to train future versions of the model", "The model becomes slower over time", "The model requires a faster internet connection", "B", 20, "AI Risks"),
                ("What is social engineering in cybersecurity?", "Building social networks for engineers", "Manipulating people into revealing confidential information", "Using social media for marketing", "A type of software engineering methodology", "B", 15, "Cyber Security"),
                ("What is RAG (Retrieval-Augmented Generation)?", "A technique that combines retrieval of external data with text generation", "A method to delete old AI models", "A type of computer hardware", "A programming language for AI", "A", 25, "AI Techniques"),
            ]
            for q in questions_data:
                conn.execute(text(
                    "INSERT INTO questions (text, option_a, option_b, option_c, option_d, correct_option, time_limit, category) "
                    "VALUES (:text, :a, :b, :c, :d, :correct, :tl, :cat)"
                ), {"text": q[0], "a": q[1], "b": q[2], "c": q[3], "d": q[4], "correct": q[5], "tl": q[6], "cat": q[7]})
            conn.commit()
            logger.info("Migration: Seeded %d questions into question bank", len(questions_data))
        else:
            logger.info("Migration: Question bank already has %d questions", qcount)
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


# --------------- 启动时自动运行迁移 ---------------
@app.on_event("startup")
def run_migrations():
    """Run data migrations on startup (idempotent).
    
    Safe-guard: if the DB already has the post-migration schema (game1~game5 exist,
    no temp columns), insert the _migrated_v2 marker before running the migration
    script — this prevents the migration from re-executing on already-migrated DBs.
    """
    try:
        from app.migrations.rename_game_scores import run_migration
        
        # Pre-check: if DB already looks post-migration, set marker to prevent re-run
        with engine.connect() as conn:
            cols = conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'scores' AND column_name LIKE 'game%_score'"
            )).fetchall()
            has_g5 = any(c[0] == 'game5_score' for c in cols)
            has_temp = conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'scores' AND column_name IN ('_g1_old','_g2_old','_g3_old','_g4_old','_g5_old')"
            )).fetchone()
            has_marker = conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'scores' AND column_name = '_migrated_v2'"
            )).fetchone()
            
            if has_g5 and not has_temp and not has_marker:
                # Schema looks post-migration but no marker → add it to prevent re-run
                conn.execute(text("ALTER TABLE scores ADD COLUMN _migrated_v2 BOOLEAN DEFAULT TRUE"))
                conn.commit()
                logger.info("Pre-check: added _migrated_v2 marker to already-migrated DB")
        
        run_migration()
        logger.info("Startup migration check complete.")
    except Exception as e:
        logger.error("Startup migration failed: %s", e)

app.include_router(users.router, prefix="/users", tags=["users"], dependencies=[Depends(verify_api_key)])
app.include_router(scores.router, prefix="/scores", tags=["scores"], dependencies=[Depends(verify_api_key)])
app.include_router(rankings.router, prefix="/rankings", tags=["rankings"], dependencies=[Depends(verify_api_key)])
app.include_router(llm.router, prefix="/llm", tags=["llm"], dependencies=[Depends(verify_api_key)])
app.include_router(rooms_router.router, prefix="/rooms", tags=["rooms"], dependencies=[Depends(verify_api_key)])


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
    """Health check endpoint - no authentication required for ALB"""
    return {"status": "ok"}


# ─── WebSocket endpoint (no API key — uses query params for auth) ─────────
@app.websocket("/ws/room/{room_code}")
async def ws_room(websocket: WebSocket, room_code: str, user_id: int = Query(...), role: str = Query(...)):
    """
    WebSocket for real-time quiz.
    Query params: ?user_id=123&role=admin|player
    """
    await websocket_endpoint(websocket, room_code, user_id, role)


logger.info("Cyber AI Festival API started (log_level=%s)", settings.log_level)
