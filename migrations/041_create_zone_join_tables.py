"""Peewee migrations -- 041_create_zone_join_tables.py.

Some examples (model - class or model name)::

    > Model = migrator.orm['model_name']            # Return model in current state by name

    > migrator.sql(sql)                             # Run custom SQL
    > migrator.python(func, *args, **kwargs)        # Run python code
    > migrator.create_model(Model)                  # Create a model (could be used as decorator)
    > migrator.remove_model(model, cascade=True)    # Remove a model
    > migrator.add_fields(model, **fields)          # Add fields to a model
    > migrator.change_fields(model, **fields)       # Change fields
    > migrator.remove_fields(model, *field_names, cascade=True)
    > migrator.rename_field(model, old_field_name, new_field_name)
    > migrator.rename_table(model, new_table_name)
    > migrator.add_index(model, *col_names, unique=False)
    > migrator.drop_index(model, *col_names)
    > migrator.add_not_null(model, *field_names)
    > migrator.drop_not_null(model, *field_names)
    > migrator.add_default(model, field_name, default)

"""

import peewee as pw

SQL = pw.SQL


def migrate(migrator, database, fake=False, **kwargs):
    migrator.sql(
        """
        CREATE TABLE IF NOT EXISTS "eventzone" (
            "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            "event_id" VARCHAR(30) NOT NULL,
            "zone" VARCHAR(100) NOT NULL
        )
        """
    )
    migrator.sql('CREATE INDEX IF NOT EXISTS "eventzone_zone" ON "eventzone" ("zone")')
    migrator.sql(
        'CREATE UNIQUE INDEX IF NOT EXISTS "eventzone_event_id_zone" '
        'ON "eventzone" ("event_id", "zone")'
    )

    migrator.sql(
        """
        CREATE TABLE IF NOT EXISTS "reviewsegmentzone" (
            "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            "review_segment_id" VARCHAR(30) NOT NULL,
            "zone" VARCHAR(100) NOT NULL
        )
        """
    )
    migrator.sql(
        'CREATE INDEX IF NOT EXISTS "reviewsegmentzone_zone" '
        'ON "reviewsegmentzone" ("zone")'
    )
    migrator.sql(
        'CREATE UNIQUE INDEX IF NOT EXISTS "reviewsegmentzone_review_segment_id_zone" '
        'ON "reviewsegmentzone" ("review_segment_id", "zone")'
    )

    # Confirmed a real gap: ReviewSegment.severity has no index at all,
    # and every review-list query sorts by (severity, start_time)
    # together (frigate/api/review.py) -- a compound index matching that
    # exact access pattern lets sqlite satisfy the sort from the index.
    migrator.sql(
        'CREATE INDEX IF NOT EXISTS "reviewsegment_severity_start_time" '
        'ON "reviewsegment" ("severity", "start_time" DESC)'
    )

    # Backfill existing rows so historical data is filterable through the
    # new indexed path immediately, not just events/reviews going
    # forward. Pure SQL via sqlite's json_each() table-valued function
    # (part of the JSON1 extension this codebase already relies on for
    # every JSONField path query) rather than a Python batch loop --
    # sqlite processes this as a single scan either way, and this avoids
    # hand-rolled chunking entirely. Verified json_each() is available in
    # the actual sqlite build Frigate ships before relying on it here.
    migrator.sql(
        """
        INSERT OR IGNORE INTO "eventzone" ("event_id", "zone")
        SELECT "event"."id", "je"."value"
        FROM "event", json_each("event"."zones") AS "je"
        WHERE json_valid("event"."zones")
          AND json_type("event"."zones") = 'array'
        """
    )
    migrator.sql(
        """
        INSERT OR IGNORE INTO "reviewsegmentzone" ("review_segment_id", "zone")
        SELECT "reviewsegment"."id", "je"."value"
        FROM "reviewsegment", json_each("reviewsegment"."data", '$.zones') AS "je"
        WHERE json_valid("reviewsegment"."data")
          AND json_extract("reviewsegment"."data", '$.zones') IS NOT NULL
        """
    )


def rollback(migrator, database, fake=False, **kwargs):
    pass
