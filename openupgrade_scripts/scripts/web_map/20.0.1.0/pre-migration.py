# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    # contact_address_complete is now defined in web_enterprise
    for model in ("res.partner", "res.users"):
        openupgrade.update_module_moved_fields(
            env.cr, model, ["contact_address_complete"], "web_map", "web_enterprise"
        )
