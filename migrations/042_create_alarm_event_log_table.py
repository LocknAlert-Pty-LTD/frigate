"""Peewee migrations -- 042_create_alarm_event_log_table.py.

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
        CREATE TABLE IF NOT EXISTS "alarmeventlog" (
            "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            "timestamp" DATETIME NOT NULL,
            "event_type" VARCHAR(30) NOT NULL,
            "camera" VARCHAR(20) NOT NULL,
            "zone" VARCHAR(50) NULL,
            "object_type" VARCHAR(50) NULL,
            "confidence" REAL NULL,
            "source" VARCHAR(10) NOT NULL,
            "message" TEXT NULL,
            "false_alarm" INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    migrator.sql(
        'CREATE INDEX IF NOT EXISTS "alarmeventlog_timestamp" ON "alarmeventlog" ("timestamp")'
    )
    migrator.sql(
        'CREATE INDEX IF NOT EXISTS "alarmeventlog_event_type" ON "alarmeventlog" ("event_type")'
    )


def rollback(migrator, database, fake=False, **kwargs):
    pass
