# Copyright 2026 Hunki Enterprises BV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def purchase_order_line_group_id(env):
    """
    purchase.order.line#group_id is gone (v19 has no line-level procurement group, the
    moves of a line take the order's reference_ids): link the line group to the
    order's stock references so it is kept on the moves created at confirmation.
    """
    openupgrade.logged_query(
        env.cr,
        """
        INSERT INTO stock_reference_purchase_rel (purchase_id, reference_id)
        SELECT DISTINCT pol.order_id, pol.group_id
        FROM purchase_order_line pol
        JOIN stock_reference sr ON sr.id = pol.group_id
        WHERE pol.group_id IS NOT NULL
        ON CONFLICT DO NOTHING
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.m2o_to_x2m(
        env.cr,
        env["purchase.order"],
        "purchase_order",
        "reference_ids",
        "group_id",
    )
    openupgrade.load_data(
        env,
        "purchase_stock",
        "19.0.1.2/noupdate_changes.xml",
        xml_transformation_filename="19.0.1.2/noupdate_changes-transformation.xml",
    )
    purchase_order_line_group_id(env)
