"""
WebSocket Game Engine — Real-time Kahoot-style quiz logic.

Architecture:
  - One GameSession per room (stored in memory dict).
  - Each WS connection receives a role: "admin" or "player".
  - Admin can START the game; players receive questions and submit answers.
  - Score = 1000 (correct) + speed_bonus + streak_bonus.
"""

import asyncio
import json
import logging
import random
import time
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.room import Room, RoomPlayer, Question, PlayerAnswer

logger = logging.getLogger(__name__)

# ─── Global storage ──────────────────────────────────────────────────────────
# room_code → GameSession
sessions: dict[str, "GameSession"] = {}


class PlayerConnection:
    """Tracks one player's WS connection and metadata."""

    def __init__(self, ws: WebSocket, user_id: int, player_name: str, room_player_id: int):
        self.ws = ws
        self.user_id = user_id
        self.player_name = player_name
        self.room_player_id = room_player_id  # DB id in room_players table


class GameSession:
    """State machine for one room's game."""

    def __init__(self, room_code: str):
        self.room_code = room_code
        self.state = "waiting"  # waiting | countdown | question | result | finished
        self.admin: Optional[WebSocket] = None
        self.players: list[PlayerConnection] = []
        self.questions: list[dict] = []        # question payloads
        self.current_question_idx: int = 0
        self.question_start_ts: float = 0.0    # when current question was sent
        self.answers: dict[int, dict] = {}     # room_player_id → {option, ms}
        self.task: Optional[asyncio.Task] = None
        self._paused = False
        self._pause_event: Optional[asyncio.Event] = None
        self._question_remaining = 0  # remaining seconds when paused

    # ─── Pause / Resume / Force-End ───────────────────────────────────────
    def pause(self):
        """Pause the current question timer."""
        self._paused = True
        if self._pause_event:
            self._pause_event.set()
        logger.info("Room %s: game paused", self.room_code)

    def resume(self):
        """Resume the current question timer."""
        self._paused = False
        if self._pause_event:
            self._pause_event.clear()
        logger.info("Room %s: game resumed", self.room_code)

    async def force_end(self):
        """Force-end the game immediately."""
        self._paused = False
        if self._pause_event:
            self._pause_event.clear()
        # Broadcast end immediately
        await self._end_game()

    # ─── Helpers ───────────────────────────────────────────────────────────
    async def broadcast(self, msg: dict):
        """Send message to all connected clients (admin + players)."""
        payload = json.dumps(msg, ensure_ascii=False)
        dead: list[PlayerConnection] = []
        for p in self.players:
            try:
                await p.ws.send_text(payload)
            except Exception:
                dead.append(p)
        for d in dead:
            self.players.remove(d)
        if self.admin:
            try:
                await self.admin.send_text(payload)
            except Exception:
                self.admin = None

    async def broadcast_players_only(self, msg: dict):
        """Send message only to players (not the admin)."""
        payload = json.dumps(msg, ensure_ascii=False)
        for p in self.players:
            try:
                await p.ws.send_text(payload)
            except Exception:
                pass

    def get_connected_player_ids(self) -> set[int]:
        """Return set of room_player_ids currently connected via WS."""
        return {p.room_player_id for p in self.players}

    def get_player_connection(self, ws: WebSocket) -> Optional[PlayerConnection]:
        for p in self.players:
            if p.ws == ws:
                return p
        return None

    # ─── Game Flow ─────────────────────────────────────────────────────────
    async def start_game(self, question_count: int = 10):
        """Admin triggered — begin the game."""
        if self.state not in ("waiting", "finished"):
            logger.warning("Room %s: cannot start — current state %s", self.room_code, self.state)
            return

        if len(self.players) < 1:
            await self._send_admin({"type": "error", "message": "Need at least 1 player"})
            return

        # Load questions from DB
        db = SessionLocal()
        try:
            all_q = (
                db.query(Question)
                .order_by(Question.id)
                .all()
            )
            if len(all_q) < question_count:
                question_count = len(all_q)
            selected = random.sample(all_q, min(question_count, len(all_q)))
            self.questions = [
                {
                    "id": q.id,
                    "text": q.text,
                    "options": [
                        {"id": "A", "label": q.option_a, "color": "red", "icon": "▲"},
                        {"id": "B", "label": q.option_b, "color": "cyan", "icon": "◆"},
                        {"id": "C", "label": q.option_c, "color": "yellow", "icon": "●"},
                        {"id": "D", "label": q.option_d, "color": "lime", "icon": "■"},
                    ],
                    "correct": q.correct_option,
                    "time_limit": q.time_limit,
                }
                for q in selected
            ]

            # Reset room state in DB
            room = db.query(Room).filter(Room.code == self.room_code).first()
            if room:
                room.status = "playing"
                room.question_count = len(self.questions)
                db.commit()

            # Reset all players' scores
            for rp in db.query(RoomPlayer).filter(
                RoomPlayer.room_id == room.id
            ).all():
                rp.total_score = 0
                rp.streak = 0
            db.commit()
            db.close()

        except Exception:
            db.close()
            raise

        self.current_question_idx = 0

        # 3-second countdown
        self.state = "countdown"
        for i in range(3, 0, -1):
            await self.broadcast({"type": "countdown", "value": i})
            await asyncio.sleep(1)

        # Start first question
        await self._next_question()

    async def _next_question(self):
        """Push next question and start answer timer."""
        if self.current_question_idx >= len(self.questions):
            await self._end_game()
            return

        q = self.questions[self.current_question_idx]
        self.state = "question"
        self.answers.clear()
        self.question_start_ts = time.time()

        # Broadcast question (exclude correct answer from players)
        question_msg = {
            "type": "question",
            "question_id": q["id"],
            "number": self.current_question_idx + 1,
            "total": len(self.questions),
            "text": q["text"],
            "options": q["options"],
            "time_limit": q["time_limit"],
        }
        await self.broadcast(question_msg)

        # Tick loop
        remaining = q["time_limit"]
        connected = len(self.players)
        self._pause_event = asyncio.Event()
        while remaining > 0:
            answered_now = len(self.answers)
            if connected > 0 and answered_now >= connected:
                break  # All answered

            # Check pause
            if self._paused:
                await self.broadcast({"type": "paused"})
                self._question_remaining = remaining
                await self._pause_event.wait()
                await self.broadcast({"type": "resumed", "remaining": remaining})
                self._pause_event = asyncio.Event()
                self._paused = False

            await asyncio.sleep(1)
            remaining -= 1
            connected = len(self.players)
            if connected == 0:
                break

            # Broadcast tick
            await self.broadcast({"type": "tick", "remaining": remaining, "answered_count": len(self.answers), "total_players": connected})

        self._pause_event = None

        # Time's up — show result
        await self._show_result(q)

    async def _show_result(self, q: dict):
        """Compute scores, save to DB, broadcast result."""
        self.state = "result"
        correct_option = q["correct"]
        db = SessionLocal()

        try:
            # Calc scores & save
            for rp_id, ans in self.answers.items():
                is_correct = (ans["option"] == correct_option)
                ans_time = ans["ms"]
                time_limit = q["time_limit"] * 1000  # convert to ms

                score = 0
                if is_correct:
                    speed_bonus = int((1 - ans_time / time_limit) * 500)
                    score = 1000 + speed_bonus

                ans["correct"] = is_correct
                ans["score"] = score

                # Save to DB
                rp = db.query(RoomPlayer).filter(RoomPlayer.id == rp_id).first()
                if rp:
                    old_streak = rp.streak
                    if is_correct:
                        rp.streak += 1
                        rp.total_score += score + rp.streak * 100
                    else:
                        rp.streak = 0
                    db.commit()

                    pa = PlayerAnswer(
                        player_id=rp_id,
                        question_id=q["id"],
                        chosen_option=ans["option"],
                        is_correct=is_correct,
                        answer_time_ms=ans_time,
                        score_earned=score + (rp.streak * 100 if is_correct else 0),
                    )
                    db.add(pa)
                    db.commit()
            db.close()
        except Exception:
            db.close()
            raise

        # Build distribution
        distribution = {"A": 0, "B": 0, "C": 0, "D": 0}
        for ans in self.answers.values():
            distribution[ans["option"]] += 1

        # Build player-specific results
        for p in self.players:
            ans = self.answers.get(p.room_player_id)
            if ans:
                await p.ws.send_text(json.dumps({
                    "type": "question_result",
                    "correct_option": correct_option,
                    "your_option": ans["option"],
                    "is_correct": ans["correct"],
                    "score_earned": ans["score"],
                    "distribution": distribution,
                }, ensure_ascii=False))

        # Send admin result
        if self.admin:
            await self.admin.send_text(json.dumps({
                "type": "question_result",
                "correct_option": correct_option,
                "distribution": distribution,
                "answers": {
                    str(k): {"option": v["option"], "correct": v["correct"]}
                    for k, v in self.answers.items()
                },
            }, ensure_ascii=False))

        # Wait before next question
        await asyncio.sleep(4)
        self.current_question_idx += 1
        await self._next_question()

    async def _end_game(self):
        """All questions done — broadcast final leaderboard."""
        self.state = "finished"
        db = SessionLocal()
        try:
            room = db.query(Room).filter(Room.code == self.room_code).first()
            if room:
                room.status = "finished"
                db.commit()

            players = (
                db.query(RoomPlayer)
                .filter(RoomPlayer.room_id == room.id)
                .order_by(RoomPlayer.total_score.desc())
                .all()
            )
            leaderboard = [
                {
                    "rank": i + 1,
                    "player_id": p.user_id,
                    "player_name": p.player_name,
                    "total_score": p.total_score,
                    "streak": p.streak,
                }
                for i, p in enumerate(players)
            ]
            db.close()
        except Exception:
            db.close()
            raise

        await self.broadcast({
            "type": "game_over",
            "leaderboard": leaderboard,
        })
        logger.info("Room %s: game over, %d players", self.room_code, len(leaderboard))

    # ─── Admin messaging ───────────────────────────────────────────────────
    async def _send_admin(self, msg: dict):
        if self.admin:
            try:
                await self.admin.send_text(json.dumps(msg, ensure_ascii=False))
            except Exception:
                pass

    # ─── Handle incoming messages ──────────────────────────────────────────
    async def handle_admin_message(self, ws: WebSocket, msg: dict):
        msg_type = msg.get("type")
        if msg_type == "start_game":
            qc = msg.get("question_count", 10)
            await self.start_game(qc)

    async def handle_player_message(self, ws: WebSocket, msg: dict):
        msg_type = msg.get("type")
        if msg_type == "submit_answer" and self.state == "question":
            player = self.get_player_connection(ws)
            if not player:
                return
            if player.room_player_id in self.answers:
                return  # Already answered
            elapsed_ms = int((time.time() - self.question_start_ts) * 1000)
            self.answers[player.room_player_id] = {
                "option": msg.get("option", ""),
                "ms": elapsed_ms,
            }


