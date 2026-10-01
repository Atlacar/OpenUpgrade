# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

# generic checkout steps new in 20.0 (hidden steps of the checkout flow)
_NEW_CHECKOUT_STEP_HREFS = ("/shop/address", "/shop/payment/transaction")


def website_prevent_sale(env):
    """website#prevent_zero_price_sale -> prevent_sale for 0 price products"""
    if not openupgrade.column_exists(env.cr, "website", "prevent_zero_price_sale"):
        return
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE website
        SET prevent_sale = TRUE, prevent_sale_for = 'zero_price'
        WHERE prevent_zero_price_sale IS TRUE
        """,
    )


def website_category_display(env):
    """The display options of the category page moved from each
    product.public.category to the website: the website option is enabled as
    soon as one of the categories of the website had it enabled.
    """
    if not openupgrade.column_exists(
        env.cr, "product_public_category", "show_category_description"
    ):
        return
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE website w
        SET show_category_title = COALESCE(s.title, FALSE),
            show_category_description = COALESCE(s.description, TRUE),
            align_category_content = COALESCE(s.align, FALSE)
        FROM (
            SELECT website.id,
                BOOL_OR(category.show_category_title) AS title,
                BOOL_OR(category.show_category_description) AS description,
                BOOL_OR(category.align_category_content) AS align
            FROM website
            JOIN product_public_category category
                ON category.website_id IS NULL OR category.website_id = website.id
            GROUP BY website.id
        ) s
        WHERE s.id = w.id
        """,
    )


def website_checkout_steps(env):
    """Create the website specific copies of the checkout steps added in 20.0"""
    Step = env["website.checkout.step"].sudo()
    generic_steps = Step.search(
        [("website_id", "=", False), ("step_href", "in", _NEW_CHECKOUT_STEP_HREFS)]
    )
    for website in env["website"].search([]):
        for step in generic_steps:
            if not Step.search_count(
                [("website_id", "=", website.id), ("step_href", "=", step.step_href)]
            ):
                step.copy({"website_id": website.id, "is_published": True})


def product_image_variant(env):
    """product.image#product_variant_id (image of a single variant) is replaced
    by attribute_value_ids: the image is shown for the variants having the
    attribute values of the variant it was linked to.
    """
    if not openupgrade.column_exists(env.cr, "product_image", "product_variant_id"):
        return
    openupgrade.logged_query(
        env.cr,
        """
        INSERT INTO product_image_attribute_value_rel (
            product_image_id, product_template_attribute_value_id
        )
        SELECT image.id, combination.product_template_attribute_value_id
        FROM product_image image
        JOIN product_variant_combination combination
            ON combination.product_product_id = image.product_variant_id
        WHERE image.product_variant_id IS NOT NULL
        ON CONFLICT DO NOTHING
        """,
    )
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE product_image image
        SET product_tmpl_id = product.product_tmpl_id
        FROM product_product product
        WHERE image.product_variant_id = product.id AND image.product_tmpl_id IS NULL
        """,
    )


def product_stock_notification(env):
    """product.product#stock_notification_partner_ids (website_sale_stock) is
    replaced by the model product.stock.notification, which also stores the
    website. The legacy relation had none: use the first website.
    """
    if not openupgrade.table_exists(env.cr, "stock_notification_product_partner_rel"):
        return
    openupgrade.logged_query(
        env.cr,
        """
        INSERT INTO product_stock_notification_rel (
            product_id, partner_id, website_id
        )
        SELECT rel.product_product_id, rel.res_partner_id, website.id
        FROM stock_notification_product_partner_rel rel
        CROSS JOIN (SELECT id FROM website ORDER BY sequence, id LIMIT 1) website
        ON CONFLICT DO NOTHING
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.load_data(env, "website_sale", "20.0.1.1/noupdate_changes.xml")
    openupgrade.delete_record_translations(
        env.cr,
        "website_sale",
        ["mail_template_sale_cart_recovery"],
        ["body_html"],
    )
    website_prevent_sale(env)
    website_category_display(env)
    website_checkout_steps(env)
    product_image_variant(env)
    product_stock_notification(env)
