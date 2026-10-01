# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

# Fields defined by 'stock_account' in Odoo 19 and by 'account' in Odoo 20.
# 'account' is loaded before 'stock_account'. The pre-migration of 'account' may
# already have moved the xmlids, in that case the helper below does nothing,
# otherwise it drops the stale 'stock_account' xmlids, so that the field records
# (and with them the stored columns) are not removed when 'stock_account' loads.
_moved_fields = [
    ("account.account", ["account_stock_expense_id", "account_stock_variation_id"]),
    ("account.move.line", ["cogs_origin_id"]),
    (
        "product.category",
        [
            "account_stock_variation_id",
            "property_cost_method",
            "property_price_difference_account_id",
            "property_stock_journal",
            "property_stock_valuation_account_id",
            "property_valuation",
        ],
    ),
    ("product.product", ["cost_method", "valuation"]),
    ("product.template", ["cost_method", "valuation"]),
    (
        "res.company",
        [
            "account_stock_journal_id",
            "account_stock_valuation_id",
            "cost_method",
            "inventory_period",
            "inventory_valuation",
        ],
    ),
]

_renamed_xmlids = [
    ("stock_account.ir_cron_post_stock_valuation", "account.ir_cron_post_stock_valuation"),
]


def _move_fields(env, model, fields, old_module, new_module):
    cr = env.cr
    cr.execute(
        """
        SELECT imd.id, imd.name
        FROM ir_model_data imd
        JOIN ir_model_fields imf ON imf.id = imd.res_id
        WHERE imd.model = 'ir.model.fields' AND imd.module = %s
            AND imf.model = %s AND imf.name IN %s
        """,
        (old_module, model, tuple(fields)),
    )
    for imd_id, name in cr.fetchall():
        cr.execute(
            "SELECT 1 FROM ir_model_data WHERE module = %s AND name = %s",
            (new_module, name),
        )
        if cr.fetchone():
            openupgrade.logged_query(
                cr, "DELETE FROM ir_model_data WHERE id = %s", (imd_id,)
            )
        else:
            openupgrade.logged_query(
                cr,
                "UPDATE ir_model_data SET module = %s WHERE id = %s",
                (new_module, imd_id),
            )


def _rename_xmlids_if_free(env):
    cr = env.cr
    for old, new in _renamed_xmlids:
        new_module, new_name = new.split(".")
        cr.execute(
            "SELECT 1 FROM ir_model_data WHERE module = %s AND name = %s",
            (new_module, new_name),
        )
        if not cr.fetchone():
            openupgrade.rename_xmlids(cr, [(old, new)])


def _map_cost_method_fifo(env):
    """The 'fifo' costing method does not exist anymore (standard / average).
    No product category uses it in aquila; map it defensively to 'average' in
    the company dependent column and in the ir.default records."""
    cr = env.cr
    if openupgrade.column_exists(cr, "product_category", "property_cost_method"):
        openupgrade.logged_query(
            cr,
            """
            UPDATE product_category
            SET property_cost_method = REPLACE(
                property_cost_method::text, '"fifo"', '"average"')::jsonb
            WHERE property_cost_method::text LIKE '%%"fifo"%%'
            """,
        )
    openupgrade.logged_query(
        cr,
        """
        UPDATE ir_default d
        SET json_value = '"average"'
        FROM ir_model_fields f
        WHERE f.id = d.field_id AND f.model = 'product.category'
            AND f.name = 'property_cost_method' AND d.json_value = '"fifo"'
        """,
    )
    if openupgrade.column_exists(cr, "res_company", "cost_method"):
        openupgrade.logged_query(
            cr,
            "UPDATE res_company SET cost_method = 'average' "
            "WHERE cost_method = 'fifo'",
        )


@openupgrade.migrate()
def migrate(env, version):
    for model, fields in _moved_fields:
        _move_fields(env, model, fields, "stock_account", "account")
    _rename_xmlids_if_free(env)
    _map_cost_method_fifo(env)
