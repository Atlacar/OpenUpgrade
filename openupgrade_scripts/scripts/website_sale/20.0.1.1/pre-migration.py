# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

_renamed_fields = [
    (
        "website",
        "website",
        "send_abandoned_cart_email",
        "send_abandoned_cart_followup",
    ),
    # both translatable (jsonb)
    (
        "website",
        "website",
        "contact_us_button_url",
        "contact_us_link_url",
    ),
]

_added_fields = [
    (
        "assigned_website_id",
        "sale.order",
        "sale_order",
        "many2one",
        None,
        "website_sale",
    ),
]


# (model, fields, old module, new module): fields now defined by website_sale
_moved_fields = [
    (
        model,
        [
            "allow_out_of_stock_order",
            "available_threshold",
            "out_of_stock_message",
            "show_availability",
        ],
        "website_sale_stock",
        "website_sale",
    )
    for model in ("product.product", "product.template")
] + [
    (
        "product.document",
        ["attached_on_sale"],
        "sale_pdf_quote_builder",
        "website_sale",
    ),
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


def product_document_attached_on_sale(env):
    """The boolean product.document#shown_on_product_page is now a key of the
    selection attached_on_sale. The key 'inside' of sale_pdf_quote_builder is
    gone: the documents are included in the quotation pdf when 'hidden' or
    'shown_on_product_page'. A document can only have one value: the
    publication on the website only wins over the default ('hidden').
    """
    # also done by the sale_pdf_quote_builder pre, whichever module loads first
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE product_document SET attached_on_sale = 'hidden'
        WHERE attached_on_sale = 'inside'
        """,
    )
    if not openupgrade.column_exists(
        env.cr, "product_document", "shown_on_product_page"
    ):
        return
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE product_document
        SET attached_on_sale = 'shown_on_product_page'
        WHERE shown_on_product_page IS TRUE
            AND COALESCE(attached_on_sale, 'hidden') IN ('hidden', 'inside')
        """,
    )


def sale_order_assigned_website(env):
    """assigned_website_id mirrors website_id (see
    `_compute_assigned_website_id`)
    """
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE sale_order SET assigned_website_id = website_id
        WHERE website_id IS NOT NULL
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    for model, field_names, old_module, new_module in _moved_fields:
        move_fields(env, model, field_names, old_module, new_module)
    openupgrade.rename_fields(env, _renamed_fields)
    openupgrade.add_fields(env, _added_fields)
    product_document_attached_on_sale(env)
    sale_order_assigned_website(env)
