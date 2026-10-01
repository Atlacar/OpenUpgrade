# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

_renamed_fields = [
    # same selection keys (no, cost, sales_price)
    (
        "product.template",
        "product_template",
        "expense_policy",
        "reinvoice_policy",
    ),
]

_added_fields = [
    (
        "section_qty",
        "sale.order.line",
        "sale_order_line",
        "float",
        None,
        "sale",
    ),
    (
        "section_uom_id",
        "sale.order.line",
        "sale_order_line",
        "many2one",
        None,
        "sale",
    ),
    (
        "document_tax_mode",
        "sale.order",
        "sale_order",
        "selection",
        None,
        "sale",
    ),
]


# (model, fields, old module, new module): fields now defined by sale. sale is
# loaded before the old modules, move the xmlids of the field definitions now
# so that the columns are kept when the old module is processed.
_moved_fields = [
    (
        "sale.order",
        ["delivery_status", "incoterm", "incoterm_location"],
        "sale_stock",
        "sale",
    ),
    (
        "sale.order.line",
        [
            "display_qty_widget",
            "is_storable",
            "qty_available_today",
            "scheduled_date",
            "virtual_available_at_date",
        ],
        "sale_stock",
        "sale",
    ),
    (
        "sale.order.line",
        ["deferred_revenue", "invoice_to_be_issued"],
        "sale_account_accountant",
        "sale",
    ),
    ("sale.order", ["amount_unpaid"], "pos_sale", "sale"),
]


def move_fields(env, model, field_names, old_module, new_module):
    """Move the xmlids of field definitions from a module to another. Tolerant
    version of openupgrade.update_module_moved_fields: if the new xmlid already
    exists the stale old one is deleted instead of violating the unique key.
    """
    env.cr.execute(
        """
        SELECT old.id, EXISTS (
            SELECT 1 FROM ir_model_data new
            WHERE new.module = %s AND new.name = old.name
        )
        FROM ir_model_data old
        JOIN ir_model_fields f ON f.id = old.res_id
        WHERE old.model = 'ir.model.fields' AND old.module = %s
            AND f.model = %s AND f.name IN %s
        """,
        (new_module, old_module, model, tuple(field_names)),
    )
    for imd_id, new_exists in env.cr.fetchall():
        if new_exists:
            env.cr.execute("DELETE FROM ir_model_data WHERE id = %s", (imd_id,))
        else:
            env.cr.execute(
                "UPDATE ir_model_data SET module = %s WHERE id = %s",
                (new_module, imd_id),
            )


def product_template_sale_delay(env):
    """product.template#sale_delay (moved from stock to sale) is company
    dependent in 20.0, i.e. a jsonb column. Keep the integer column under its
    legacy name, the values are restored in post-migration.
    """
    env.cr.execute(
        """
        SELECT data_type FROM information_schema.columns
        WHERE table_schema = current_schema AND table_name = 'product_template'
            AND column_name = 'sale_delay'
        """
    )
    row = env.cr.fetchone()
    if row and row[0] != "jsonb":
        openupgrade.rename_columns(env.cr, {"product_template": [("sale_delay", None)]})


def sale_order_line_sections(env):
    """New stored computed fields section_qty / section_uom_id: sections and
    subsections get 1 unit, other lines 0 / NULL (see `_compute_section_qty`).
    Filling them here avoids a computation by the ORM on every line.
    """
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE sale_order_line
        SET section_qty = CASE
                WHEN display_type IN ('line_section', 'line_subsection')
                THEN 1.0 ELSE 0.0 END
        """,
    )
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE sale_order_line sol
        SET section_uom_id = imd.res_id
        FROM ir_model_data imd
        WHERE imd.module = 'uom' AND imd.name = 'product_uom_unit'
            AND imd.model = 'uom.uom'
            AND sol.display_type IN ('line_section', 'line_subsection')
        """,
    )


def sale_order_document_tax_mode(env):
    """New required stored field sale.order#document_tax_mode, computed from
    the company setting res.company#account_price_include.
    """
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE sale_order so
        SET document_tax_mode = COALESCE(
            company.account_price_include, 'tax_excluded')
        FROM res_company company
        WHERE company.id = so.company_id
        """,
    )
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE sale_order SET document_tax_mode = 'tax_excluded'
        WHERE document_tax_mode IS NULL
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    for model, field_names, old_module, new_module in _moved_fields:
        move_fields(env, model, field_names, old_module, new_module)
    openupgrade.rename_fields(env, _renamed_fields)
    openupgrade.add_fields(env, _added_fields)
    product_template_sale_delay(env)
    sale_order_line_sections(env)
    sale_order_document_tax_mode(env)
    # the 19 window action got the same xmlid as the new server action of 20
    # (found record of different model ir.actions.act_window at data load)
    openupgrade.delete_records_safely_by_xml_id(
        env, ["sale.action_accrued_revenue_entry_sale_order_line"]
    )
