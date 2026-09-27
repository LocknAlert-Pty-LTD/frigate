#!/usr/bin/env python3
"""Reproduce Frigate's startup database work against a copy of a real database.

When Frigate dies during startup, nginx stays up and every /api/* returns 500
with nothing in the log but

    connect() failed (111: Connection refused) ... upstream:
    "http://127.0.0.1:5001/auth"

because uvicorn never bound :5001. That message names the symptom, never the
cause. Database migration is one of the few things that runs early enough to
cause it, so this replays exactly that step -- the same repair-then-Router.run()
sequence FrigateApp.init_database() performs -- and prints the real traceback.

**Always operates on a temporary copy.** The source database is opened read-only
to make the copy and is never written to, so this is safe to point at a live
production file.

A clean run here does NOT mean Frigate will start: it only clears migrations.
If this passes, the crash is later in startup and the container log is the
place to look.

Usage:
    python3 scripts/diagnose_db.py /path/to/frigate.db

To pull the database out of a running (or crash-looping) container first:
    docker cp frigate:/config/frigate.db ./frigate-copy.db
    python3 scripts/diagnose_db.py ./frigate-copy.db
"""

from __future__ import annotations

import argparse
import logging
import pathlib
import shutil
import sys
import tempfile
import traceback

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

MIGRATE_DIR = REPO_ROOT / "migrations"


def heading(text: str) -> None:
    print()
    print(text)
    print("-" * len(text))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", help="path to frigate.db (never modified)")
    parser.add_argument(
        "--keep",
        action="store_true",
        help="keep the temporary copy and print its path",
    )
    args = parser.parse_args()

    source = pathlib.Path(args.database).expanduser().resolve()
    if not source.is_file():
        sys.exit(f"No such database: {source}")

    try:
        from peewee_migrate import Router
        from playhouse.sqlite_ext import SqliteExtDatabase
    except ImportError as exc:
        sys.exit(
            f"Missing a dependency ({exc.name}). Install the pinned versions:\n\n"
            '  pip install "peewee==3.17.*" "peewee_migrate==1.14.*"\n'
        )

    from frigate.util.migration_history import (
        RENUMBERED_MIGRATIONS,
        repair_renumbered_migration_history,
    )

    workdir = pathlib.Path(tempfile.mkdtemp(prefix="frigate-dbcheck-"))
    copy = workdir / "frigate.db"
    shutil.copyfile(source, copy)
    print(f"Source   : {source}")
    print(f"Working  : {copy}   (a copy; the source is not touched)")

    logging.disable(logging.CRITICAL)
    db = SqliteExtDatabase(str(copy))

    on_disk = {p.stem for p in MIGRATE_DIR.glob("*.py") if p.name[0].isdigit()}

    heading("Applied migrations recorded in this database")
    tables = {
        row[0]
        for row in db.execute_sql("SELECT name FROM sqlite_master WHERE type='table'")
    }
    if "migratehistory" not in tables:
        print("  none - no migratehistory table (this database is brand new)")
        applied: list[str] = []
    else:
        applied = [
            row[0]
            for row in db.execute_sql("SELECT name FROM migratehistory ORDER BY id")
        ]
        print(f"  {len(applied)} applied, most recent last:")
        for name in applied[-6:]:
            print(f"    {name}")

    heading("Recorded migrations with no matching file")
    orphans = [name for name in applied if name not in on_disk]
    if orphans:
        for name in orphans:
            fixed = RENUMBERED_MIGRATIONS.get(name)
            note = f"  -> renamed to {fixed}" if fixed else "  -> UNKNOWN"
            print(f"    {name}{note}")
        print()
        print("  These are fatal on their own. Router.migrator replays every")
        print("  recorded name by reading its file, so a missing one raises")
        print("  FileNotFoundError before any SQL runs.")
    else:
        print("  none")

    heading("Repairing renumbered history entries")
    repaired = repair_renumbered_migration_history(db)
    if repaired:
        for old, new in repaired:
            print(f"    {old} -> {new}")
    else:
        print("  nothing to repair")

    heading("Running migrations")
    try:
        router = Router(db, migrate_dir=str(MIGRATE_DIR))
        pending = list(router.diff)
        print(f"  {len(pending)} pending:")
        for name in pending:
            print(f"    {name}")
        router.run()
    except Exception:
        print()
        print("  MIGRATION FAILED -- this is very likely why Frigate will not start.")
        print()
        traceback.print_exc()
        if args.keep:
            print(f"\nCopy kept at {copy}")
        else:
            shutil.rmtree(workdir, ignore_errors=True)
        return 1

    print("  migrations completed")

    heading("Result")
    print("  Migrations are NOT the problem: the full chain applied cleanly")
    print("  against a copy of this database.")
    print()
    print("  Look at the container log for the real traceback:")
    print("    docker compose logs frigate --no-log-prefix 2>&1 \\")
    print("      | grep -viE 'nginx|GET /|POST /' | tail -80")
    print()
    print("  And check the config, the other common startup killer:")
    print("    docker compose run --rm --entrypoint= frigate \\")
    print("      python3 -m frigate --validate-config")

    if args.keep:
        print(f"\nCopy kept at {copy}")
    else:
        shutil.rmtree(workdir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
