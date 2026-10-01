# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

_STOCK_QUANTITY_FIELDS = [
    "free_qty",
    "incoming_qty",
    "is_storable",
    "outgoing_qty",
    "qty_available",
    "show_qty_update_button",
    "virtual_available",
]
_BASE_UNIT_FIELDS = [
    "base_unit_count",
    "base_unit_id",
    "base_unit_name",
    "base_unit_price",
]

# (model, fields, old module)  -> all of them are now defined in 'product'
_moved_fields = [
    ("product.product", _STOCK_QUANTITY_FIELDS, "stock"),
    ("product.template", _STOCK_QUANTITY_FIELDS, "stock"),
    ("product.product", _BASE_UNIT_FIELDS, "website_sale"),
    ("product.template", _BASE_UNIT_FIELDS, "website_sale"),
    ("product.base.unit", ["name", "display_name"], "website_sale"),
]

_renamed_xmlids = [
    ("website_sale.base_unit_action", "product.base_unit_action"),
    ("website_sale.group_show_uom_price", "product.group_show_uom_price"),
]

_renamed_fields = [
    # uom fields were harmonised to uom_id
    (
        "product.supplierinfo",
        "product_supplierinfo",
        "product_uom_id",
        "uom_id",
    ),
]


def _move_fields(env, model, fields, old_module, new_module):
    """Move the xmlid of the field definitions to the new module.

    ``openupgrade.update_module_moved_fields`` only works when the new module did
    not reflect the field yet (UNIQUE (module, name) on ir_model_data). In this
    script the new module is 'product', which is loaded before the old ones, so
    that is the case, but stay tolerant if an xmlid of the new module exists
    already: then the stale xmlid of the old module is simply dropped, so that the
    field record (and its column) is not removed when the old module is updated.
    """
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


def _rename_base_unit_model(env):
    """website.base.unit (website_sale) -> product.base.unit (product)"""
    cr = env.cr
    if openupgrade.table_exists(cr, "website_base_unit") and not (
        openupgrade.table_exists(cr, "product_base_unit")
    ):
        openupgrade.rename_models(cr, [("website.base.unit", "product.base.unit")])
        openupgrade.rename_tables(cr, [("website_base_unit", "product_base_unit")])
    openupgrade.update_module_moved_models(
        cr, "product.base.unit", "website_sale", "product"
    )


def _convert_pricelist_item_compute_price(env):
    """Odoo 19 compute_price: fixed / percentage / formula
    Odoo 20 compute_price: fixed / discount / markup, where the price is always
    base_price * (1 - price_discount / 100) (+ rounding, surcharge, margins), and
    'markup' is only the presentation of -price_discount that keeps the 'Based on'
    selector for the cost.

    * percentage: price = base * (1 - percent_price / 100), nothing else is
      applied (rounding, surcharge and margins were ignored) -> price_discount =
      percent_price and the other price parameters are reset to 0.
    * formula: price = base * (1 - d / 100) + ... with d = price_discount, or
      d = -price_markup when the base is the cost (standard_price) -> price_discount
      = d.
    Rules based on the cost become 'markup', all others 'discount'.
    """
    cr = env.cr
    if not openupgrade.column_exists(cr, "product_pricelist_item", "percent_price"):
        return
    openupgrade.logged_query(
        cr,
        """
        UPDATE product_pricelist_item
        SET price_discount = percent_price,
            price_round = 0,
            price_surcharge = 0,
            price_min_margin = 0,
            price_max_margin = 0
        WHERE compute_price = 'percentage'
        """,
    )
    openupgrade.logged_query(
        cr,
        """
        UPDATE product_pricelist_item
        SET price_discount = -COALESCE(price_markup, 0)
        WHERE compute_price = 'formula' AND base = 'standard_price'
        """,
    )
    openupgrade.logged_query(
        cr,
        """
        UPDATE product_pricelist_item
        SET compute_price = CASE WHEN base = 'standard_price'
            THEN 'markup' ELSE 'discount' END
        WHERE compute_price IN ('percentage', 'formula')
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    for model, fields, old_module in _moved_fields:
        _move_fields(env, model, fields, old_module, "product")
    # product.product.qty_available is now a stored company_dependent float (jsonb)
    # in 'product' (stock turns it back into a non stored computed field); the old
    # numeric column is a stale leftover of a non stored field (recomputed by stock)
    # and the ORM cannot cast numeric to jsonb.
    openupgrade.drop_columns(env.cr, [("product_product", "qty_available")])
    _rename_base_unit_model(env)
    openupgrade.rename_xmlids(env.cr, _renamed_xmlids)
    openupgrade.rename_fields(env, _renamed_fields)
    _convert_pricelist_item_compute_price(env)
