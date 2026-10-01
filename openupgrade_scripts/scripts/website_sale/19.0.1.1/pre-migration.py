# Copyright 2026 Hunki Enterprises BV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def website_add_to_cart_action(env):
    """
    website#add_to_cart_action == force_dialog has been removed, map to stay
    """
    openupgrade.copy_columns(env.cr, {"website": [("add_to_cart_action", None, None)]})
    openupgrade.map_values(
        env.cr,
        openupgrade.get_legacy_name("add_to_cart_action"),
        "add_to_cart_action",
        [("force_dialog", "stay")],
        table="website",
    )


def product_template_publish_date(env):
    """
    New required field publish_date replaces create_date as the key of the
    "Newest Arrivals" shop sort. Pre-create it from create_date, otherwise the
    ORM default (now) is written on every product and the sort becomes random.
    """
    if openupgrade.column_exists(env.cr, "product_template", "publish_date"):
        return
    openupgrade.add_fields(
        env,
        [
            (
                "publish_date",
                "product.template",
                "product_template",
                "datetime",
                False,
                "website_sale",
            )
        ],
    )
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE product_template
        SET publish_date = COALESCE(create_date, write_date, NOW() AT TIME ZONE 'UTC')
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    website_add_to_cart_action(env)
    product_template_publish_date(env)
