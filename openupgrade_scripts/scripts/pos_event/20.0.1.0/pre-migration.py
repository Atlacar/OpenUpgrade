# Copyright 2026 Hunki Enterprises BV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def new_uuid_columns(env):
    """
    The python default of the new uuid fields is evaluated once by the ORM, which
    would give the same uuid to every existing row. Generate one per row.
    """
    cr = env.cr
    for table in ("event_registration", "event_registration_answer"):
        if not openupgrade.column_exists(cr, table, "uuid"):
            openupgrade.logged_query(cr, f"ALTER TABLE {table} ADD COLUMN uuid varchar")
        openupgrade.logged_query(
            cr, f"UPDATE {table} SET uuid = gen_random_uuid()::text WHERE uuid IS NULL"
        )


@openupgrade.migrate()
def migrate(env, version):
    new_uuid_columns(env)
