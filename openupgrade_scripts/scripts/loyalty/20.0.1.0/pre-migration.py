# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

_added_fields = [
    (
        "points_changed_date",
        "loyalty.history",
        "loyalty_history",
        "datetime",
        None,
        "loyalty",
    ),
]


@openupgrade.migrate()
def migrate(env, version):
    # new required field: the date the points moved is the creation date of
    # the history line (the ORM default would be the migration date)
    openupgrade.add_fields(env, _added_fields)
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE loyalty_history
        SET points_changed_date = COALESCE(create_date, write_date, NOW())
        WHERE points_changed_date IS NULL
        """,
    )
