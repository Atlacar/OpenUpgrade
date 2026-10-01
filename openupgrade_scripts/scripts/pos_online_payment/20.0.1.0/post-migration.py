# Copyright 2026 Hunki Enterprises BV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def pos_payment_method_online_type(env):
    """
    pos.payment.method#is_online_payment is replaced by the selection value 'online'
    of the stored pos.payment.method#type (filled by the point_of_sale pre script)
    """
    cr = env.cr
    if not openupgrade.column_exists(cr, "pos_payment_method", "is_online_payment"):
        return
    openupgrade.logged_query(
        cr,
        "UPDATE pos_payment_method SET type = 'online' WHERE is_online_payment",
    )


@openupgrade.migrate()
def migrate(env, version):
    pos_payment_method_online_type(env)
