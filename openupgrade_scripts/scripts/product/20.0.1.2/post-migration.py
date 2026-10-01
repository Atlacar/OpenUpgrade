# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _convert_attribute_exclusions(env):
    """product.template.attribute.exclusion (merged into
    product.template.attribute.value): the value excluding other values of the
    template becomes the owner of the m2m excluded_value_ids."""
    cr = env.cr
    if not openupgrade.table_exists(
        cr, "product_template_attribute_exclusion"
    ) or not openupgrade.table_exists(cr, "product_attr_exclusion_value_ids_rel"):
        return
    openupgrade.logged_query(
        cr,
        """
        INSERT INTO product_template_attribute_excluded_value_ids_rel (
            product_template_attribute_value_id,
            excluded_product_template_attribute_value_id
        )
        SELECT DISTINCT e.product_template_attribute_value_id,
            r.product_template_attribute_value_id
        FROM product_template_attribute_exclusion e
        JOIN product_attr_exclusion_value_ids_rel r
            ON r.product_template_attribute_exclusion_id = e.id
        WHERE e.product_template_attribute_value_id IS NOT NULL
        ON CONFLICT DO NOTHING
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    _convert_attribute_exclusions(env)
