"""Repair migration history rows whose files were renumbered.

peewee_migrate keys applied migrations by filename, and `Router.migrator` is a
cached property that replays **every** name in the history table by reading its
file back off disk:

    for name in self.done:
        self.run_one(name, migrator)      # -> read(name) -> open(<name>.py)

So renaming a migration that some database has already applied does not merely
cause it to re-run -- it makes `Router` raise FileNotFoundError before any SQL
executes. In Kestrel that aborts startup: uvicorn never binds 127.0.0.1:5001,
nginx keeps serving the UI, and every API request returns 500 with nothing in
the log but "connect() failed (111: Connection refused)".

The four alarm migrations were renumbered 036-039 -> 040-043 after upstream
claimed 036-039 for its own migrations, so any database created by the earlier
build carries the old names. Rewriting those rows must happen *before* the
Router is constructed, which is why this is a plain function called from
FrigateApp.init_database() rather than a migration -- a migration cannot fix a
failure that happens while the migrator is being built.

Safe to run on every start: it is a no-op when the history table is absent (a
fresh database) or when no legacy rows are present.
"""

import logging

logger = logging.getLogger(__name__)

# old filename -> current filename
RENUMBERED_MIGRATIONS = {
    "036_create_alarm_audit_log_table": "040_create_alarm_audit_log_table",
    "037_create_zone_join_tables": "041_create_zone_join_tables",
    "038_create_alarm_event_log_table": "042_create_alarm_event_log_table",
    "039_add_object_id_to_alarm_event_log": "043_add_object_id_to_alarm_event_log",
}


def repair_renumbered_migration_history(database) -> list[tuple[str, str]]:
    """Rename history rows left behind by renumbered migrations.

    Returns the (old, new) pairs actually rewritten, for logging and tests.
    """
    table_exists = list(
        database.execute_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='migratehistory'"
        )
    )

    if not table_exists:
        # Fresh database; the Router will create the table itself.
        return []

    existing = {
        row[0] for row in database.execute_sql("SELECT name FROM migratehistory")
    }

    repaired: list[tuple[str, str]] = []

    for old, new in RENUMBERED_MIGRATIONS.items():
        if old not in existing:
            continue

        if new in existing:
            # Both names recorded: the new one already applied, so the stale
            # row is just debris. Drop it rather than creating a duplicate.
            database.execute_sql(
                "DELETE FROM migratehistory WHERE name = ?",
                (old,),
            )
        else:
            database.execute_sql(
                "UPDATE migratehistory SET name = ? WHERE name = ?",
                (new, old),
            )

        repaired.append((old, new))

    if repaired:
        logger.info(
            "Repaired %d renumbered migration history entries: %s",
            len(repaired),
            ", ".join(f"{old} -> {new}" for old, new in repaired),
        )

    return repaired
