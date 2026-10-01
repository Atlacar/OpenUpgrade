# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def product_template_service_tracking(env):
    """The boolean service_to_purchase is replaced by the key 'subcontract' of
    service_tracking (see `_compute_service_tracking`: it requires purchase_ok
    and no re-invoicing). In 19 the boolean was company dependent (jsonb
    {"<company_id>": true}), so any company with true counts.
    """
    if not openupgrade.column_exists(env.cr, "product_template", "service_to_purchase"):
        return
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE product_template
        SET service_tracking = 'subcontract'
        WHERE EXISTS (
                SELECT 1 FROM jsonb_each_text(service_to_purchase::jsonb) j
                WHERE j.value = 'true')
            AND purchase_ok IS TRUE
            AND COALESCE(reinvoice_policy, 'no') = 'no'
            AND COALESCE(service_tracking, 'no') = 'no'
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    product_template_service_tracking(env)
