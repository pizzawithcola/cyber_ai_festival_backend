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
from app.routers import questions as questions_router
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
except Exception:
    logger.warning("Database not reachable at startup (will retry on first request): %s", traceback.format_exc())

# ─── Auto-migration: Add score column to questions ─────────────────────────────
# Runs independently so it is never skipped by failures in the legacy steps below.
try:
    with engine.connect() as conn:
        r = conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='questions' AND column_name='score'"
        ))
        if not r.fetchone():
            conn.execute(text(
                "ALTER TABLE questions ADD COLUMN score INTEGER NOT NULL DEFAULT 1000"
            ))
            conn.commit()
            logger.info("Migration: Added 'score' column to questions table")
        else:
            logger.info("Migration: 'score' column already exists")
except Exception:
    logger.warning("Migration: failed to add 'score' column to questions: %s", traceback.format_exc())

# ─── Auto-migration: Add balance column to rooms (per-category game balance) ───
try:
    with engine.connect() as conn:
        r = conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='rooms' AND column_name='balance'"
        ))
        if not r.fetchone():
            conn.execute(text("ALTER TABLE rooms ADD COLUMN balance JSON"))
            conn.commit()
            logger.info("Migration: Added 'balance' column to rooms table")
        else:
            logger.info("Migration: 'balance' column already exists")
except Exception:
    logger.warning("Migration: failed to add 'balance' column to rooms: %s", traceback.format_exc())

