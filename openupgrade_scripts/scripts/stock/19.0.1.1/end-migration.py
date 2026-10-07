# Copyright 2026 Hunki Enterprises BV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def _keep_sms_confirmation_off(env):
    """stock_sms auto-installed during the migration (not installed in 18, so no
    legacy res_company.stock_move_sms_validation column): its post_init_hook turns
    SMS delivery confirmation on for every company. Keep the 18 behaviour (off)."""
    if openupgrade.column_exists(
        env.cr, "res_company", "stock_move_sms_validation"
    ) or not openupgrade.is_module_installed(env.cr, "stock_sms"):
        return
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE res_company
        SET stock_text_confirmation = FALSE
        WHERE stock_text_confirmation AND stock_confirmation_type = 'sms'
        """,
    )


@openupgrade.migrate()
def migrate(env, version):
    _keep_sms_confirmation_off(env)
    env["stock.picking"].search(
        [
            ("move_line_ids", "not in", ("done", "cancel")),
        ]
    )._check_entire_pack()
