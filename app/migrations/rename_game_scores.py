"""
Run this script to migrate the scores table:
  - Remove DeepFake (old G1)
  - Renumber G2→G1, G3→G2, G4→G3, G5→G4
  - Add new G5 (Final Showdown) default 0
  - Recalculate total_score

Usage:
  python -m app.migrations.rename_game_scores

Safe to run multiple times (idempotent check).
"""

import logging
from sqlalchemy import text
from app.database import engine, SessionLocal

logger = logging.getLogger(__name__)


def run_migration():
    """One-time migration: renumber game scores after removing DeepFake (old G1).

    IDEMPOTENT: checks for _migrated_v2 marker column — if present, skips entirely.
    This migration should ONLY run once. Do NOT trigger on every startup.
    """
    db = SessionLocal()
    try:
        # ── Idempotency check: _migrated_v2 flag ──────────────────────────
        result = db.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'scores' AND column_name = '_migrated_v2'
        """)).fetchone()

        if result:
            logger.info("Migration v2 already applied (_migrated_v2 found). Skipping.")
            # Still recalculate total_score for safety
            db.execute(text("""
                UPDATE scores SET total_score =
                    COALESCE(game1_score, 0) + COALESCE(game2_score, 0) +
                    COALESCE(game3_score, 0) + COALESCE(game4_score, 0) + COALESCE(game5_score, 0)
            """))
            db.commit()
            return

        # ── Clean up any leftover temp columns from a previous failed run ─
        for col in ['_g1_old', '_g2_old', '_g3_old', '_g4_old', '_g5_old']:
            try:
                db.execute(text(f"ALTER TABLE scores DROP COLUMN IF EXISTS {col}"))
                db.commit()
            except Exception:
                db.rollback()

        # Step 1: Check current column state
        result = db.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'scores' AND column_name LIKE 'game%_score'
            ORDER BY column_name
        """)).fetchall()
        existing_cols = {row[0] for row in result}
        logger.info("Existing game score columns: %s", existing_cols)

        if 'game5_score' not in existing_cols:
            logger.info("No game5_score column found — schema may be incomplete. Aborting.")
            return

        logger.info("=== Starting game score renumbering migration ===")

        # Step 2: Rename old columns to temp names
        db.execute(text("ALTER TABLE scores RENAME COLUMN game1_score TO _g1_old"))
        db.execute(text("ALTER TABLE scores RENAME COLUMN game2_score TO _g2_old"))
        db.execute(text("ALTER TABLE scores RENAME COLUMN game3_score TO _g3_old"))
        db.execute(text("ALTER TABLE scores RENAME COLUMN game4_score TO _g4_old"))
        db.execute(text("ALTER TABLE scores RENAME COLUMN game5_score TO _g5_old"))
        db.commit()
        logger.info("Old columns renamed to _gX_old temp names.")

        # Step 3: Create new columns with default 0
        db.execute(text("ALTER TABLE scores ADD COLUMN game1_score FLOAT NOT NULL DEFAULT 0"))
        db.execute(text("ALTER TABLE scores ADD COLUMN game2_score FLOAT NOT NULL DEFAULT 0"))
        db.execute(text("ALTER TABLE scores ADD COLUMN game3_score FLOAT NOT NULL DEFAULT 0"))
        db.execute(text("ALTER TABLE scores ADD COLUMN game4_score FLOAT NOT NULL DEFAULT 0"))
        db.execute(text("ALTER TABLE scores ADD COLUMN game5_score FLOAT NOT NULL DEFAULT 0"))
        db.commit()
        logger.info("New game1_score~game5_score columns created.")

        # Step 4: Copy data with new mapping
        # Old G2→New G1, Old G3→New G2, Old G4→New G3, Old G5→New G4, New G5=0
        db.execute(text("UPDATE scores SET game1_score = COALESCE(_g2_old, 0)"))
        db.execute(text("UPDATE scores SET game2_score = COALESCE(_g3_old, 0)"))
        db.execute(text("UPDATE scores SET game3_score = COALESCE(_g4_old, 0)"))
        db.execute(text("UPDATE scores SET game4_score = COALESCE(_g5_old, 0)"))
        db.commit()
        logger.info("Data copied: old G2→new G1, G3→G2, G4→G3, G5→G4. New G5=0.")

        # Step 5: Recalculate total_score
        db.execute(text("""
            UPDATE scores SET total_score =
                COALESCE(game1_score, 0) + COALESCE(game2_score, 0) +
                COALESCE(game3_score, 0) + COALESCE(game4_score, 0) + COALESCE(game5_score, 0)
        """))
        db.commit()
        logger.info("total_score recalculated = G1+G2+G3+G4+G5.")

        # Step 6: Drop temp columns
        db.execute(text("ALTER TABLE scores DROP COLUMN _g1_old"))
        db.execute(text("ALTER TABLE scores DROP COLUMN _g2_old"))
        db.execute(text("ALTER TABLE scores DROP COLUMN _g3_old"))
        db.execute(text("ALTER TABLE scores DROP COLUMN _g4_old"))
        db.execute(text("ALTER TABLE scores DROP COLUMN _g5_old"))
        db.commit()
        logger.info("Temp columns _gX_old dropped.")

        # Step 7: Set idempotency marker so migration never runs again
        db.execute(text("ALTER TABLE scores ADD COLUMN _migrated_v2 BOOLEAN DEFAULT TRUE"))
        db.commit()
        logger.info("Migration complete! _migrated_v2 flag set.")

        # Step 7: Verify
        count = db.execute(text("SELECT COUNT(*) FROM scores")).scalar()
        logger.info("Total scores rows after migration: %d", count)

    except Exception as e:
        db.rollback()
        logger.error("Migration failed: %s", e)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