# ─── Legacy startup migrations (role / admin / question seed) ──────────────────
try:
    with engine.connect() as conn:
        # ─── Auto-migration: Add role column if not exists ─────────────────
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

        # ─── Create admin account if not exists (email column was dropped) ────
        r = conn.execute(text("SELECT id FROM users WHERE firstname = 'admin' AND role = 'admin'"))
        if not r.fetchone():
            conn.execute(text(
                "INSERT INTO users (firstname, lastname, region, role) "
                "VALUES ('admin', 'account', 'United Kingdom', 'admin')"
            ))
            conn.commit()
            # Get the new admin user id to create score record
            r = conn.execute(text("SELECT id FROM users WHERE firstname = 'admin' AND role = 'admin'"))
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
                # ── General AI (category "ai") ─────────────────────────────
                ("What is a deepfake?", "A very realistic AI-generated fake image or video", "A type of blockchain transaction", "A deep-learning training technique", "A type of firewall", "A", 20, "ai"),
                ("Which company developed ChatGPT?", "Google", "Meta", "OpenAI", "Microsoft", "C", 15, "ai"),
                ("Which of these is a real cybersecurity concern with AI models?", "Model inversion attacks that reveal training data", "AI models developing consciousness", "AI models needing food and water", "AI models refusing to process numbers", "A", 20, "ai"),
                ("What does NLP stand for in AI?", "Neural Learning Protocol", "Natural Language Processing", "Network Layer Protection", "Non-Linear Programming", "B", 15, "ai"),
                ("What is the biggest risk of using public AI models with sensitive data?", "The model might run out of memory", "Data could be used to train future versions of the model", "The model becomes slower over time", "The model requires a faster internet connection", "B", 20, "ai"),
                # ── Hallucination (category "hallucination") ───────────────
                ("What is an AI hallucination?", "AI refusing to answer", "AI giving slow responses", "AI making up false information", "AI repeating your question", "C", 20, "hallucination"),
                ("Why shouldn't you trust AI blindly?", "AI is always slow", "AI can be wrong or biased", "AI cannot read text", "AI only works at night", "B", 20, "hallucination"),
                ("If an AI tool provides a source or a link to back up its claim, what should you do?", "Check the link yourself, as AI can hallucinate false sources", "Trust it completely because AI doesn't lie", "Assume the link is a phishing scam", "Copy and paste it without reading", "A", 20, "hallucination"),
                ("What is \"Data Bias\" in AI?", "When an AI responds too quickly", "When an AI produces unfair or skewed results because its training data was unbalanced", "When an AI requires a password to use", "When an AI works without an internet connection", "B", 20, "hallucination"),
                ("What is the best practice when using AI to generate code or text for work?", "Copy and paste it directly without reading it", "Let the AI deploy it directly to production", "Assume the AI is 100% correct", "Review, verify, and test the output before using it", "D", 20, "hallucination"),
                # ── Data (category "data") ─────────────────────────────────
                ("Who decides what data is sensitive?", "The AI", "The app", "You", "Your internet provider", "C", 20, "data"),
                ("Why shouldn't you type highly confidential company or personal secrets into a public AI tool?", "The data may be used to train the AI and could be exposed to other users", "The tool will break down immediately", "The AI will charge you extra money", "Public AI tools automatically post your prompts to social media", "A", 20, "data"),
                ("What makes data \"sensitive\"?", "If it takes up a lot of storage space on your hard drive", "If its unauthorized exposure could cause harm, financial loss, or privacy violations to an individual or company", "If it can only be opened using an AI tool", "If it was created before the year 2000", "B", 20, "data"),
                ("What is a \"digital footprint\"?", "A virus that tracks your keystrokes", "A type of cloud storage", "A password manager", "The trail of data you leave behind when you use the internet", "D", 20, "data"),
                ("Why is it risky to reuse the same password across multiple accounts?", "It makes your accounts slower to load", "Websites will ban you for reusing passwords", "If one account is compromised, attackers can try it on all your others", "Passwords expire more quickly", "C", 20, "data"),
                # ── Agent (category "agent") ───────────────────────────────
                ("What is agentic AI?", "AI that acts on your behalf", "AI used only for gaming", "AI that works without electricity", "AI that only answers yes/no", "A", 20, "agent"),
                ("What is prompt injection?", "A way to speed up AI", "A trick to make AI behave incorrectly", "A method to clean your computer", "A type of antivirus", "B", 20, "agent"),
                ("What's the safest way to use AI for online shopping?", "Let AI buy everything automatically", "Never shop online", "Only buy from ads", "Check the websites and verify the choices", "D", 20, "agent"),
                ("What is the main risk of a \"Prompt Injection\" attack?", "It physically breaks the user's monitor", "It bypasses the AI's safety guardrails to make it execute unintended or malicious actions", "It slows down the Wi-Fi connection", "It deletes the user's browser history", "B", 20, "agent"),
                ("If an AI assistant acts as an autonomous agent (\"Agentic AI\"), who is ultimately responsible for monitoring its actions?", "The human user who deployed or instructed the agent", "The AI itself", "The internet service provider", "Nobody", "A", 20, "agent"),
                # ── Phishing (category "phishing") ─────────────────────────
                ("What is the goal of a phishing email?", "To entertain you", "To improve your computer speed", "To trick you into giving personal information", "To update your apps", "C", 20, "phishing"),
                ("Which of these is NOT a common sign of a phishing email?", "Urgency", "Fear", "Reward", "Transparency", "D", 20, "phishing"),
                ("What should you do if you receive an email from an unknown sender asking you to click a link?", "Click it immediately", "Reply with your details", "Ignore or delete it", "Forward it to friends", "C", 20, "phishing"),
                ("An email claims your bank account will be frozen in 2 hours unless you click a link. What tactic is being used?", "Transparency", "Artificial Intelligence", "Technical Support", "Creating a false sense of urgency", "D", 20, "phishing"),
                ("What is \"Smishing\"?", "A phishing attack sent via SMS/text message", "A type of computer virus that slows down your internet", "Sharing your password with a friend", "An update to your email application", "A", 20, "phishing"),
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
    version="0.1.2",
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
app.include_router(questions_router.router, prefix="/questions", tags=["questions"], dependencies=[Depends(verify_api_key)])


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
