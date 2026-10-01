# Copyright 2026 Hunki Enterprises BV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def pos_session_logged_employees(env):
    """
    pos.session#logged_employee_ids is new: it collects the employees that logged in
    the session. v19 only knows the current one (pos.session#employee_id).
    """
    field = env["pos.session"]._fields["logged_employee_ids"]
    openupgrade.logged_query(
        env.cr,
        f"""
        INSERT INTO {field.relation} ({field.column1}, {field.column2})
        SELECT id, employee_id
        FROM pos_session
        WHERE employee_id IS NOT NULL
        ON CONFLICT DO NOTHING
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    pos_session_logged_employees(env)