# ─── WebSocket endpoint ────────────────────────────────────────────────────
async def websocket_endpoint(ws: WebSocket, room_code: str, user_id: int, role: str):
    """
    Main WebSocket handler.
    ?user_id=123&role=admin  → admin connection
    ?user_id=456&role=player → player connection
    """
    await ws.accept()

    # Get or create session
    session = sessions.get(room_code)
    if not session:
        session = GameSession(room_code)
        sessions[room_code] = session

    # Get player name from DB
    player_name = "Unknown"
    room_player_id = 0
    db = SessionLocal()
    try:
        room = db.query(Room).filter(Room.code == room_code).first()
        if room and role == "player":
            rp = (
                db.query(RoomPlayer)
                .filter(RoomPlayer.room_id == room.id, RoomPlayer.user_id == user_id)
                .first()
            )
            if rp:
                player_name = rp.player_name
                room_player_id = rp.id
        db.close()
    except Exception:
        db.close()

    if role == "admin":
        session.admin = ws
        # Send current player count
        await ws.send_text(json.dumps({
            "type": "player_count",
            "count": len(session.players),
            "players": [
                {
                    "player_id": p.user_id,
                    "player_name": p.player_name,
                    "total_score": p.total_score if hasattr(p, 'total_score') else 0,
                }
                for p in session.players
            ],
        }, ensure_ascii=False))
    else:
        pc = PlayerConnection(ws, user_id=user_id, player_name=player_name, room_player_id=room_player_id)
        session.players.append(pc)
        # Broadcast player join
        await session.broadcast({
            "type": "player_joined",
            "player_count": len(session.players),
            "player_name": player_name,
            "players": [
                {
                    "player_id": p.user_id,
                    "player_name": p.player_name,
                    "total_score": 0,
                }
                for p in session.players
            ],
        })
        logger.info("Room %s: player %s (uid=%s) connected", room_code, player_name, user_id)

    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)

            # Heartbeat: respond to ping from any client (admin or player)
            if msg.get("type") == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
                continue

            if role == "admin":
                await session.handle_admin_message(ws, msg)
            else:
                await session.handle_player_message(ws, msg)
    except WebSocketDisconnect:
        logger.info("Room %s: %s (uid=%s) disconnected", room_code, role, user_id)
    except Exception as e:
        logger.error("Room %s: WS error for %s (uid=%s): %s", room_code, role, user_id, e)
    finally:
        if role == "player":
            if pc in session.players:
                session.players.remove(pc)
            await session.broadcast({
                "type": "player_left",
                "player_count": len(session.players),
                "player_name": player_name,
            })
            logger.info("Room %s: player %s removed, %d remaining", room_code, player_name, len(session.players))
        if role == "admin":
            session.admin = None
