"""
Backfill nicknames for all existing users (one-time script, run after migration).

Rules:
- admin role users → nickname 'admin@admin.com' (fixed identity)
- other users → generated as Firstname+LastnameInitial_NNN, ordered by user.id ascending
  (same-name collisions resolved by id order: lower id gets lower number)

Usage:
    cd cyber_ai_festival_be
    python scripts/backfill_nicknames.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.user import User
from app.crud.user import generate_nickname

ADMIN_NICKNAME = "admin@admin.com"


def backfill(dry_run: bool = False) -> None:
    db = SessionLocal()
    try:
        users = (
            db.query(User)
            .filter((User.nickname.is_(None)) | (User.nickname == ""))
            .order_by(User.id.asc())
            .all()
        )
        print(f"Found {len(users)} users without nickname")

        updated = 0
        for user in users:
            if user.role == "admin":
                # admin 固定昵称
                if db.query(User).filter(User.nickname == ADMIN_NICKNAME, User.id != user.id).first():
                    print(f"  [skip] id={user.id} admin nickname '{ADMIN_NICKNAME}' already taken by another user")
                    continue
                candidate = ADMIN_NICKNAME
            else:
                candidate = generate_nickname(db, user.firstname, user.lastname)

            if dry_run:
                print(f"  [dry] id={user.id} {user.firstname} {user.lastname} → {candidate}")
                continue

            for _ in range(10):
                try:
                    user.nickname = candidate
                    db.commit()
                    updated += 1
                    print(f"  ✓ id={user.id} {user.firstname} {user.lastname} → {candidate}")
                    break
                except Exception:
                    db.rollback()
                    if user.role == "admin":
                        print(f"  [skip] id={user.id} admin nickname conflict, giving up")
                        break
                    candidate = generate_nickname(db, user.firstname, user.lastname)
            else:
                # 10 次冲突兜底：带 id 后缀
                user.nickname = f"{generate_nickname(db, user.firstname, user.lastname)}_{user.id}"
                db.commit()
                updated += 1
                print(f"  ✓ id={user.id} → {user.nickname} (id-suffix fallback)")

        print(f"\nDone. {'[dry run] ' if dry_run else ''}Updated {updated} users.")
    finally:
        db.close()


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    backfill(dry_run=dry)
