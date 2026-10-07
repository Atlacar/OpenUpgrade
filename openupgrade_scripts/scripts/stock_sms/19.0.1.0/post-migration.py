# Copyright 2026 ForgeFlow S.L. (https://www.forgeflow.com)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE res_company
        SET stock_confirmation_type = NULL
        WHERE stock_move_sms_validation IS DISTINCT FROM TRUE
         AND stock_confirmation_type = 'sms'
    """,
    )
    # 18 SMS confirmation on -> 19 text confirmation on (stock_text_confirmation is new in stock)
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE res_company
        SET stock_text_confirmation = TRUE
        WHERE stock_move_sms_validation IS TRUE
         AND stock_confirmation_type = 'sms'
    """,
    )
