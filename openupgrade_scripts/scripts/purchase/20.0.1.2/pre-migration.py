# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

# (model, fields, old module); all of them are now defined in 'purchase', which
# is loaded before purchase_stock and purchase_accountant
_moved_fields = [
    ("purchase.order", ["incoterm_location", "receipt_status"], "purchase_stock"),
    (
        "purchase.order.line",
        ["bill_to_receive", "prepaid_expense"],
        "purchase_accountant",
    ),
]

_renamed_fields = [
    # uom fields were harmonised to uom_id
    ("purchase.order.line", "purchase_order_line", "product_uom_id", "uom_id"),
]


def _move_fields(env, model, fields, old_module, new_module):
    """Move the xmlid of the field definitions to the new module, tolerating
    that the new module reflected the field already (then the stale xmlid of
    the old module is dropped so that the field record and its column survive)."""
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


def _fill_document_tax_mode(env):
    """purchase.order.document_tax_mode is new (required, computed from the
    company default account_price_include). Fill it in SQL: an order is
    'tax_included' when one of its lines uses a tax that is included in the
    price (override on the tax, else company default), otherwise the company
    default applies."""
    cr = env.cr
    openupgrade.add_fields(
        env,
        [
            (
                "document_tax_mode",
                "purchase.order",
                "purchase_order",
                "selection",
                False,
                "purchase",
            )
        ],
    )
    has_override = openupgrade.column_exists(
        cr, "account_tax", "price_include_override"
    )
    tax_included = (
        """
        t.price_include_override = 'tax_included'
        OR (t.price_include_override IS NULL
            AND tc.account_price_include = 'tax_included')
        """
        if has_override
        else "tc.account_price_include = 'tax_included'"
    )
    openupgrade.logged_query(
        cr,
        f"""
        UPDATE purchase_order po
        SET document_tax_mode = CASE WHEN EXISTS (
            SELECT 1
            FROM purchase_order_line pol
            JOIN account_tax_purchase_order_line_rel r
                ON r.purchase_order_line_id = pol.id
            JOIN account_tax t ON t.id = r.account_tax_id
            JOIN res_company tc ON tc.id = t.company_id
            WHERE pol.order_id = po.id AND ({tax_included})
        ) THEN 'tax_included'
        ELSE COALESCE(
            (SELECT c.account_price_include FROM res_company c
             WHERE c.id = po.company_id), 'tax_excluded')
        END
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    for model, fields, old_module in _moved_fields:
        _move_fields(env, model, fields, old_module, "purchase")
    openupgrade.rename_fields(env, _renamed_fields)
    _fill_document_tax_mode(env)
