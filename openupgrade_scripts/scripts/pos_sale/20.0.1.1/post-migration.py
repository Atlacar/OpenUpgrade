# Copyright 2026 Hunki Enterprises BV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def pos_config_default_products(env):
    """
    pos.config#down_payment_product_id is now required (it was empty in v19 unless
    the user set it) and pos.config#default_product_id is new and required. The ORM
    fills both through pos.config#_init_column_default_products; make sure no NULL is
    left, e.g. when the products already existed.
    """
    for fname, xmlid in (
        ("down_payment_product_id", "pos_sale.default_downpayment_product"),
        ("default_product_id", "pos_sale.default_sol_product"),
    ):
        product = env.ref(xmlid, raise_if_not_found=False)
        if not product:
            continue
        openupgrade.logged_query(
            env.cr,
            f"UPDATE pos_config SET {fname} = %s WHERE {fname} IS NULL",
            (product.id,),
        )


@openupgrade.migrate()
def migrate(env, version):
    pos_config_default_products(env)
