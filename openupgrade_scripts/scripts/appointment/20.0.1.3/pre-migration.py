# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def appointment_type_responsible(env):
    """appointment.type#responsible_id is new (default: the current user, which
    would be the superuser during the migration): take the first staff user, or
    the creator of the appointment type.
    """
    cr = env.cr
    openupgrade.add_columns(
        env,
        [("appointment.type", "responsible_id", "many2one", None, "appointment_type")],
    )
    if openupgrade.table_exists(cr, "appointment_type_res_users_rel"):
        openupgrade.logged_query(
            cr,
            """
            UPDATE appointment_type t
            SET responsible_id = (
                SELECT min(rel.res_users_id)
                FROM appointment_type_res_users_rel rel
                WHERE rel.appointment_type_id = t.id
            )
            WHERE t.responsible_id IS NULL
            """,
        )
    openupgrade.logged_query(
        cr,
        "UPDATE appointment_type SET responsible_id = create_uid "
        "WHERE responsible_id IS NULL",
    )


@openupgrade.migrate()
def migrate(env, version):
    appointment_type_responsible(env)
