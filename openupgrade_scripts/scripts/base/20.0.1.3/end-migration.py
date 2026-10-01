# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _ir_actions_report_save_as_attachment(env):
    """ir.actions.report.save_as_attachment (new, only drives the form view): a
    report was saved as attachment when its 'attachment' expression was set. Done
    at the end so that the reports of all the modules are taken into account."""
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE ir_act_report_xml
        SET save_as_attachment = TRUE
        WHERE attachment IS NOT NULL AND attachment != ''
            AND save_as_attachment IS NOT TRUE
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    _ir_actions_report_save_as_attachment(env)
    openupgrade.disable_invalid_filters(env)
