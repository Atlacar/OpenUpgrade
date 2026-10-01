# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

_deleted_xmlids = [
    # the cron was moved to 'account' (renamed there); remove it when the module
    # 'account' created its own record
    "stock_account.ir_cron_post_stock_valuation",
]


def _fill_product_value_costs(env):
    """product.value gained quantity / old_cost / new_cost / old_value /
    new_value to document the manual changes of the standard price. The
    valuation itself keeps using product.value.value (new standard price) and
    stock.move.value, which are unchanged. Rebuild what can be rebuilt from the
    history of the same product / lot: new_cost = value, old_cost = value of the
    previous record (0 for the first one). The quantity at the time of the change
    is unknown: old_value and new_value keep their default 0."""
    cr = env.cr
    openupgrade.logged_query(
        cr,
        """
        UPDATE product_value pv
        SET new_cost = h.value,
            old_cost = COALESCE(h.previous_value, 0)
        FROM (
            SELECT id, value, LAG(value) OVER (
                PARTITION BY product_id, lot_id ORDER BY date, id
            ) AS previous_value
            FROM product_value
            WHERE move_id IS NULL
        ) h
        WHERE h.id = pv.id AND pv.new_cost IS NULL
        """,
    )
    # manual change of the value of a move: the new value is the value
    openupgrade.logged_query(
        cr,
        """
        UPDATE product_value
        SET new_value = value
        WHERE move_id IS NOT NULL AND COALESCE(new_value, 0) = 0
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    _fill_product_value_costs(env)
    openupgrade.delete_records_safely_by_xml_id(env, _deleted_xmlids)
