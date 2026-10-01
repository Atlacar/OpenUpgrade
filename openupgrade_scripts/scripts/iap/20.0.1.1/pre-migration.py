# Copyright 2026 Odoo Community Association (OCA)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    # iap.account.balance (char "<amount> <unit>") is now computed from the new
    # stored float balance_amount: parse the amount from the old char column
    # (the column stays in the table, it is just not used anymore)
    openupgrade.add_columns(
        env, [("iap.account", "balance_amount", "float", None, "iap_account")]
    )
    if openupgrade.column_exists(env.cr, "iap_account", "balance"):
        openupgrade.logged_query(
            env.cr,
            r"""
            UPDATE iap_account
            SET balance_amount = COALESCE(
                substring(balance FROM '^\s*(-?[0-9]+(?:\.[0-9]+)?)')::float, 0
            )
            """,
        )
