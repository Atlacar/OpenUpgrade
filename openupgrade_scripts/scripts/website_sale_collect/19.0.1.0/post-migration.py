# Copyright 2026 Tecnativa - Pedro M. Baeza
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _mark_pickup_auxiliary_addresses(env):
    """Mark as pickup locations those delivery addresses of partners that match with the
    address data of the pickup locations. This is because this version has a patch for
    avoiding to show that auto-created addresses into the checkout form, which wasn't
    available in 18.

    More info at https://github.com/odoo/odoo/commit/1d24fc854fbb25fbf979f14ecc6a6507fba

    Meanwhile, in 18, it was fixed through OPW putting the record as archived:

    https://github.com/odoo/odoo/pull/242876

    For having consistency, let's put the flag even if they are archived.
    """
    pickup_locations = (
        env["delivery.carrier"]
        .with_context(active_test=False)
        .search([("delivery_type", "=", "in_store")])
        .warehouse_ids.partner_id
    )
    for p in pickup_locations:
        if not p.street:
            # Avoid flagging every address-less delivery contact
            continue
        # Same matching criteria as `sale.order._action_confirm` in `delivery`
        # (a domain `('field', '=', False)` matches NULL, hence IS NOT DISTINCT FROM)
        openupgrade.logged_query(
            env.cr,
            """
            UPDATE res_partner
            SET is_pickup_location = TRUE
            WHERE
                street IS NOT DISTINCT FROM %s
                AND city IS NOT DISTINCT FROM %s
                AND state_id IS NOT DISTINCT FROM %s
                AND country_id IS NOT DISTINCT FROM %s
                AND parent_id IS NOT NULL
                AND type = 'delivery'
                AND is_pickup_location IS NOT TRUE
            """,
            (
                p.street or None,
                p.city or None,
                p.state_id.id or None,
                p.country_id.id or None,
            ),
        )


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.load_data(env, "website_sale_collect", "19.0.1.0/noupdate_changes.xml")
    _mark_pickup_auxiliary_addresses(env)
