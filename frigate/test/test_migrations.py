"""Migrations must apply cleanly, including on databases from an earlier build.

These run the *real* peewee_migrate Router against a real SQLite file, the same
way FrigateApp.init_database() does, rather than a stand-in. That matters: a
shim would not have caught that `Migrator` in the pinned peewee_migrate 1.14
has no `python()` method, even though the boilerplate docstring in every
migration advertises one.

Motivation: the four alarm migrations were renumbered 036-039 -> 040-043 after
upstream claimed 036-039. peewee_migrate keys applied migrations by *filename*,
so on a database created by the earlier build the renamed files look unapplied
and run a second time. A migration that is not idempotent then fails, and a
failed migration aborts startup -- uvicorn never binds 127.0.0.1:5001 and every
request 500s behind nginx, with nothing in the log but "connect() failed (111:
Connection refused)".

Needs only peewee, peewee_migrate and sqlite3, so it runs on a bare host as
well as in the container.
"""

import logging
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from peewee_migrate import Router
from playhouse.sqlite_ext import SqliteExtDatabase

from frigate.util.migration_history import (
    RENUMBERED_MIGRATIONS,
    repair_renumbered_migration_history,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATE_DIR = REPO_ROOT / "migrations"

# The alarm migrations, under the names they shipped with before the renumber.
RENAMED = {
    "040_create_alarm_audit_log_table": "036_create_alarm_audit_log_table",
    "041_create_zone_join_tables": "037_create_zone_join_tables",
    "042_create_alarm_event_log_table": "038_create_alarm_event_log_table",
    "043_add_object_id_to_alarm_event_log": "039_add_object_id_to_alarm_event_log",
}

LAST_SHARED_MIGRATION = "035_add_motion_heatmap"

# a "#" comment may legitimately name a method that does not exist, e.g. to
# explain why it is not used, so comments are stripped before scanning
COMMENT_RE = re.compile("#[^" + chr(10) + "]*")


class MigrationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        logging.disable(logging.CRITICAL)
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.addCleanup(logging.disable, logging.NOTSET)
        self.path = str(Path(self.tmp) / "frigate.db")
        self.db = SqliteExtDatabase(self.path)
        self.addCleanup(self.db.close)

    def router(self) -> Router:
        return Router(self.db, migrate_dir=str(MIGRATE_DIR))

    def columns(self, table: str) -> set:
        return {row[1] for row in self.db.execute_sql(f'PRAGMA table_info("{table}")')}

    def tables(self) -> set:
        return {
            row[0]
            for row in self.db.execute_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

    def history(self) -> list:
        return [
            row[0]
            for row in self.db.execute_sql(
                "SELECT name FROM migratehistory ORDER BY id"
            )
        ]


class TestFreshDatabase(MigrationTestCase):
    def test_every_migration_applies(self) -> None:
        router = self.router()
        self.assertGreater(len(router.diff), 0, "no migrations discovered")

        router.run()

        self.assertEqual(len(self.router().diff), 0, "migrations left pending")

    def test_fork_tables_exist_with_expected_shape(self) -> None:
        self.router().run()
        tables = self.tables()

        for table in (
            "alarmauditlog",
            "alarmeventlog",
            "eventzone",
            "reviewsegmentzone",
        ):
            self.assertIn(table, tables)

        self.assertIn("object_id", self.columns("alarmeventlog"))
        self.assertIn("false_alarm", self.columns("alarmeventlog"))
        self.assertEqual({"id", "event_id", "zone"}, self.columns("eventzone"))

    def test_running_twice_is_a_noop(self) -> None:
        self.router().run()
        before = self.history()

        self.router().run()  # must not raise

        self.assertEqual(before, self.history())


class TestDatabaseFromEarlierBuild(MigrationTestCase):
    """The deployed case: a database created before the alarm renumber."""

    def _simulate_old_build(self) -> None:
        # Everything up to the point where the two histories agree.
        self.router().run(LAST_SHARED_MIGRATION)

        # Then the alarm migrations as the old build applied them: same schema,
        # recorded under their old filenames. Upstream's 036-039 did not exist
        # yet, so they are absent from history and run for the first time on
        # upgrade, exactly as on the deployed database.
        router = self.router()
        for current, legacy in RENAMED.items():
            router.run_one(current, router.migrator, fake=False, force=True)
            self.db.execute_sql(
                "UPDATE migratehistory SET name = ? WHERE name = ?", (legacy, current)
            )

    def test_old_alarm_migrations_are_recorded_under_legacy_names(self) -> None:
        self._simulate_old_build()
        history = self.history()

        for legacy in RENAMED.values():
            self.assertIn(legacy, history)
        for current in RENAMED:
            self.assertNotIn(current, history)

        self.assertIn("object_id", self.columns("alarmeventlog"))

    def test_router_cannot_even_be_built_without_the_repair(self) -> None:
        """Why the repair exists at all.

        Router.migrator is a cached property that replays every name in the
        history table by reading its file. A renamed migration therefore blows
        up before any SQL runs -- this is what takes Kestrel's startup down,
        not the duplicate column.
        """
        self._simulate_old_build()

        with self.assertRaises(FileNotFoundError):
            self.router().run()

    def test_upgrade_from_old_build_succeeds_after_repair(self) -> None:
        """The full startup path: repair history, then migrate."""
        self._simulate_old_build()

        repaired = repair_renumbered_migration_history(self.db)
        self.assertEqual(len(repaired), len(RENAMED))

        self.router().run()

        self.assertEqual(len(self.router().diff), 0)
        self.assertIn("object_id", self.columns("alarmeventlog"))
        for current in RENAMED:
            self.assertIn(current, self.history())

    def test_upgrade_preserves_existing_alarm_rows(self) -> None:
        """Re-running the renamed migrations must not drop data."""
        self._simulate_old_build()
        repair_renumbered_migration_history(self.db)
        self.db.execute_sql(
            'INSERT INTO "alarmeventlog" '
            '("timestamp", "event_type", "camera", "source", "false_alarm") '
            "VALUES ('2026-01-01 00:00:00', 'burglary', 'driveway', 'api', 0)"
        )

        self.router().run()

        rows = list(self.db.execute_sql('SELECT camera FROM "alarmeventlog"'))
        self.assertEqual([("driveway",)], rows)


class TestMigrationFilesAreWellFormed(unittest.TestCase):
    """Cheap static guards against the two mistakes already made here."""

    def migration_files(self) -> list:
        return sorted(p for p in MIGRATE_DIR.glob("*.py") if p.name[0].isdigit())

    def test_numeric_prefixes_are_unique(self) -> None:
        """A duplicate prefix makes apply order ambiguous.

        This is what the 036-039 collision with upstream looked like.
        """
        prefixes = {}
        for path in self.migration_files():
            prefix = path.name.split("_", 1)[0]
            self.assertNotIn(
                prefix,
                prefixes,
                f"migrations {prefixes.get(prefix)} and {path.name} share "
                f"prefix {prefix}",
            )
            prefixes[prefix] = path.name

    def test_no_migration_calls_a_missing_migrator_method(self) -> None:
        """Every migrator.<attr>() used must exist on the pinned Migrator.

        The docstring boilerplate copied into each migration advertises
        `migrator.python(...)`, which peewee_migrate 1.14's Migrator does not
        implement. Using it fails only at runtime, during startup.
        """
        from peewee_migrate.migrator import Migrator

        available = {m for m in dir(Migrator) if not m.startswith("_")}

        for path in self.migration_files():
            source = path.read_text(encoding="utf-8")
            # skip the module docstring, which lists methods as examples
            body = source.split("import peewee as pw", 1)[-1]
            # drop comments too: a comment may legitimately name a method that
            # does not exist, e.g. explaining why it is not used
            body = re.sub(COMMENT_RE, "", body)
            for used in set(re.findall(r"migrator\.([a-z_]+)\s*\(", body)):
                self.assertIn(
                    used,
                    available,
                    f"{path.name} calls migrator.{used}(), which does not exist "
                    f"on peewee_migrate's Migrator",
                )


if __name__ == "__main__":
    unittest.main()
