"""One-off migration: rewrite every non-admin nickname to the 'JL1' format.

The old rule (Firstname+LastInitial_NNN, e.g. 'JamieL_001') was hard to remember
and type. New rule: initials + smallest free number per initials group.

Admins are excluded: their nickname 'admin@admin.com' is their login identity.

Usage (from cyber_ai_festival_be/):
    python scripts/migrate_nicknames.py --dry-run --database-url "$DATABASE_URL"
    python scripts/migrate_nicknames.py --database-url "$DATABASE_URL"
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text

from app.crud.user import initials_of


def _parse_url(argv: list[str]) -> str | None:
    for i, arg in enumerate(argv):
        if arg == "--database-url" and i + 1 < len(argv):
            return argv[i + 1]
    return os.environ.get("DATABASE_URL")


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    url = _parse_url(sys.argv[1:])
    if not url:
        print("ERROR: pass --database-url <postgres url> or set DATABASE_URL")
        sys.exit(1)

    engine = create_engine(url)
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT id, firstname, lastname, nickname, role FROM users "
            "WHERE role != 'admin' ORDER BY id"
        )).fetchall()

    empty = [r for r in rows if not ((r.firstname or "").strip() and (r.lastname or "").strip())]
    if empty:
        print(f"WARNING: {len(empty)} user(s) have an empty first/last name:")
        for r in empty:
            print(f"  id={r.id} first={r.firstname!r} last={r.lastname!r} nickname={r.nickname!r}")
    else:
        print("OK: no empty first/last names among non-admin users.")

    used: set[str] = {r.nickname for r in rows if r.nickname}
    plan: list[tuple[int, str | None, str]] = []
    for r in rows:
        base = initials_of(r.firstname, r.lastname)
        n = 1
        while f"{base}{n}" in used:
            n += 1
        used.add(f"{base}{n}")
        plan.append((r.id, r.nickname, f"{base}{n}"))

    changed = [(uid, old, new) for uid, old, new in plan if old != new]
    print(f"Total non-admin users: {len(rows)}; to change: {len(changed)}")
    for uid, old, new in changed:
        print(f"  id={uid} {old!r} -> {new!r}")

    if dry_run:
        print("[dry-run] no changes written.")
        return

    with engine.begin() as conn:
        for uid, _old, new in changed:
            conn.execute(text("UPDATE users SET nickname = :n WHERE id = :i"), {"n": new, "i": uid})
    print(f"Applied {len(changed)} nickname updates.")


if __name__ == "__main__":
    main()
