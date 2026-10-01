# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    # ir.model.access / ir.rule -> ir.access, same xmlids (see
    # mail/20.0.1.19/pre-migration.py). Defensive: no-op if base already did it.
    openupgrade.logged_query(
        env.cr,
        """
        DELETE FROM ir_model_data
        WHERE module = 'sms' AND model IN ('ir.model.access', 'ir.rule')
        """,
    )
