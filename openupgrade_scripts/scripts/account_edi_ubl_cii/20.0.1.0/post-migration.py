# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    # UN/ECE codes of the standard units of measure (noupdate data)
    openupgrade.load_data(env, "account_edi_ubl_cii", "20.0.1.0/noupdate_changes.xml")
