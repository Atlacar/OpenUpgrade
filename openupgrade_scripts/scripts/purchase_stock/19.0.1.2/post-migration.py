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


def stock_warehouse_buy_to_resupply(env):
    """
    stock.warehouse#buy_to_resupply is no longer stored: v19 computes it as
    "the warehouse is in the warehouses of the Buy route" (and writing a warehouse
    deactivates its buy rule when it is False). Link the Buy route of the warehouse
    (route of its buy rule, else purchase_stock.route_warehouse0_buy) to every
    warehouse that had buy_to_resupply set in v18.
    """
    if not openupgrade.column_exists(env.cr, "stock_warehouse", "buy_to_resupply"):
        return
    buy_route = env.ref("purchase_stock.route_warehouse0_buy", raise_if_not_found=False)
    openupgrade.logged_query(
        env.cr,
        """
        INSERT INTO stock_route_warehouse (route_id, warehouse_id)
        SELECT DISTINCT COALESCE(sr.route_id, %s), sw.id
        FROM stock_warehouse sw
        LEFT JOIN stock_rule sr ON sr.id = sw.buy_pull_id
        WHERE sw.buy_to_resupply
            AND COALESCE(sr.route_id, %s) IS NOT NULL
        ON CONFLICT DO NOTHING
        """,
        (buy_route.id if buy_route else None, buy_route.id if buy_route else None),
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
    stock_warehouse_buy_to_resupply(env)
