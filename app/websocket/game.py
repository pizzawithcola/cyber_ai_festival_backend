"""
WebSocket Game Engine — Real-time Kahoot-style quiz logic.

Architecture:
  - One GameSession per room (stored in memory dict).
  - Each WS connection receives a role: "admin" or "player".
  - Admin can START the game; players receive questions and submit answers.
  - Correct = 500 base + speed (0–500) → 500–1000; wrong = 0.
  - Bonus questions (x2/x3) multiply the earned score. No streak bonus.
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
        self._force_ended = False  # set by force_end() to break game loop
        self.snapshot: Optional[dict] = None  # latest state, replayed to (re)connecting clients

    # ─── Pause / Resume / Force-End ───────────────────────────────────────
    def pause(self):
        """Pause the current question timer."""
        self._paused = True
        # Do NOT set the event — the tick loop should WAIT on it.
        # resume() / force_end() will set the event to wake the loop.
        logger.info("Room %s: game paused", self.room_code)

    def resume(self):
        """Resume the current question timer."""
        self._paused = False
        if self._pause_event:
            self._pause_event.set()  # Wake the waiting pause loop
        logger.info("Room %s: game resumed", self.room_code)

    def force_end(self):
        """Signal the game loop to stop immediately. The loop will call _end_game()."""
        self._force_ended = True
        self._paused = False
        if self._pause_event:
            self._pause_event.set()  # Unblock pause wait so loop can exit
        logger.info("Room %s: force-end signaled", self.room_code)

    # ─── Helpers ───────────────────────────────────────────────────────────
    async def _get_leaderboard(self) -> list[dict]:
        """Fetch current leaderboard from DB for this room."""
        db = SessionLocal()
        try:
            room = db.query(Room).filter(Room.code == self.room_code).first()
            if not room:
                return []
            players = (
                db.query(RoomPlayer)
                .filter(RoomPlayer.room_id == room.id)
                .order_by(RoomPlayer.total_score.desc())
                .all()
            )
            return [
                {
                    "rank": i + 1,
                    "player_id": p.user_id,
                    "player_name": p.player_name,
                    "total_score": p.total_score,
                    "streak": p.streak,
                }
                for i, p in enumerate(players)
            ]
        except Exception:
            return []
        finally:
            db.close()

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
            room = db.query(Room).filter(Room.code == self.room_code).first()
            balance = (room.balance if room and room.balance else {}) or {}

            all_q = (
                db.query(Question)
                .order_by(Question.id)
                .all()
            )

            if balance:
                # Balanced draw: sample `count` random questions from EACH category.
                # Every game re-samples randomly so the set stays fair per category.
                selected: list = []
                for cat, count in balance.items():
                    if not count or count <= 0:
                        continue
                    cat_qs = [q for q in all_q if (q.category or "") == cat]
                    selected += random.sample(cat_qs, min(count, len(cat_qs)))
                random.shuffle(selected)
            else:
                # Legacy fallback: random sample from the whole bank
                qc = min(question_count, len(all_q))
                selected = random.sample(all_q, qc)

            # ── Bonus multiplier: pick up to 2 bonus questions, assign x2/x3,
            #    and force them to appear as the LAST two questions of the game. ──
            bonus_qs = [q for q in selected if (q.category or "") == "bonus"]
            regular_qs = [q for q in selected if (q.category or "") != "bonus"]
            # multiplier per question id
            mult: dict[int, int] = {}
            if len(bonus_qs) >= 2:
                random.shuffle(bonus_qs)
                mult[bonus_qs[0].id] = 2
                mult[bonus_qs[1].id] = 3
                # extra bonus questions (if any) are treated as regular
                regular_qs.extend(bonus_qs[2:])
                bonus_qs = bonus_qs[:2]
            elif len(bonus_qs) == 1:
                # only one bonus drawn → single x2
                mult[bonus_qs[0].id] = 2
            random.shuffle(regular_qs)

            # Ordered: regular questions first, then bonus x2/x3 as the last two.
            ordered = regular_qs + bonus_qs

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
                    "score": 500,  # base points for a correct answer (500–1000 with speed)
                    "multiplier": mult.get(q.id, 1),
                }
                for q in ordered
            ]

            # Reset room state in DB
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
            self.snapshot = {"phase": "countdown", "countdown_value": i}
            await self.broadcast({"type": "countdown", "value": i})
            await asyncio.sleep(1)

        # Start first question
        await self._next_question()

    async def _next_question(self):
        """Push next question and start answer timer."""
        if self._force_ended:
            await self._end_game()
            return
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
            "score": q.get("score", 500),
            "multiplier": q.get("multiplier", 1),
        }
        await self.broadcast(question_msg)
        # Cache current state so reconnecting clients can resume this exact question
        self.snapshot = {
            "phase": "question",
            "question": question_msg,
            "remaining": q["time_limit"],
            "answered_count": 0,
            "is_paused": False,
            "total_players": len(self.players),
        }

        # Tick loop
        remaining = q["time_limit"]
        connected = len(self.players)
        self._pause_event = asyncio.Event()
        # Send initial tick so clients have the starting value
        await self.broadcast({"type": "tick", "remaining": remaining, "answered_count": 0, "total_players": connected})
        while remaining > 0:
            if self._force_ended:
                break
            answered_now = len(self.answers)
            if connected > 0 and answered_now >= connected:
                break  # All answered

            # Check pause — enter pause loop
            if self._paused:
                self.snapshot["is_paused"] = True
                self.snapshot["remaining"] = remaining
                await self.broadcast({"type": "paused", "remaining": remaining})
                self._question_remaining = remaining
                # Wait until resumed (or force-ended)
                while self._paused and not self._force_ended:
                    await self._pause_event.wait()
                if self._force_ended:
                    break
                # Resumed
                self.snapshot["is_paused"] = False
                self.snapshot["remaining"] = remaining
                await self.broadcast({"type": "resumed", "remaining": remaining})
                self._pause_event = asyncio.Event()
                self._paused = False
                # Re-check exit conditions after resume
                connected = len(self.players)
                answered_now = len(self.answers)
                if connected > 0 and answered_now >= connected:
                    break
                if remaining <= 0:
                    break

            await asyncio.sleep(1)
            # Re-check pause/force after sleep
            if self._paused or self._force_ended:
                continue
            remaining -= 1
            connected = len(self.players)
            if connected == 0:
                break

            # Broadcast tick
            self.snapshot["remaining"] = remaining
            self.snapshot["answered_count"] = len(self.answers)
            self.snapshot["total_players"] = connected
            await self.broadcast({"type": "tick", "remaining": remaining, "answered_count": len(self.answers), "total_players": connected})

        self._pause_event = None

        # If force-ended, go directly to end_game
        if self._force_ended:
            await self._end_game()
            return

        # Time's up — show result
        await self._show_result(q)

    async def _show_result(self, q: dict):
        """Compute scores, save to DB, broadcast result.

        Scoring (2026): correct = 500 base + speed (0–500) → 500–1000.
        Wrong = 0. Bonus questions multiply the final score by x2/x3.
        Speed: each full second slower removes 25 points, rounded to the integer point.
        No streak bonus.
        """
        self.state = "result"
        correct_option = q["correct"]
        multiplier = int(q.get("multiplier", 1))
        db = SessionLocal()

        try:
            # Calc scores & batch collect
            score_updates: list[dict] = []  # {rp, is_correct, score}
            for rp_id, ans in self.answers.items():
                is_correct = (ans["option"] == correct_option)
                ans_time = ans["ms"]
                time_limit = q["time_limit"] * 1000  # convert to ms

                score = 0
                if is_correct:
                    # Base 500 + speed (up to 500). At 20s limit this is 25 pts/second.
                    speed_bonus = max(0, min(500, int((1 - ans_time / time_limit) * 500)))
                    score = 500 + speed_bonus
                    score = int(score * multiplier)  # bonus x2/x3 applied after base score

                ans["correct"] = is_correct
                ans["score"] = score

                # Batch collect: fetch player, update, collect answer
                rp = db.query(RoomPlayer).filter(RoomPlayer.id == rp_id).first()
                if rp:
                    if is_correct:
                        rp.total_score += score
                    else:
                        pass  # wrong answer → no points

                    pa = PlayerAnswer(
                        player_id=rp_id,
                        question_id=q["id"],
                        chosen_option=ans["option"],
                        is_correct=is_correct,
                        answer_time_ms=ans_time,
                        score_earned=score,
                    )
                    db.add(pa)

            # Single commit for all updates
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        # Build distribution
        distribution = {"A": 0, "B": 0, "C": 0, "D": 0}
        for ans in self.answers.values():
            distribution[ans["option"]] += 1

        # Cache result state so a reconnecting client can resume the result screen.
        self.snapshot = {
            "phase": "result",
            "question": {
                "type": "question",
                "question_id": q["id"],
                "number": self.current_question_idx + 1,
                "total": len(self.questions),
                "text": q["text"],
                "options": q["options"],
                "time_limit": q["time_limit"],
                "score": q.get("score", 500),
                "multiplier": q.get("multiplier", 1),
            },
            "correct_option": correct_option,
            "distribution": distribution,
            "result_answers": {
                str(k): {"option": v.get("option"), "correct": v.get("correct"), "score": v.get("score", 0)}
                for k, v in self.answers.items()
            },
        }

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

        # Broadcast per-question leaderboard after a short delay
        await asyncio.sleep(7)
        leaderboard = await self._get_leaderboard()
        self.snapshot = {
            "phase": "leaderboard",
            "leaderboard": leaderboard,
            "question_number": self.current_question_idx + 1,
            "total_questions": len(self.questions),
        }
        await self.broadcast({
            "type": "leaderboard",
            "leaderboard": leaderboard,
            "question_number": self.current_question_idx + 1,
            "total_questions": len(self.questions),
        })

        # Wait before next question
        await asyncio.sleep(5)
        if self._force_ended:
            await self._end_game()
            return
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
        except Exception:
            raise
        finally:
            db.close()

        self.snapshot = {"phase": "finished", "leaderboard": leaderboard}
        await self.broadcast({
            "type": "game_over",
            "leaderboard": leaderboard,
        })
        logger.info("Room %s: game over, %d players", self.room_code, len(leaderboard))

        # Schedule cleanup: remove session from memory after clients have received game_over
        room_code = self.room_code
        asyncio.get_event_loop().call_later(
            10, lambda: sessions.pop(room_code, None) and logger.info("Room %s: session cleaned up", room_code)
        )

    # ─── Admin messaging ───────────────────────────────────────────────────
    async def _send_admin(self, msg: dict):
        if self.admin:
            try:
                await self.admin.send_text(json.dumps(msg, ensure_ascii=False))
            except Exception:
                pass

    # ─── Reconnect state replay ────────────────────────────────────────────
    async def _replay_snapshot(self, ws: WebSocket, role: str):
        """After a (re)connect, resend the current game state so the client resumes
        the exact phase instead of desyncing (stuck waiting / wrong question / score).

        The player/admin already received player_count / player_joined; these follow-up
        messages drive the shared useGameWebSocket state machine to the live phase.
        """
        snap = self.snapshot
        if not snap:
            return
        phase = snap.get("phase")
        try:
            if phase == "countdown":
                await ws.send_text(json.dumps({"type": "countdown", "value": snap.get("countdown_value", 3)}, ensure_ascii=False))
            elif phase == "question":
                q = snap.get("question") or {}
                # question payload already excludes the correct answer
                await ws.send_text(json.dumps(q, ensure_ascii=False))
                await ws.send_text(json.dumps({
                    "type": "tick",
                    "remaining": snap.get("remaining", q.get("time_limit", 0)),
                    "answered_count": snap.get("answered_count", 0),
                    "total_players": snap.get("total_players", 0),
                }, ensure_ascii=False))
                if snap.get("is_paused"):
                    await ws.send_text(json.dumps({"type": "paused", "remaining": snap.get("remaining", 0)}, ensure_ascii=False))
            elif phase == "result":
                q = snap.get("question") or {}
                await ws.send_text(json.dumps(q, ensure_ascii=False))
                if role == "admin":
                    await ws.send_text(json.dumps({
                        "type": "question_result",
                        "correct_option": snap.get("correct_option"),
                        "distribution": snap.get("distribution", {}),
                        "answers": snap.get("result_answers", {}),
                    }, ensure_ascii=False))
                else:
                    pc = self.get_player_connection(ws)
                    ans = snap.get("result_answers", {}).get(str(pc.room_player_id)) if pc else None
                    await ws.send_text(json.dumps({
                        "type": "question_result",
                        "correct_option": snap.get("correct_option"),
                        "your_option": (ans or {}).get("option"),
                        "is_correct": bool((ans or {}).get("correct")),
                        "score_earned": (ans or {}).get("score", 0),
                        "distribution": snap.get("distribution", {}),
                    }, ensure_ascii=False))
            elif phase == "leaderboard":
                await ws.send_text(json.dumps({
                    "type": "leaderboard",
                    "leaderboard": snap.get("leaderboard", []),
                    "question_number": snap.get("question_number", 0),
                    "total_questions": snap.get("total_questions", 0),
                }, ensure_ascii=False))
            elif phase == "finished":
                await ws.send_text(json.dumps({
                    "type": "game_over",
                    "leaderboard": snap.get("leaderboard", []),
                }, ensure_ascii=False))
        except Exception:
            pass

    # ─── Handle incoming messages ──────────────────────────────────────────
    async def handle_admin_message(self, ws: WebSocket, msg: dict):
        msg_type = msg.get("type")
        if msg_type == "start_game":
            qc = msg.get("question_count", 10)
            await self.start_game(qc)
        elif msg_type == "pause":
            if not self._paused:
                self.pause()
        elif msg_type == "resume":
            if self._paused:
                self.resume()

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

    # Replay current game state so a freshly connected / reconnected client resumes
    # the live phase instead of desyncing. (Must run after the player is appended.)
    await session._replay_snapshot(ws, role)

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
