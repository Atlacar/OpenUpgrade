# Copyright 2026 Hunki Enterprises BV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

_deleted_xmlids = [
    "stock_account.stock_valuation_layer_company_rule",
    "stock_account.group_stock_accounting_automatic",
]


def stock_lot_avg_cost(env):
    """
    Precreate stock.lot#avg_cost to avoid compute method
    """
    openupgrade.add_fields(
        env,
        [
            ("avg_cost", "stock.lot", "stock_lot", "float", None, "stock_account", 0),
        ],
    )


def stock_move_is_fields(env):
    """
    Precreate stock.move#is_* to avoid compute method
    """
    openupgrade.add_fields(
        env,
        [
            (
                "is_in",
                "stock.move",
                "stock_move",
                "boolean",
                None,
                "stock_account",
                False,
            ),
            (
                "is_out",
                "stock.move",
                "stock_move",
                "boolean",
                None,
                "stock_account",
                False,
            ),
            (
                "is_dropship",
                "stock.move",
                "stock_move",
                "boolean",
                None,
                "stock_account",
                False,
            ),
        ],
    )


def res_company_cost_method_inventory_valuation(env):
    """
    New required res.company#cost_method and res.company#inventory_valuation: v19
    uses them as the fallback of product.category#property_cost_method /
    property_valuation, and every res.company write resets the company ir.default of
    those category fields from them (_set_category_defaults). Pre-create them from
    the v18 ir.default of the category fields (company-specific, else global), else
    the categories that relied on the default flip to the column default
    ('standard' / 'periodic'). 'manual_periodic' became 'periodic'.
    """
    openupgrade.add_fields(
        env,
        [
            (
                "cost_method",
                "res.company",
                "res_company",
                "selection",
                False,
                "stock_account",
                "standard",
            ),
            (
                "inventory_valuation",
                "res.company",
                "res_company",
                "selection",
                False,
                "stock_account",
                "periodic",
            ),
        ],
    )
    for column, field_name, mapping in (
        ("cost_method", "property_cost_method", {}),
        ("inventory_valuation", "property_valuation", {"manual_periodic": "periodic"}),
    ):
        openupgrade.logged_query(
            env.cr,
            f"""
            WITH defaults AS (
                SELECT idf.company_id, idf.json_value::jsonb #>> '{{}}' AS value
                FROM ir_default idf
                JOIN ir_model_fields imf ON imf.id = idf.field_id
                WHERE imf.model = 'product.category'
                    AND imf.name = %(field_name)s
                    AND idf.condition IS NULL
                    AND jsonb_typeof(idf.json_value::jsonb) = 'string'
            )
            UPDATE res_company rc
            SET {column} = COALESCE(
                (SELECT value FROM defaults WHERE company_id = rc.id),
                (SELECT value FROM defaults WHERE company_id IS NULL),
                rc.{column}
            )
            """,
            {"field_name": field_name},
        )
        for old, new in mapping.items():
            openupgrade.logged_query(
                env.cr,
                f"UPDATE res_company SET {column} = %s WHERE {column} = %s",
                (new, old),
            )


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.delete_records_safely_by_xml_id(env, _deleted_xmlids)
    stock_lot_avg_cost(env)
    stock_move_is_fields(env)
    res_company_cost_method_inventory_valuation(env)
