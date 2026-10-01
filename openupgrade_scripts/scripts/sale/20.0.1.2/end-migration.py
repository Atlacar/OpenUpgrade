# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def sale_order_amount_unpaid(env):
    """sale.order#amount_unpaid (moved from pos_sale to sale) has another
    formula in 20.0, and is extended by pos_sale (refunds): recompute it once
    all the modules are loaded.
    """
    orders = env["sale.order"].with_context(active_test=False).search([])
    env.add_to_compute(env["sale.order"]._fields["amount_unpaid"], orders)
    orders._recompute_model(["amount_unpaid"])
    env.flush_all()


@openupgrade.migrate()
def migrate(env, version):
    sale_order_amount_unpaid(env)
