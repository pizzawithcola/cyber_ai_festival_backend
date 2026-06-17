"""
Add admin account and run role migration.

Usage:
    cd cyber_ai_festival_be
    python scripts/add_admin.py
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import engine, SessionLocal, Base
from app.models.user import User
from app.models.score import Score
from sqlalchemy import text


def run_migration():
    """Add role column if it doesn't exist"""
    print("Checking if 'role' column exists...")
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='users' AND column_name='role'"
        ))
        if result.fetchone():
            print("  → 'role' column already exists, skipping migration.")
        else:
            print("  → Adding 'role' column...")
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN role VARCHAR(32) NOT NULL DEFAULT 'player'"
            ))
            conn.commit()
            print("  ✓ 'role' column added with default 'player'.")


def create_admin():
    """Create admin account if it doesn't exist"""
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == "admin@admin.com").first()
        if existing:
            print(f"  → Admin account already exists (id={existing.id}), updating role...")
            existing.role = "admin"
            db.commit()
            print("  ✓ Admin role updated.")
            return

        admin = User(
            firstname="admin",
            lastname="account",
            email="admin@admin.com",
            region="United Kingdom",
            role="admin",
        )
        db.add(admin)
        db.flush()

        # Create default score record
        score = Score(
            user_id=admin.id,
            game1_score=0,
            game2_score=0,
            game3_score=0,
            game4_score=0,
            game5_score=0,
            total_score=0,
        )
        db.add(score)
        db.commit()
        print(f"  ✓ Admin account created (id={admin.id}, email=admin@admin.com, role=admin).")
    finally:
        db.close()


if __name__ == "__main__":
    print("=== Add Role Migration & Admin Account ===\n")
    run_migration()
    print("\nCreating admin account...")
    create_admin()
    print("\nDone! All existing users have role='player', admin account has role='admin'.")
