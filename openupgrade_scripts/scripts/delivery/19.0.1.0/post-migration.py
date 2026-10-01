# Copyright 2026 Tecnativa - Pilar Vargas
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def payment_provider_cod_disabled(env):
    """
    delivery 19 creates the 'Cash on Delivery' payment provider enabled and
    published (noupdate data). It is new in 19 like delivery.carrier
    #allow_cash_on_delivery, so on a migrated database no carrier allows it yet:
    disable and unpublish it, unless a carrier already allows cash on delivery.
    It can be enabled again once carriers are configured for it.
    """
    provider = env.ref("delivery.payment_provider_cod", raise_if_not_found=False)
    if not provider:
        return
    if env["delivery.carrier"].with_context(active_test=False).search_count(
        [("allow_cash_on_delivery", "=", True)], limit=1
    ):
        return
    provider.write({"state": "disabled", "is_published": False})


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.load_data(env, "delivery", "19.0.1.0/noupdate_changes.xml")
    payment_provider_cod_disabled(env)
