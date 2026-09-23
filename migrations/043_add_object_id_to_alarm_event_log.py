"""Peewee migrations -- 043_add_object_id_to_alarm_event_log.py.

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


def _add_object_id_if_missing(migrator, database, fake=False):
    """Add alarmeventlog.object_id only when it is not already present.

    SQLite has no ALTER TABLE ... ADD COLUMN IF NOT EXISTS, and a bare ADD
    COLUMN against an existing column aborts the whole migration run, which
    takes Frigate's startup down with it -- the API never binds :5001 and every
    request 500s behind nginx.

    The guard is needed because this migration was renumbered: it shipped once
    as 039_add_object_id_to_alarm_event_log, before upstream claimed 036-039.
    peewee_migrate keys applied migrations by filename, so on a database
    created by that earlier build the new name looks unapplied and runs again.
    """
    if fake:
        return

    columns = {
        row[1] for row in database.execute_sql('PRAGMA table_info("alarmeventlog")')
    }

    if "object_id" in columns:
        return

    database.execute_sql(
        'ALTER TABLE "alarmeventlog" ADD COLUMN "object_id" VARCHAR(30) NULL'
    )


def migrate(migrator, database, fake=False, **kwargs):
    migrator.python(_add_object_id_if_missing, migrator, database, fake=fake)
    migrator.sql(
        'CREATE INDEX IF NOT EXISTS "alarmeventlog_object_id" ON "alarmeventlog" ("object_id")'
    )


def rollback(migrator, database, fake=False, **kwargs):
    migrator.sql('DROP INDEX IF EXISTS "alarmeventlog_object_id"')
    migrator.sql('ALTER TABLE "alarmeventlog" DROP COLUMN "object_id"')
