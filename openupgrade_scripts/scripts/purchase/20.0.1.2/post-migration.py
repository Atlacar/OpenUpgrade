# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

from odoo.addons.openupgrade_framework import template_tools


@openupgrade.migrate()
def migrate(env, version):
    template_tools.load_data_keep_customized(env, "purchase", "20.0.1.2/noupdate_changes.xml")
